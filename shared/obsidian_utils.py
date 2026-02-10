"""Shared Obsidian vault utilities - replaces Obsidian MCP server.

Provides tag management, frontmatter parsing, note moving (with wikilink
updates), and vault search.  All functions operate directly on the filesystem.

Usage::

    sys.path.insert(0, r'C:\\Users\\thisi\\.claude\\skills')
    from shared.obsidian_utils import add_tags, move_note, search_vault
"""

import re
from pathlib import Path

VAULT_DIR = Path.home() / "Documents" / "Obsidian Vault"

# ── Frontmatter parsing ─────────────────────────────────────

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from note content.

    Returns (frontmatter_dict, body) where body is everything after ---.
    If no frontmatter found, returns ({}, full_content).
    """
    m = _FM_RE.match(content)
    if not m:
        return {}, content

    fm_text = m.group(1)
    body = content[m.end() :]
    fm: dict = {}

    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        # Parse inline lists: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = [
                x.strip().strip('"').strip("'")
                for x in val[1:-1].split(",")
                if x.strip()
            ]
            fm[key] = items
        # Parse booleans
        elif val.lower() in ("true", "false"):
            fm[key] = val.lower() == "true"
        # Parse numbers
        elif val.isdigit():
            fm[key] = int(val)
        # Strip surrounding quotes
        elif (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            fm[key] = val[1:-1]
        else:
            fm[key] = val

    return fm, body


def _serialize_frontmatter(fm: dict) -> str:
    """Serialize a frontmatter dict back to YAML string (between --- markers)."""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, list):
            items = ", ".join(str(x) for x in v)
            lines.append(f"{k}: [{items}]")
        elif '"' in str(v):
            lines.append(f"{k}: '{v}'")
        else:
            lines.append(f'{k}: "{v}"')
    lines.append("---")
    return "\n".join(lines)


def update_frontmatter(content: str, updates: dict) -> str:
    """Update frontmatter fields in note content. Creates frontmatter if missing."""
    fm, body = parse_frontmatter(content)
    fm.update(updates)
    return _serialize_frontmatter(fm) + "\n" + body


# ── Tag operations ───────────────────────────────────────────


def add_tags(
    filepath: str | Path, tags: list[str], vault_dir: Path = VAULT_DIR
) -> list[str]:
    """Add tags to a note's frontmatter. Returns the final tag list.

    Tags are deduplicated. Existing tags are preserved.
    """
    path = _resolve(filepath, vault_dir)
    content = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    existing = set(fm.get("tags", []))
    existing.update(tags)
    fm["tags"] = sorted(existing)

    path.write_text(_serialize_frontmatter(fm) + "\n" + body, encoding="utf-8")
    return fm["tags"]


def remove_tags(
    filepath: str | Path, tags: list[str], vault_dir: Path = VAULT_DIR
) -> list[str]:
    """Remove tags from a note's frontmatter. Returns the remaining tag list."""
    path = _resolve(filepath, vault_dir)
    content = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    existing = set(fm.get("tags", []))
    existing -= set(tags)
    fm["tags"] = sorted(existing)

    path.write_text(_serialize_frontmatter(fm) + "\n" + body, encoding="utf-8")
    return fm["tags"]


def rename_tag(old_tag: str, new_tag: str, vault_dir: Path = VAULT_DIR) -> list[str]:
    """Rename a tag across the entire vault. Returns list of modified file paths."""
    modified = []
    for md in vault_dir.rglob("*.md"):
        try:
            content = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        fm, body = parse_frontmatter(content)
        tags = fm.get("tags", [])
        if old_tag not in tags:
            continue

        tags = [new_tag if t == old_tag else t for t in tags]
        fm["tags"] = sorted(set(tags))
        md.write_text(_serialize_frontmatter(fm) + "\n" + body, encoding="utf-8")
        modified.append(str(md.relative_to(vault_dir)))

    return modified


def list_tags(vault_dir: Path = VAULT_DIR) -> dict[str, int]:
    """List all tags in the vault with their usage counts."""
    counts: dict[str, int] = {}
    for md in vault_dir.rglob("*.md"):
        try:
            content = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        fm, _ = parse_frontmatter(content)
        for tag in fm.get("tags", []):
            if isinstance(tag, str) and tag:
                counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ── Note move with wikilink updates ─────────────────────────

# Matches [[target]] and [[target|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]")


def move_note(
    source: str | Path,
    destination: str | Path,
    vault_dir: Path = VAULT_DIR,
) -> dict:
    """Move a note and update all wikilinks pointing to it.

    Args:
        source: Path relative to vault (e.g. "收件箱/Docker.md")
        destination: Path relative to vault (e.g. "写作/技术概念/Docker.md")
        vault_dir: Vault root directory

    Returns:
        {"moved": True, "links_updated": int, "files_touched": [...]}
    """
    src = vault_dir / source
    dst = vault_dir / destination
    if not src.exists():
        raise FileNotFoundError(f"Source not found: {source}")
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    # Obsidian wikilinks use stem (filename without extension)
    old_stem = src.stem
    new_stem = dst.stem

    # Ensure destination directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Move the file
    src.rename(dst)

    # Update wikilinks across vault (only if stem changed)
    files_touched = []
    links_updated = 0

    if old_stem != new_stem:
        for md in vault_dir.rglob("*.md"):
            if md == dst:
                continue
            try:
                content = md.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue

            new_content, count = _WIKILINK_RE.subn(
                lambda m: _replace_link(m, old_stem, new_stem),
                content,
            )
            if count > 0 and new_content != content:
                md.write_text(new_content, encoding="utf-8")
                actual = content.count(f"[[{old_stem}")
                if actual > 0:
                    files_touched.append(str(md.relative_to(vault_dir)))
                    links_updated += actual

    return {
        "moved": True,
        "links_updated": links_updated,
        "files_touched": files_touched,
    }


def _replace_link(match: re.Match, old_stem: str, new_stem: str) -> str:
    """Replace wikilink target if it matches old_stem."""
    target = match.group(1).strip()
    alias = match.group(2) or ""

    # Handle paths in links: [[folder/name]] → just compare name part
    target_stem = target.rsplit("/", 1)[-1] if "/" in target else target

    if target_stem == old_stem:
        if alias:
            return f"[[{new_stem}{alias}]]"
        return f"[[{new_stem}]]"
    return match.group(0)


# ── Search ───────────────────────────────────────────────────


def search_vault(
    query: str,
    vault_dir: Path = VAULT_DIR,
    search_type: str = "content",
    max_results: int = 20,
) -> list[dict]:
    """Search the vault.

    Args:
        query: Search string (case-insensitive substring match)
        search_type: "content" (search body), "filename" (search names),
                     "tag" (search tags), "frontmatter" (search all FM fields)
        max_results: Max results to return

    Returns:
        List of {"path": str, "match": str, "line": int|None}
    """
    results = []
    q = query.lower()

    for md in vault_dir.rglob("*.md"):
        if len(results) >= max_results:
            break

        rel = str(md.relative_to(vault_dir))

        if search_type == "filename":
            if q in md.stem.lower():
                results.append({"path": rel, "match": md.stem, "line": None})
            continue

        try:
            content = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        if search_type == "tag":
            fm, _ = parse_frontmatter(content)
            tags = fm.get("tags", [])
            if any(q in str(t).lower() for t in tags):
                results.append({"path": rel, "match": f"tags: {tags}", "line": None})

        elif search_type == "frontmatter":
            fm, _ = parse_frontmatter(content)
            for k, v in fm.items():
                if q in str(v).lower():
                    results.append({"path": rel, "match": f"{k}: {v}", "line": None})
                    break

        else:  # content
            for i, line in enumerate(content.split("\n"), 1):
                if q in line.lower():
                    snippet = line.strip()[:120]
                    results.append({"path": rel, "match": snippet, "line": i})
                    break  # one match per file

    return results


# ── Helpers ──────────────────────────────────────────────────


def _resolve(filepath: str | Path, vault_dir: Path) -> Path:
    """Resolve a filepath relative to vault or absolute."""
    p = Path(filepath)
    if p.is_absolute():
        return p
    return vault_dir / p


def get_note(filepath: str | Path, vault_dir: Path = VAULT_DIR) -> dict:
    """Read a note and return parsed structure.

    Returns: {"frontmatter": dict, "body": str, "path": str}
    """
    path = _resolve(filepath, vault_dir)
    content = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    return {"frontmatter": fm, "body": body, "path": str(path)}


def create_note(
    filepath: str | Path,
    content: str,
    vault_dir: Path = VAULT_DIR,
    overwrite: bool = False,
) -> Path:
    """Create a new note in the vault.

    Args:
        filepath: Relative path within vault (e.g. "收件箱/new note.md")
        content: Full markdown content (with or without frontmatter)
        overwrite: If False, raises error when file exists

    Returns:
        Absolute path of created note
    """
    path = vault_dir / filepath
    if path.exists() and not overwrite:
        raise FileExistsError(f"Note already exists: {filepath}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def delete_note(filepath: str | Path, vault_dir: Path = VAULT_DIR) -> dict:
    """Delete a note. Checks for incoming wikilinks first.

    Returns: {"deleted": bool, "incoming_links": [...]}
    If incoming_links is non-empty, deletion is skipped (safety).
    Pass the result to the caller for confirmation.
    """
    path = _resolve(filepath, vault_dir)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {filepath}")

    stem = path.stem
    incoming = []

    for md in vault_dir.rglob("*.md"):
        if md == path:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if f"[[{stem}" in text:
            incoming.append(str(md.relative_to(vault_dir)))

    if incoming:
        return {"deleted": False, "incoming_links": incoming}

    path.unlink()
    return {"deleted": True, "incoming_links": []}


def force_delete_note(filepath: str | Path, vault_dir: Path = VAULT_DIR) -> bool:
    """Delete a note regardless of incoming links. Returns True if deleted."""
    path = _resolve(filepath, vault_dir)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {filepath}")
    path.unlink()
    return True

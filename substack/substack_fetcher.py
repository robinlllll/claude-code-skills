"""Substack RSS to Obsidian pipeline.

Fetches Substack newsletters via RSS, summarizes content (copyright-compliant),
detects ticker symbols, and saves notes to Obsidian vault.

Usage:
    python substack_fetcher.py sync          # Pull all new articles
    python substack_fetcher.py add URL       # Add new subscription
    python substack_fetcher.py list          # Show subscriptions
"""

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

# ── Shared utilities ─────────────────────────────────────────
sys.path.insert(0, r"C:\Users\thisi\.claude\skills")

from shared.frontmatter_utils import (
    VAULT_DIR,
    build_frontmatter,
    is_already_ingested,
    make_url_hash,
    record_ingestion,
    safe_filename,
)
from shared.ticker_detector import detect_ticker_symbols

# ── Paths ────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent
CONFIG_PATH = SKILL_DIR / "substack_feeds.yaml"
RAW_CACHE_DIR = SKILL_DIR / "raw_cache"
SUBSTACK_VAULT_DIR = VAULT_DIR / "Substack"


# ── Feed Parsing ─────────────────────────────────────────────


def fetch_feed(feed_url: str) -> list[dict]:
    """Parse an RSS feed and return a list of article dicts.

    Each dict contains: title, link, published, content_html, author.

    Args:
        feed_url: Full RSS feed URL (e.g. https://name.substack.com/feed)

    Returns:
        List of article dicts from the feed.
    """
    import fastfeedparser

    try:
        result = fastfeedparser.parse(feed_url)
    except Exception as e:
        print(f"  [ERROR] Failed to fetch feed {feed_url}: {e}")
        return []

    articles = []
    for entry in result.get("entries", []):
        # Parse published date
        pub_date = None
        for date_field in ("published", "updated", "created"):
            raw = entry.get(date_field)
            if raw:
                pub_date = _parse_date(raw)
                if pub_date:
                    break

        # Get content HTML — prefer content:encoded, then summary
        content_html = ""
        if "content" in entry and entry["content"]:
            if isinstance(entry["content"], list):
                content_html = entry["content"][0].get("value", "")
            elif isinstance(entry["content"], str):
                content_html = entry["content"]
        if not content_html:
            content_html = entry.get("summary", "")

        # Extract author
        author = ""
        if "author" in entry:
            author = entry["author"]
        elif "author_detail" in entry:
            author = entry["author_detail"].get("name", "")

        articles.append(
            {
                "title": entry.get("title", "Untitled"),
                "link": entry.get("link", ""),
                "published": pub_date,
                "content_html": content_html,
                "author": author,
            }
        )

    return articles


def _parse_date(date_str: str) -> date | None:
    """Try multiple date formats to parse a date string."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    # Last resort: try dateutil if available
    try:
        from dateutil.parser import parse as dateutil_parse

        return dateutil_parse(date_str).date()
    except Exception:
        return None


# ── Full Text Extraction ─────────────────────────────────────


def extract_full_text(article_url: str) -> str:
    """Fetch and extract full article text using trafilatura.

    Used as fallback when RSS content is truncated (< 500 chars).

    Args:
        article_url: URL of the article to fetch.

    Returns:
        Extracted text content, or empty string on failure.
    """
    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(article_url)
        if not downloaded:
            print(f"  [WARN] trafilatura could not download: {article_url}")
            return ""
        text = trafilatura.extract(
            downloaded, include_comments=False, include_tables=True
        )
        return text or ""
    except Exception as e:
        print(f"  [ERROR] trafilatura extraction failed for {article_url}: {e}")
        return ""


# ── HTML to Markdown ─────────────────────────────────────────


def _html_to_markdown(html: str) -> str:
    """Convert HTML content to Markdown."""
    try:
        from markdownify import markdownify as md

        return md(html, heading_style="ATX", strip=["img", "script", "style"])
    except Exception:
        # Fallback: strip HTML tags with regex
        clean = re.sub(r"<[^>]+>", "", html)
        return clean


# ── Summarization ────────────────────────────────────────────


def summarize_content(full_text: str, max_words: int = 500) -> tuple[str, list[str]]:
    """Generate a summary and key excerpts from article text.

    Summary: first ~max_words words of the article.
    Key excerpts: up to 3 paragraphs longer than 50 words, selected from
    the article body (skipping the first paragraph which is already in
    the summary).

    Args:
        full_text: Full article text (Markdown or plain text).
        max_words: Maximum word count for the summary.

    Returns:
        Tuple of (summary_text, list_of_excerpt_strings).
    """
    if not full_text or not full_text.strip():
        return ("", [])

    # Build summary from first N words
    words = full_text.split()
    if len(words) <= max_words:
        summary = full_text.strip()
    else:
        summary_words = words[:max_words]
        summary = " ".join(summary_words)
        # Try to end at a sentence boundary
        last_period = summary.rfind(".")
        last_question = summary.rfind("?")
        last_exclaim = summary.rfind("!")
        best_end = max(last_period, last_question, last_exclaim)
        if best_end > len(summary) * 0.5:
            summary = summary[: best_end + 1]

    # Pick key excerpts: paragraphs with >50 words, not already in summary
    paragraphs = re.split(r"\n\s*\n", full_text)
    excerpts = []
    summary_lower = summary.lower()
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_words = para.split()
        if len(para_words) < 50:
            continue
        # Skip if this paragraph is substantially contained in the summary
        if para[:100].lower() in summary_lower:
            continue
        excerpts.append(para)
        if len(excerpts) >= 3:
            break

    return (summary, excerpts)


# ── Save to Obsidian ─────────────────────────────────────────


def save_to_obsidian(article: dict, author_name: str) -> Path:
    """Save article summary + excerpts to Obsidian vault.

    Creates note at: Substack/{author_name}/YYYY-MM-DD - {title}.md

    Args:
        article: Dict with keys: title, link, published, content_html, author,
                 and optionally: markdown_text, summary, excerpts, tickers.
        author_name: Display name for the author (used as subfolder).

    Returns:
        Path to the created Obsidian note.
    """
    pub_date = article.get("published") or date.today()
    title = safe_filename(article.get("title", "Untitled"))
    filename = f"{pub_date.isoformat()} - {title}.md"

    # Ensure author directory exists
    safe_author = safe_filename(author_name) if author_name else "Unknown"
    output_dir = SUBSTACK_VAULT_DIR / safe_author
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    # Prepare content
    url_hash = make_url_hash(article.get("link", ""))
    tickers = article.get("tickers", [])
    summary = article.get("summary", "")
    excerpts = article.get("excerpts", [])

    # Build frontmatter
    canonical_key = f"substack_{url_hash}"
    tags = ["substack", "newsletter"]
    if tickers:
        tags.append("has-tickers")

    frontmatter = build_frontmatter(
        id=canonical_key,
        type="substack",
        source_platform="substack",
        author=article.get("author", author_name),
        source_url=article.get("link", ""),
        published_at=pub_date if isinstance(pub_date, date) else None,
        tickers=tickers,
        tags=tags,
    )

    # Build note body
    lines = [frontmatter, ""]
    lines.append(f"# {article.get('title', 'Untitled')}")
    lines.append("")
    lines.append(f"**Author:** {article.get('author', author_name)}")
    lines.append(f"**Published:** {pub_date.isoformat()}")
    lines.append(
        f"**Source:** [{article.get('title', 'Link')}]({article.get('link', '')})"
    )
    lines.append("")

    if tickers:
        lines.append(f"**Tickers mentioned:** {', '.join(tickers)}")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    if summary:
        lines.append(summary)
    else:
        lines.append("*No summary available.*")
    lines.append("")

    if excerpts:
        lines.append("## Key Excerpts")
        lines.append("")
        for i, excerpt in enumerate(excerpts, 1):
            lines.append(f"### Excerpt {i}")
            lines.append("")
            lines.append(f"> {excerpt}")
            lines.append("")

    lines.append("---")
    lines.append(
        f"*Read the full article: [{article.get('title', 'Link')}]({article.get('link', '')})*"
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ── Raw Cache ────────────────────────────────────────────────


def _cache_raw_html(article: dict) -> None:
    """Save raw HTML to local cache directory (not synced to Obsidian)."""
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = make_url_hash(article.get("link", ""))
    cache_file = RAW_CACHE_DIR / f"{url_hash}.html"
    html = article.get("content_html", "")
    if html:
        cache_file.write_text(html, encoding="utf-8")


# ── Config Management ────────────────────────────────────────


def _load_config(config_path: Path | None = None) -> dict:
    """Load feed configuration from YAML file."""
    path = config_path or CONFIG_PATH
    if not path.exists():
        return {"feeds": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "feeds" not in data:
        return {"feeds": []}
    # Ensure feeds is a list (handle null)
    if data["feeds"] is None:
        data["feeds"] = []
    return data


def _save_config(config: dict, config_path: Path | None = None) -> None:
    """Save feed configuration to YAML file."""
    path = config_path or CONFIG_PATH
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def _normalize_feed_url(url: str) -> tuple[str, str]:
    """Normalize a Substack URL to a feed URL and extract the author name.

    Accepts:
        https://name.substack.com
        https://name.substack.com/feed
        name.substack.com

    Returns:
        Tuple of (feed_url, author_name).
    """
    url = url.strip().rstrip("/")

    # Add scheme if missing
    if not url.startswith("http"):
        url = "https://" + url

    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Extract name from subdomain
    if "substack.com" in hostname:
        author_name = hostname.replace(".substack.com", "")
    else:
        # Custom domain — use hostname as name
        author_name = hostname.split(".")[0]

    # Ensure /feed path
    if not parsed.path.rstrip("/").endswith("/feed"):
        feed_url = f"{parsed.scheme}://{parsed.netloc}/feed"
    else:
        feed_url = url

    return (feed_url, author_name)


# ── Main Commands ────────────────────────────────────────────


def sync_all(config_path: Path | None = None) -> dict:
    """Sync all subscribed feeds: fetch, dedup, summarize, save.

    Args:
        config_path: Optional path to feeds YAML config.

    Returns:
        Stats dict with keys: total_feeds, total_articles, new_saved, skipped, errors.
    """
    config = _load_config(config_path)
    feeds = config.get("feeds", [])

    stats = {
        "total_feeds": len(feeds),
        "total_articles": 0,
        "new_saved": 0,
        "skipped": 0,
        "errors": 0,
        "saved_paths": [],
    }

    if not feeds:
        print("[INFO] No feeds configured. Use 'add' to add a subscription.")
        return stats

    for feed_info in feeds:
        feed_name = feed_info.get("name", "Unknown")
        feed_url = feed_info.get("url", "")
        if not feed_url:
            print(f"  [WARN] Skipping feed '{feed_name}' — no URL configured.")
            continue

        print(f"\n[SYNC] {feed_name} ({feed_url})")

        articles = fetch_feed(feed_url)
        if not articles:
            print("  No articles found or feed unreachable.")
            continue

        print(f"  Found {len(articles)} articles in feed.")
        stats["total_articles"] += len(articles)

        for article in articles:
            link = article.get("link", "")
            if not link:
                stats["errors"] += 1
                continue

            url_hash = make_url_hash(link)

            # Dedup check
            if is_already_ingested("substack", url_hash):
                stats["skipped"] += 1
                continue

            try:
                print(f"  Processing: {article.get('title', 'Untitled')}")

                # Cache raw HTML
                _cache_raw_html(article)

                # Convert HTML to markdown
                content_html = article.get("content_html", "")
                markdown_text = _html_to_markdown(content_html)

                # Fallback to trafilatura if content is truncated
                if len(markdown_text.split()) < 500:
                    print(
                        f"    RSS content short ({len(markdown_text.split())} words), trying trafilatura..."
                    )
                    full_text = extract_full_text(link)
                    if full_text and len(full_text.split()) > len(
                        markdown_text.split()
                    ):
                        markdown_text = full_text
                        print(
                            f"    trafilatura extracted {len(full_text.split())} words."
                        )

                # Summarize
                summary, excerpts = summarize_content(markdown_text)

                # Detect tickers
                tickers = detect_ticker_symbols(markdown_text)

                # Enrich article dict
                article["markdown_text"] = markdown_text
                article["summary"] = summary
                article["excerpts"] = excerpts
                article["tickers"] = tickers

                # Determine author name (prefer feed-level name, fallback to article author)
                author_display = feed_name or article.get("author", "Unknown")

                # Save to Obsidian
                saved_path = save_to_obsidian(article, author_display)
                print(f"    Saved: {saved_path}")

                # Record ingestion
                canonical_key = record_ingestion(
                    source_platform="substack",
                    stable_id=url_hash,
                    obsidian_path=str(saved_path),
                    metadata=article.get("title", ""),
                )

                # Record pipeline entry for stage tracking
                try:
                    from shared.task_manager import record_pipeline_entry

                    record_pipeline_entry(
                        canonical_key=canonical_key,
                        item_type="substack",
                        item_title=article.get("title", ""),
                        source_platform="substack",
                        obsidian_path=str(saved_path),
                        note_id=canonical_key,
                        has_frontmatter=True,
                        has_tickers=bool(tickers),
                        tickers_found=tickers,
                    )
                except ImportError:
                    pass

                stats["new_saved"] += 1
                stats["saved_paths"].append(str(saved_path))

            except Exception as e:
                print(
                    f"    [ERROR] Failed to process '{article.get('title', '?')}': {e}"
                )
                stats["errors"] += 1

    return stats


def add_feed(url: str, config_path: Path | None = None) -> None:
    """Add a new Substack subscription.

    Args:
        url: Substack URL (e.g. https://name.substack.com or https://name.substack.com/feed)
        config_path: Optional path to feeds YAML config.
    """
    config = _load_config(config_path)
    feed_url, author_name = _normalize_feed_url(url)

    # Check for duplicates
    for existing in config.get("feeds", []):
        if existing.get("url") == feed_url:
            print(f"[INFO] Feed already exists: {author_name} ({feed_url})")
            return

    config["feeds"].append(
        {
            "name": author_name,
            "url": feed_url,
        }
    )
    _save_config(config, config_path)
    print(f"[ADDED] {author_name} ({feed_url})")


def list_feeds(config_path: Path | None = None) -> list:
    """List all subscribed feeds.

    Args:
        config_path: Optional path to feeds YAML config.

    Returns:
        List of feed dicts with name and url.
    """
    config = _load_config(config_path)
    feeds = config.get("feeds", [])

    if not feeds:
        print("[INFO] No feeds configured. Use 'add' to add a subscription.")
        return []

    print(f"\nSubstack Subscriptions ({len(feeds)} feeds):")
    print("-" * 50)
    for i, feed in enumerate(feeds, 1):
        print(f"  {i}. {feed.get('name', 'Unknown')} — {feed.get('url', 'N/A')}")
    print()

    return feeds


# ── CLI Entry Point ──────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Substack RSS to Obsidian pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python substack_fetcher.py sync
  python substack_fetcher.py add https://doomberg.substack.com
  python substack_fetcher.py list
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync all subscribed feeds")
    sync_parser.add_argument(
        "--config", type=Path, default=None, help="Path to feeds YAML config"
    )

    # add
    add_parser = subparsers.add_parser("add", help="Add a new Substack subscription")
    add_parser.add_argument("url", help="Substack URL (e.g. https://name.substack.com)")
    add_parser.add_argument(
        "--config", type=Path, default=None, help="Path to feeds YAML config"
    )

    # list
    list_parser = subparsers.add_parser("list", help="List all subscriptions")
    list_parser.add_argument(
        "--config", type=Path, default=None, help="Path to feeds YAML config"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sync":
        print("=" * 60)
        print("Substack RSS to Obsidian — Sync")
        print("=" * 60)
        stats = sync_all(config_path=args.config)
        print()
        print("=" * 60)
        print(
            f"Done. Feeds: {stats['total_feeds']} | "
            f"Articles: {stats['total_articles']} | "
            f"New: {stats['new_saved']} | "
            f"Skipped: {stats['skipped']} | "
            f"Errors: {stats['errors']}"
        )
        print("=" * 60)

    elif args.command == "add":
        add_feed(args.url, config_path=args.config)

    elif args.command == "list":
        list_feeds(config_path=args.config)


if __name__ == "__main__":
    main()

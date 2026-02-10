#!/usr/bin/env python3
"""
Version Manager for Prompt Optimizer
Handles prompt version storage with manifest-based tracking
"""

from __future__ import annotations

import json
import time
import difflib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class VersionMeta:
    version: int
    created_at: float
    source: str
    notes: str
    chars: int


class VersionManager:
    """Manages prompt versions within a session"""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.versions_dir = self.session_dir / "versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.versions_dir / "manifest.json"
        if not self.manifest_path.exists():
            self._write_manifest([])

    def _read_manifest(self) -> list[dict]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, items: list[dict]) -> None:
        self.manifest_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def latest_version(self) -> Optional[int]:
        """Get the latest version number, or None if no versions exist"""
        items = self._read_manifest()
        return items[-1]["version"] if items else None

    def read_version(self, version: int) -> str:
        """Read the content of a specific version"""
        p = self.versions_dir / f"v{version}.md"
        return p.read_text(encoding="utf-8")

    def add_version(self, text: str, source: str, notes: str = "") -> VersionMeta:
        """
        Add a new version of the prompt.

        Args:
            text: The prompt content
            source: Origin (e.g., "user", "claude", "iteration")
            notes: Optional notes about this version

        Returns:
            VersionMeta with version info
        """
        v = (self.latest_version() or 0) + 1
        path = self.versions_dir / f"v{v}.md"
        path.write_text(text, encoding="utf-8")

        meta = VersionMeta(
            version=v,
            created_at=time.time(),
            source=source,
            notes=notes,
            chars=len(text),
        )
        manifest = self._read_manifest()
        manifest.append(asdict(meta))
        self._write_manifest(manifest)
        return meta

    def diff(self, a: int, b: int) -> str:
        """Generate unified diff between two versions"""
        ta = self.read_version(a).splitlines(keepends=True)
        tb = self.read_version(b).splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                ta, tb,
                fromfile=f"v{a}.md",
                tofile=f"v{b}.md",
            )
        )

    def list_versions(self) -> list[dict]:
        """Get all version metadata"""
        return self._read_manifest()


def main():
    """Test version manager"""
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description='Test version manager')
    parser.add_argument('--test', action='store_true', help='Run test')

    args = parser.parse_args()

    if args.test:
        with tempfile.TemporaryDirectory() as tmpdir:
            vm = VersionManager(Path(tmpdir))

            v1 = vm.add_version("Write a poem about cats.", source="user")
            print(f"Added v{v1.version}: {v1.chars} chars")

            v2 = vm.add_version("Write a short rhyming poem about cats.", source="claude", notes="Added constraints")
            print(f"Added v{v2.version}: {v2.chars} chars")

            print(f"\nLatest: v{vm.latest_version()}")
            print(f"\nDiff:\n{vm.diff(1, 2)}")
    else:
        print("Use --test to run test")


if __name__ == "__main__":
    main()

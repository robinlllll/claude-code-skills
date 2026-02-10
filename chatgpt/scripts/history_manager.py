#!/usr/bin/env python3
"""
ChatGPT Answer History Manager
Persists Q&A pairs to JSON (structured) and Obsidian (human-readable).

JSON:     data/history.json — searchable, programmatic access
Obsidian: ~/Documents/Obsidian Vault/ChatGPT/ChatGPT_YYYY-MM-DD.md — one file per day
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent))

from config import HISTORY_FILE, DATA_DIR, OBSIDIAN_DIR


class HistoryManager:
    """Manages persistent Q&A history for ChatGPT queries."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.history_file = HISTORY_FILE
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load history from JSON file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  Warning: Could not load history ({e}), starting fresh", file=sys.stderr)
        return {"version": 1, "updated_at": "", "total_entries": 0, "entries": []}

    def _persist(self):
        """Write history to JSON file."""
        self._data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._data["total_entries"] = len(self._data["entries"])
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def _next_id(self) -> int:
        if not self._data["entries"]:
            return 1
        return max(e["id"] for e in self._data["entries"]) + 1

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Convert name to a safe filename."""
        cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
        return cleaned.strip() or "ChatGPT"

    # ── Public API ──────────────────────────────────────────────

    def save(
        self,
        question: str,
        answer: str,
        model: str = "default",
    ) -> Dict[str, Any]:
        """
        Persist a Q&A pair to JSON history and append to Obsidian log.
        Returns the saved entry dict.
        """
        now = datetime.now()

        entry = {
            "id": self._next_id(),
            "timestamp": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "question": question,
            "answer": answer,
            "model": model,
        }

        self._data["entries"].append(entry)
        self._persist()

        # Also write to Obsidian
        self._append_obsidian(entry)

        return entry

    def search(
        self, query: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Case-insensitive search across question + answer text."""
        q = query.lower()
        results = []
        for entry in reversed(self._data["entries"]):
            if q in entry["question"].lower() or q in entry["answer"].lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent entries, newest first."""
        return list(reversed(self._data["entries"]))[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Total count and per-model breakdown."""
        by_model: Dict[str, int] = {}
        for entry in self._data["entries"]:
            key = entry.get("model", "default")
            by_model[key] = by_model.get(key, 0) + 1

        return {
            "total": len(self._data["entries"]),
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])),
            "history_file": str(self.history_file),
            "obsidian_dir": str(OBSIDIAN_DIR),
        }

    # ── Obsidian output ─────────────────────────────────────────

    def _append_obsidian(self, entry: Dict[str, Any]):
        """Append a Q&A entry to the daily Obsidian markdown file."""
        OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)

        filename = f"ChatGPT_{entry['date']}.md"
        filepath = OBSIDIAN_DIR / filename

        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            # Update the 'updated' field in frontmatter
            content = re.sub(
                r"^updated: .+$",
                f"updated: {entry['date']}",
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            content = (
                f"---\n"
                f"type: chatgpt-log\n"
                f"created: {entry['date']}\n"
                f"updated: {entry['date']}\n"
                f"tags: [chatgpt, qa-log]\n"
                f"---\n\n"
                f"# ChatGPT Q&A - {entry['date']}\n\n"
                f"> Auto-saved by ChatGPT skill.\n\n"
            )

        # Append the new entry
        model_tag = f" `{entry['model']}`" if entry.get("model", "default") != "default" else ""
        qa_block = (
            f"## {entry['time']}{model_tag}\n\n"
            f"**Q:** {entry['question']}\n\n"
            f"**A:** {entry['answer']}\n\n"
            f"---\n\n"
        )
        content += qa_block

        filepath.write_text(content, encoding="utf-8")


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ChatGPT Answer History")
    sub = parser.add_subparsers(dest="command")

    sp = sub.add_parser("search", help="Search Q&A history")
    sp.add_argument("--query", required=True, help="Search term")
    sp.add_argument("--limit", type=int, default=20, help="Max results")

    lp = sub.add_parser("list", help="List recent Q&A entries")
    lp.add_argument("--limit", type=int, default=10, help="Max entries")

    sub.add_parser("stats", help="Show history statistics")

    args = parser.parse_args()
    mgr = HistoryManager()

    if args.command == "search":
        results = mgr.search(args.query, limit=args.limit)
        if results:
            print(f"\nFound {len(results)} results for '{args.query}':\n")
            for e in results:
                model_tag = f" [{e.get('model', '')}]" if e.get("model") else ""
                print(f"  [{e['date']}]{model_tag}")
                print(f"  Q: {e['question'][:100]}")
                print(f"  A: {e['answer'][:150]}...")
                print()
        else:
            print(f"No results for '{args.query}'")

    elif args.command == "list":
        entries = mgr.get_history(limit=args.limit)
        if entries:
            print(f"\nRecent Q&A ({len(entries)} entries):\n")
            for e in entries:
                model_tag = f" [{e.get('model', '')}]" if e.get("model") else ""
                print(f"  [{e['date']} {e['time']}]{model_tag}")
                print(f"  Q: {e['question'][:100]}")
                print(f"  A: {e['answer'][:150]}...")
                print()
        else:
            print("No history entries yet.")

    elif args.command == "stats":
        stats = mgr.get_stats()
        print("\nChatGPT History Statistics:")
        print(f"  Total Q&A pairs: {stats['total']}")
        print(f"  History file: {stats['history_file']}")
        print(f"  Obsidian dir: {stats['obsidian_dir']}")
        if stats["by_model"]:
            print("\n  By model:")
            for model, count in stats["by_model"].items():
                print(f"    {model}: {count}")
        print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

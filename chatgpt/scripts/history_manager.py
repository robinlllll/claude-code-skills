#!/usr/bin/env python3
"""
ChatGPT Answer History Manager
Persists Q&A pairs to JSON (structured) and Obsidian (human-readable).

JSON:     data/history.json — searchable, programmatic access
Obsidian: ~/Documents/Obsidian Vault/ChatGPT/ChatGPT_YYYY-MM-DD.md — one file per day
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"
OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian Vault" / "ChatGPT"


class HistoryManager:
    """Manages persistent Q&A history for ChatGPT queries."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.history_file = HISTORY_FILE
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(
                    f"  Warning: Could not load history ({e}), starting fresh",
                    file=sys.stderr,
                )
        return {"version": 1, "updated_at": "", "total_entries": 0, "entries": []}

    def _persist(self):
        self._data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._data["total_entries"] = len(self._data["entries"])
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def _next_id(self) -> int:
        if not self._data["entries"]:
            return 1
        return max(e["id"] for e in self._data["entries"]) + 1

    def save(
        self, question: str, answer: str, model: str = "default"
    ) -> dict[str, Any]:
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
        self._append_obsidian(entry)
        return entry

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        results = []
        for entry in reversed(self._data["entries"]):
            if q in entry["question"].lower() or q in entry["answer"].lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self._data["entries"]))[:limit]

    def get_stats(self) -> dict[str, Any]:
        by_model: dict[str, int] = {}
        for entry in self._data["entries"]:
            key = entry.get("model", "default")
            by_model[key] = by_model.get(key, 0) + 1
        return {
            "total": len(self._data["entries"]),
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])),
        }

    def _append_obsidian(self, entry: dict[str, Any]):
        OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"ChatGPT_{entry['date']}.md"
        filepath = OBSIDIAN_DIR / filename

        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
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

        model_tag = (
            f" `{entry['model']}`" if entry.get("model", "default") != "default" else ""
        )
        qa_block = (
            f"## {entry['time']}{model_tag}\n\n"
            f"**Q:** {entry['question']}\n\n"
            f"**A:** {entry['answer']}\n\n"
            f"---\n\n"
        )
        content += qa_block
        filepath.write_text(content, encoding="utf-8")

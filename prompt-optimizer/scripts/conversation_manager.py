#!/usr/bin/env python3
"""
Conversation Manager for Prompt Optimizer
Tracks review rounds: Gemini output + user feedback (no Claude analysis stored)
"""

from __future__ import annotations

import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class RoundRecord:
    """A single review round record"""

    round: int
    created_at: float
    prompt_version: int
    gemini_model: str
    gemini_review: str
    user_feedback: str = ""
    test_report: str = ""
    notes: str = ""
    gpt_model: str = ""
    gpt_review: str = ""
    synthesis: str = ""
    gemini_time: float = 0.0
    gpt_time: float = 0.0


class ConversationManager:
    """Manages review round history"""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)
        self.conv_dir = self.session_dir / "conversations"
        self.conv_dir.mkdir(parents=True, exist_ok=True)

    def next_round(self) -> int:
        """Get the next round number"""
        existing = sorted(self.conv_dir.glob("round_*.json"))
        if not existing:
            return 1
        last = existing[-1].stem.split("_")[-1]
        return int(last) + 1

    def current_round(self) -> Optional[int]:
        """Get the current (latest) round number"""
        existing = sorted(self.conv_dir.glob("round_*.json"))
        if not existing:
            return None
        return int(existing[-1].stem.split("_")[-1])

    def save_round(self, rec: RoundRecord) -> Path:
        """Save a round record"""
        p = self.conv_dir / f"round_{rec.round:03d}.json"
        p.write_text(
            json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return p

    def load_round(self, n: int) -> dict[str, Any]:
        """Load a round record"""
        p = self.conv_dir / f"round_{n:03d}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def update_round(self, n: int, **updates) -> dict[str, Any]:
        """Update fields in an existing round"""
        rec = self.load_round(n)
        rec.update(updates)
        p = self.conv_dir / f"round_{n:03d}.json"
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return rec

    def list_rounds(self) -> list[dict]:
        """Get summary of all rounds"""
        rounds = []
        for p in sorted(self.conv_dir.glob("round_*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            rounds.append(
                {
                    "round": rec["round"],
                    "prompt_version": rec["prompt_version"],
                    "has_feedback": bool(rec.get("user_feedback")),
                    "model": rec.get("gemini_model", "unknown"),
                }
            )
        return rounds

    def get_history_excerpt(self, last_n: int = 2) -> str:
        """Get recent history as text for context"""
        existing = sorted(self.conv_dir.glob("round_*.json"))
        if not existing:
            return ""

        lines = []
        for p in existing[-last_n:]:
            rec = json.loads(p.read_text(encoding="utf-8"))
            lines.append(f"[Round {rec['round']} - v{rec['prompt_version']}]")
            if rec.get("user_feedback"):
                lines.append(f"User feedback: {rec['user_feedback'][:200]}")
        return "\n".join(lines)


def main():
    """Test conversation manager"""
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description="Test conversation manager")
    parser.add_argument("--test", action="store_true", help="Run test")

    args = parser.parse_args()

    if args.test:
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = ConversationManager(Path(tmpdir))

            # Save a round
            cm.save_round(
                RoundRecord(
                    round=1,
                    created_at=time.time(),
                    prompt_version=1,
                    gemini_model="gemini-2.0-flash",
                    gemini_review="Verdict: FAIL\n1. Too vague...",
                )
            )

            # Add feedback
            cm.update_round(1, user_feedback="Agree, need more specifics")

            # List
            print(cm.list_rounds())
    else:
        print("Use --test to run test")


if __name__ == "__main__":
    main()

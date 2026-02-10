#!/usr/bin/env python3
"""
Session Manager for Prompt Optimizer
Simplified: event-driven state derived from artifacts, not hardcoded state machine
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class SessionState:
    """Session state - computed from artifacts, not stored transitions"""
    schema_version: int
    session_id: str
    goal: str
    created_at: float
    updated_at: float
    status: str  # INITIALIZED, HAS_VERSION, REVIEWING, COMPLETED
    active_version: Optional[int] = None
    active_round: int = 0


class SessionManager:
    """Manages optimization sessions"""

    def __init__(self, base_sessions_dir: Path):
        self.base_sessions_dir = Path(base_sessions_dir)
        self.base_sessions_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, session_dir: Path) -> Path:
        return session_dir / "state.json"

    def create(self, goal: str) -> Path:
        """Create a new session with spec.md skeleton"""
        sid = uuid.uuid4().hex[:12]
        session_dir = self.base_sessions_dir / sid

        # Create directory structure
        (session_dir / "versions").mkdir(parents=True, exist_ok=True)
        (session_dir / "conversations").mkdir(parents=True, exist_ok=True)
        (session_dir / "tests").mkdir(parents=True, exist_ok=True)

        now = time.time()
        state = SessionState(
            schema_version=1,
            session_id=sid,
            goal=goal,
            created_at=now,
            updated_at=now,
            status="INITIALIZED",
            active_version=None,
            active_round=0,
        )
        self._state_path(session_dir).write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Create spec.md skeleton
        spec_content = f"""# PromptSpec

## Goal
{goal}

## 任务一句话
（用一句话描述这个 prompt 要完成的任务）

## 输入
- 输入格式：
- 输入示例：

## 输出
- 输出格式：
- 输出示例：

## 硬约束（必须满足）
-

## 软约束（尽量满足）
-

## 必须避免
-

## 评估标准
-

## 测试用例
见 tests/ 目录
"""
        (session_dir / "spec.md").write_text(spec_content, encoding="utf-8")

        # Create example test case
        test_example = """# Test Case 001

## Input
（测试输入）

## Expected Output Characteristics
（期望输出的特征，不是固定答案）
-
-

## Pass Criteria
-
"""
        (session_dir / "tests" / "case_001.md").write_text(test_example, encoding="utf-8")

        return session_dir

    def load(self, session_id: str) -> SessionState:
        """Load session state"""
        session_dir = self.base_sessions_dir / session_id
        data = json.loads(self._state_path(session_dir).read_text(encoding="utf-8"))
        return SessionState(**data)

    def update(self, session_id: str, **kwargs) -> SessionState:
        """Update session state fields"""
        session_dir = self.base_sessions_dir / session_id
        state = self.load(session_id)
        d = asdict(state)
        d.update(kwargs)
        d["updated_at"] = time.time()
        self._state_path(session_dir).write_text(
            json.dumps(d, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return SessionState(**d)

    def list_sessions(self) -> list[dict]:
        """List all sessions"""
        sessions = []
        for d in self.base_sessions_dir.iterdir():
            if d.is_dir() and (d / "state.json").exists():
                state = self.load(d.name)
                sessions.append({
                    "id": state.session_id,
                    "goal": state.goal[:50] + "..." if len(state.goal) > 50 else state.goal,
                    "status": state.status,
                    "active_version": state.active_version,
                })
        return sorted(sessions, key=lambda x: x["id"], reverse=True)

    def get_session_dir(self, session_id: str) -> Path:
        """Get session directory path"""
        return self.base_sessions_dir / session_id

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists"""
        return (self.base_sessions_dir / session_id / "state.json").exists()


def main():
    """Test session manager"""
    import argparse

    parser = argparse.ArgumentParser(description='Session manager')
    parser.add_argument('--new', metavar='GOAL', help='Create new session')
    parser.add_argument('--list', action='store_true', help='List sessions')
    parser.add_argument('--show', metavar='ID', help='Show session')

    args = parser.parse_args()

    # Use actual data directory
    skill_dir = Path(__file__).parent.parent
    sm = SessionManager(skill_dir / "data" / "sessions")

    if args.new:
        session_dir = sm.create(args.new)
        print(f"Created: {session_dir.name}")
        return

    if args.list:
        for s in sm.list_sessions():
            print(f"{s['id']}  {s['status']:<15}  {s['goal']}")
        return

    if args.show:
        state = sm.load(args.show)
        print(json.dumps(asdict(state), ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()

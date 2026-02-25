"""Pydantic data models for the investment decision tracking system.

Defines schemas for:
- DecisionRecord / OutcomeRecord (SQLite via db_utils)
- FailureRecord (JSONL via jsonl_utils)
- ConsensusRecord / PriceAlertRecord (existing JSONL, now validated)
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enums ──


class DecisionType(str, Enum):
    buy = "buy"
    sell = "sell"
    add = "add"
    trim = "trim"
    hold = "hold"
    skip = "skip"
    watchlist = "watchlist"


class Trigger(str, Enum):
    earnings = "earnings"
    thesis = "thesis"
    valuation = "valuation"
    macro = "macro"
    thirteenf = "13f"
    technical = "technical"
    other = "other"


class OutcomeResult(str, Enum):
    win = "win"
    loss = "loss"
    neutral = "neutral"


class FailureType(str, Enum):
    late_stop = "止损过晚"
    chasing = "追涨"
    over_concentration = "过度集中"
    ignore_kill = "忽视kill_criteria"
    insufficient_info = "信息不足交易"
    bad_timing = "时机错误"
    oversize = "仓位过大"
    anchoring_bias = "锚定效应"
    other = "other"


class CognitiveBias(str, Enum):
    anchoring = "anchoring"
    confirmation = "confirmation"
    loss_aversion = "loss_aversion"
    recency = "recency"
    overconfidence = "overconfidence"
    herd = "herd"
    sunk_cost = "sunk_cost"
    none = "none"


# ── Record Models ──


class DecisionRecord(BaseModel):
    """Investment decision — stored in SQLite decisions table."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    date: str  # YYYY-MM-DD
    ticker: str  # uppercase, e.g. "CELH"
    decision_type: DecisionType
    reasoning: str
    alternatives: str = ""
    conviction: int = Field(default=5, ge=1, le=10)
    thesis_link: str = ""
    trigger: Trigger = Trigger.other

    def to_db_dict(self) -> dict:
        """Convert to dict for SQLite insertion."""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "date": self.date,
            "ticker": self.ticker.upper(),
            "decision_type": self.decision_type.value,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "conviction": self.conviction,
            "thesis_link": self.thesis_link,
            "trigger": self.trigger.value,
        }


class OutcomeRecord(BaseModel):
    """Outcome of a decision — stored in SQLite outcomes table."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    decision_id: UUID  # FK to decisions.id
    date: str  # YYYY-MM-DD when outcome was recorded
    result: OutcomeResult
    pnl: float = 0.0  # realized P&L
    pnl_pct: float = 0.0  # percentage return
    notes: str = ""

    def to_db_dict(self) -> dict:
        """Convert to dict for SQLite insertion."""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "decision_id": str(self.decision_id),
            "date": self.date,
            "result": self.result.value,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "notes": self.notes,
        }


class FailureRecord(BaseModel):
    """Investment failure/mistake — stored in failures.jsonl (append-only)."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    date: str  # YYYY-MM-DD
    ticker: str
    failure_type: FailureType
    description: str
    root_cause: str = ""
    cognitive_bias: CognitiveBias = CognitiveBias.none
    prevention: str = ""
    severity: int = Field(default=5, ge=1, le=10)
    related_decision_id: str = ""  # UUID string linking to decisions table

    def to_jsonl_dict(self) -> dict:
        """Convert to dict for JSONL serialization."""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "date": self.date,
            "ticker": self.ticker.upper(),
            "failure_type": self.failure_type.value,
            "description": self.description,
            "root_cause": self.root_cause,
            "cognitive_bias": self.cognitive_bias.value,
            "prevention": self.prevention,
            "severity": self.severity,
            "related_decision_id": self.related_decision_id,
        }


class ConsensusRecord(BaseModel):
    """Consensus snapshot — matches existing consensus_history JSONL format."""

    ticker: str
    date: str = ""
    timestamp: str = ""
    # Flexible: consensus data varies by source, so we allow extras
    eps_current: float | None = None
    eps_next: float | None = None
    revenue_current: float | None = None
    revenue_next: float | None = None
    price_target: float | None = None
    analyst_count: int | None = None
    buy_count: int | None = None
    hold_count: int | None = None
    sell_count: int | None = None

    model_config = {"extra": "allow"}

    def to_jsonl_dict(self) -> dict:
        """Convert to dict for JSONL serialization, including extras."""
        d = self.model_dump(exclude_none=True)
        d["ticker"] = d["ticker"].upper()
        return d


class PriceAlertRecord(BaseModel):
    """Price alert log — matches existing price_alerts.jsonl format."""

    ticker: str
    price: float | None = None
    direction: str = ""
    reason: str = ""
    logged_at: str = ""

    model_config = {"extra": "allow"}

    def to_jsonl_dict(self) -> dict:
        """Convert to dict for JSONL serialization, including extras."""
        d = self.model_dump(exclude_none=True)
        d["ticker"] = d["ticker"].upper()
        return d

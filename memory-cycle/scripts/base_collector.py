"""Common interface for all Memory Cycle collectors."""

from dataclasses import dataclass, field
import time
import sys
from pathlib import Path

# Allow sibling imports
sys.path.insert(0, str(Path(__file__).parent))
import memory_db as db


@dataclass
class CollectorResult:
    """Standard result from any collector run."""

    source: str
    status: str = "pending"  # 'success', 'partial', 'failed'
    rows_added: int = 0
    signals: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def log(self):
        """Log this result to the fetch_log table."""
        error_msg = "; ".join(self.errors) if self.errors else None
        db.log_fetch(
            source=self.source,
            status=self.status,
            rows_added=self.rows_added,
            error_message=error_msg,
            duration_seconds=self.duration_seconds,
        )

    def save_signals(self) -> int:
        """Save collected signals to the database. Returns rows saved."""
        if not self.signals:
            return 0
        count = db.upsert_signals_batch(self.signals)
        self.rows_added = count
        return count


class BaseCollector:
    """Base class for collectors. Subclass and implement collect()."""

    SOURCE_NAME = "unknown"

    def run(self) -> CollectorResult:
        """Execute collection with timing and error handling."""
        start = time.time()
        result = CollectorResult(source=self.SOURCE_NAME)
        try:
            self.collect(result)
            if result.errors and result.signals:
                result.status = "partial"
            elif result.errors:
                result.status = "failed"
            else:
                result.status = "success"
        except Exception as e:
            result.status = "failed"
            result.errors.append(f"Unhandled: {e}")
        finally:
            result.duration_seconds = round(time.time() - start, 2)
            result.save_signals()
            result.log()
        return result

    def collect(self, result: CollectorResult):
        """Override in subclass. Append signals to result.signals."""
        raise NotImplementedError


def make_signal(
    date: str,
    source: str,
    metric: str,
    value: float,
    unit: str = None,
    signal_group: str = None,
    sub_cycle: str = "ALL",
    metadata: str = None,
) -> dict:
    """Helper to create a signal dict matching the DB schema."""
    return {
        "date": date,
        "source": source,
        "metric": metric,
        "value": value,
        "unit": unit,
        "signal_group": signal_group,
        "sub_cycle": sub_cycle,
        "metadata": metadata,
    }

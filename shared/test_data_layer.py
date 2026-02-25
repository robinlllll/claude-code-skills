"""Integration test for the data layer: schemas + db_utils + jsonl_utils.

Tests:
1. SQLite decision CRUD + UUID generation
2. SQLite outcome with FK constraint
3. JSONL failure append with Pydantic validation
4. Pydantic rejection of malformed data
5. Concurrent JSONL writes (portalocker)
6. Cross-module query flow (decisions → outcomes → stats)
7. Chinese content round-trip in JSONL
8. Failures JSONL linked to decision UUID

Run:
    python test_data_layer.py
"""

import json
import sys
import tempfile
import threading
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_utils import (
    get_db,
    get_decision_stats,
    get_decisions_for_ticker,
    get_pending_outcomes,
    init_db,
    insert_decision,
    insert_outcome,
    query_decisions,
)
from jsonl_utils import count_jsonl, query_jsonl, read_jsonl, safe_jsonl_append
from schemas import (
    DecisionRecord,
    FailureRecord,
    OutcomeRecord,
)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} — {detail}")


def test_sqlite_crud():
    """Test 1-2: SQLite decision + outcome CRUD."""
    print("\n== SQLite CRUD ==")
    tmp = Path(tempfile.mktemp(suffix=".db"))
    conn = get_db(tmp)
    init_db(conn)

    # Insert decision
    d = DecisionRecord(
        date="2026-02-24",
        ticker="celh",  # lowercase — should be uppercased in to_db_dict
        decision_type="buy",
        reasoning="Velocity improving, Alani Nu distribution expanding",
        alternatives="Wait for next earnings",
        conviction=8,
        thesis_link="PORTFOLIO/research/companies/CELH/thesis.md",
        trigger="earnings",
    )
    did = insert_decision(d, conn=conn)
    check("Decision insert returns UUID", len(did) == 36)
    check("UUID is valid", UUID(did, version=4) is not None)

    # Query back
    results = query_decisions(ticker="CELH", conn=conn)
    check("Query by ticker finds 1 record", len(results) == 1)
    check("Ticker is uppercase", results[0]["ticker"] == "CELH")
    check("Conviction preserved", results[0]["conviction"] == 8)
    check("Trigger preserved", results[0]["trigger"] == "earnings")

    # Insert second decision (same ticker, same day)
    d2 = DecisionRecord(
        date="2026-02-24",
        ticker="CELH",
        decision_type="add",
        reasoning="Dip buy after morning sell-off",
        conviction=6,
        trigger="technical",
    )
    did2 = insert_decision(d2, conn=conn)
    check("Two decisions same day/ticker have different IDs", did != did2)
    results2 = query_decisions(ticker="CELH", conn=conn)
    check("Both decisions queryable", len(results2) == 2)

    # Insert outcome for first decision
    o = OutcomeRecord(
        decision_id=d.id,
        date="2026-03-24",
        result="win",
        pnl=500.0,
        pnl_pct=12.5,
        notes="Velocity confirmed in Q1 data",
    )
    oid = insert_outcome(o, conn=conn)
    check("Outcome insert returns UUID", len(oid) == 36)

    # Verify FK constraint — outcome for nonexistent decision
    from uuid import uuid4

    fake = OutcomeRecord(
        decision_id=uuid4(),
        date="2026-03-24",
        result="loss",
        pnl=-100.0,
    )
    try:
        insert_outcome(fake, conn=conn)
        check("FK violation rejected", False, "Should have raised ValueError")
    except ValueError:
        check("FK violation rejected", True)

    # Stats
    stats = get_decision_stats(conn=conn)
    check("Total decisions = 2", stats["total"] == 2)
    check("With outcome = 1", stats["with_outcome"] == 1)
    check("Win = 1", stats["win"] == 1)
    check("Pending = 1", stats["pending"] == 1)
    check("Avg conviction on win = 8", stats["avg_conviction_win"] == 8.0)

    # Pending outcomes
    pending = get_pending_outcomes(days=0, conn=conn)
    check("1 pending outcome", len(pending) == 1)
    check("Pending is the second decision", pending[0]["id"] == did2)

    # Timeline
    timeline = get_decisions_for_ticker("CELH", conn=conn)
    check("Timeline has 2 entries", len(timeline) == 2)
    check(
        "First entry has outcome",
        timeline[0]["outcome_result"] == "win",
    )
    check(
        "Second entry has no outcome",
        timeline[1]["outcome_result"] is None,
    )

    conn.close()
    tmp.unlink()


def test_jsonl_failures():
    """Test 3: JSONL failure append with Pydantic validation."""
    print("\n== JSONL Failures ==")
    tmp = Path(tempfile.mktemp(suffix=".jsonl"))

    # Append valid failure
    f = FailureRecord(
        date="2026-02-20",
        ticker="NVDA",
        failure_type="追涨",
        description="Chased momentum after 10% run-up",
        root_cause="FOMO triggered by peer discussion",
        cognitive_bias="herd",
        severity=7,
        related_decision_id="abc-123",
    )
    safe_jsonl_append(tmp, f, model_class=FailureRecord)
    check("Failure appended", count_jsonl(tmp) == 1)

    # Read back and verify Chinese content
    content = tmp.read_text(encoding="utf-8")
    check("Chinese failure_type preserved", "追涨" in content)
    check("Chinese description preserved", "Chased momentum" in content)

    records = read_jsonl(tmp)
    check("Failure has UUID", len(records[0]["id"]) == 36)
    check("Failure has created_at", "T" in records[0]["created_at"])
    check("Ticker uppercased", records[0]["ticker"] == "NVDA")

    # Query by Chinese field
    results = query_jsonl(tmp, failure_type="追涨")
    check("Query by Chinese enum", len(results) == 1)

    tmp.unlink()


def test_pydantic_rejection():
    """Test 4: Pydantic rejects malformed data."""
    print("\n== Pydantic Rejection ==")
    tmp = Path(tempfile.mktemp(suffix=".jsonl"))

    # Invalid conviction (out of range)
    try:
        DecisionRecord(
            date="2026-02-24",
            ticker="X",
            decision_type="buy",
            reasoning="test",
            conviction=15,
        )
        check("Conviction > 10 rejected", False, "Should have raised")
    except Exception:
        check("Conviction > 10 rejected", True)

    # Invalid failure_type enum
    try:
        safe_jsonl_append(
            tmp,
            {
                "date": "2026-02-20",
                "ticker": "X",
                "failure_type": "NONEXISTENT",
                "description": "bad",
            },
            model_class=FailureRecord,
        )
        check("Invalid failure_type rejected", False, "Should have raised")
    except (ValueError, Exception):
        check("Invalid failure_type rejected", True)

    # Missing required field
    try:
        safe_jsonl_append(
            tmp,
            {"date": "2026-02-20", "ticker": "X"},
            model_class=FailureRecord,
        )
        check("Missing required field rejected", False, "Should have raised")
    except (ValueError, Exception):
        check("Missing required field rejected", True)

    # File should still be empty (all appends failed)
    check("No garbage written on rejection", count_jsonl(tmp) == 0)
    if tmp.exists():
        tmp.unlink()


def test_concurrent_writes():
    """Test 5: Concurrent JSONL writes with portalocker."""
    print("\n== Concurrent Writes ==")
    tmp = Path(tempfile.mktemp(suffix=".jsonl"))
    n_threads = 10
    n_writes = 20
    errors = []

    def writer(thread_id):
        for i in range(n_writes):
            try:
                safe_jsonl_append(
                    tmp,
                    {"thread": thread_id, "seq": i, "data": "x" * 100},
                )
            except Exception as e:
                errors.append(f"Thread {thread_id}, seq {i}: {e}")

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = n_threads * n_writes
    actual = count_jsonl(tmp)
    check(f"All {expected} writes landed", actual == expected, f"got {actual}")
    check("No write errors", len(errors) == 0, str(errors[:3]))

    # Verify every line is valid JSON
    bad_lines = 0
    with open(tmp, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
    check("All lines are valid JSON", bad_lines == 0, f"{bad_lines} bad lines")

    tmp.unlink()


def test_cross_module_flow():
    """Test 6: Full flow — decision → failure with linked UUID."""
    print("\n== Cross-Module Flow ==")
    tmp_db = Path(tempfile.mktemp(suffix=".db"))
    tmp_jsonl = Path(tempfile.mktemp(suffix=".jsonl"))

    conn = get_db(tmp_db)
    init_db(conn)

    # Step 1: Record a decision
    d = DecisionRecord(
        date="2026-01-15",
        ticker="BABA",
        decision_type="buy",
        reasoning="Valuation attractive post-earnings",
        conviction=7,
        trigger="valuation",
    )
    did = insert_decision(d, conn=conn)

    # Step 2: Later, record a failure linked to that decision
    f = FailureRecord(
        date="2026-02-15",
        ticker="BABA",
        failure_type="时机错误",
        description="Bought before regulatory announcement",
        root_cause="Did not check policy calendar",
        cognitive_bias="overconfidence",
        severity=6,
        related_decision_id=did,
    )
    safe_jsonl_append(tmp_jsonl, f, model_class=FailureRecord)

    # Step 3: Verify linkage
    failures = query_jsonl(tmp_jsonl, ticker="BABA")
    check("Failure linked to decision UUID", failures[0]["related_decision_id"] == did)

    # Step 4: Can look up the decision from the failure
    decisions = query_decisions(ticker="BABA", conn=conn)
    check("Decision found from failure link", decisions[0]["id"] == did)

    conn.close()
    tmp_db.unlink()
    tmp_jsonl.unlink()


if __name__ == "__main__":
    print("=" * 60)
    print("Context Engineering Data Layer — Integration Tests")
    print("=" * 60)

    test_sqlite_crud()
    test_jsonl_failures()
    test_pydantic_rejection()
    test_concurrent_writes()
    test_cross_module_flow()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed out of {PASS + FAIL} checks")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)

#!/usr/bin/env python3
"""
Claims Ledger - Track and manage claims/assertions in writing.
Each claim has status: unverified | supported | disputed | abandoned
Research results link back to claims they support or challenge.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).parent.parent))

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from session import load_session, get_session_path, save_session

CLAIM_STATUSES = {
    "unverified": "⏳ 待验证",
    "supported": "✓ 已支持",
    "disputed": "⚡ 有争议",
    "abandoned": "✗ 已放弃"
}


def load_claims(session_id: str) -> dict:
    """Load claims ledger for a session."""
    session_path = get_session_path(session_id)
    claims_file = session_path / "claims.json"

    if not claims_file.exists():
        return {"claims": [], "next_id": 1}

    with open(claims_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_claims(session_id: str, claims_data: dict):
    """Save claims ledger."""
    session_path = get_session_path(session_id)
    claims_file = session_path / "claims.json"

    claims_data["updated_at"] = datetime.now().isoformat()

    with open(claims_file, "w", encoding="utf-8") as f:
        json.dump(claims_data, f, indent=2, ensure_ascii=False)


def cmd_add(session_id: str, text: str, source: str = "user"):
    """Add a new claim to the ledger."""
    claims_data = load_claims(session_id)

    claim = {
        "id": f"C{claims_data['next_id']}",
        "text": text,
        "status": "unverified",
        "source": source,  # user | dialogue | ai_extracted
        "created_at": datetime.now().isoformat(),
        "evidence": [],  # List of {type: support|dispute, source_id, text}
        "notes": []
    }

    claims_data["claims"].append(claim)
    claims_data["next_id"] += 1

    save_claims(session_id, claims_data)

    print(f"✓ Added claim {claim['id']}: {text[:60]}...")
    return claim["id"]


def cmd_list(session_id: str, status: str = None):
    """List all claims, optionally filtered by status."""
    claims_data = load_claims(session_id)
    claims = claims_data.get("claims", [])

    if not claims:
        print("No claims in ledger yet.")
        print("Add claims with: claims.py add --session ID --text 'Your claim'")
        return

    if status:
        claims = [c for c in claims if c["status"] == status]

    print(f"\n{'ID':<6} {'Status':<12} {'Evidence':<10} {'Claim':<60}")
    print("-" * 90)

    for c in claims:
        status_display = CLAIM_STATUSES.get(c["status"], c["status"])
        evidence_count = len(c.get("evidence", []))
        supports = len([e for e in c.get("evidence", []) if e["type"] == "support"])
        disputes = len([e for e in c.get("evidence", []) if e["type"] == "dispute"])
        evidence_str = f"+{supports}/-{disputes}" if evidence_count else "-"

        text = c["text"][:58] + "..." if len(c["text"]) > 58 else c["text"]
        print(f"{c['id']:<6} {status_display:<12} {evidence_str:<10} {text:<60}")

    # Summary
    print("\n" + "-" * 90)
    total = len(claims_data.get("claims", []))
    by_status = {}
    for c in claims_data.get("claims", []):
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1

    print(f"Total: {total} claims")
    for s, count in by_status.items():
        print(f"  {CLAIM_STATUSES.get(s, s)}: {count}")


def cmd_update(session_id: str, claim_id: str, status: str = None, note: str = None):
    """Update a claim's status or add a note."""
    claims_data = load_claims(session_id)

    claim = None
    for c in claims_data["claims"]:
        if c["id"] == claim_id:
            claim = c
            break

    if not claim:
        print(f"Claim not found: {claim_id}")
        return

    if status:
        if status not in CLAIM_STATUSES:
            print(f"Invalid status. Choose from: {', '.join(CLAIM_STATUSES.keys())}")
            return
        old_status = claim["status"]
        claim["status"] = status
        print(f"✓ {claim_id}: {CLAIM_STATUSES[old_status]} → {CLAIM_STATUSES[status]}")

    if note:
        claim["notes"].append({
            "text": note,
            "timestamp": datetime.now().isoformat()
        })
        print(f"✓ Added note to {claim_id}")

    save_claims(session_id, claims_data)


def cmd_link_evidence(session_id: str, claim_id: str, evidence_type: str,
                       source_id: str, text: str):
    """Link research evidence to a claim."""
    if evidence_type not in ["support", "dispute"]:
        print("Evidence type must be 'support' or 'dispute'")
        return

    claims_data = load_claims(session_id)

    claim = None
    for c in claims_data["claims"]:
        if c["id"] == claim_id:
            claim = c
            break

    if not claim:
        print(f"Claim not found: {claim_id}")
        return

    evidence = {
        "type": evidence_type,
        "source_id": source_id,
        "text": text,
        "added_at": datetime.now().isoformat()
    }
    claim["evidence"].append(evidence)

    # Auto-update status based on evidence
    supports = len([e for e in claim["evidence"] if e["type"] == "support"])
    disputes = len([e for e in claim["evidence"] if e["type"] == "dispute"])

    if disputes > 0 and supports > 0:
        claim["status"] = "disputed"
    elif supports > 0 and disputes == 0:
        claim["status"] = "supported"

    save_claims(session_id, claims_data)

    print(f"✓ Linked {evidence_type} evidence to {claim_id}")
    print(f"  Status now: {CLAIM_STATUSES[claim['status']]}")


def cmd_show(session_id: str, claim_id: str):
    """Show detailed view of a single claim."""
    claims_data = load_claims(session_id)

    claim = None
    for c in claims_data["claims"]:
        if c["id"] == claim_id:
            claim = c
            break

    if not claim:
        print(f"Claim not found: {claim_id}")
        return

    print("=" * 70)
    print(f"Claim: {claim['id']}")
    print("=" * 70)
    print(f"Text: {claim['text']}")
    print(f"Status: {CLAIM_STATUSES[claim['status']]}")
    print(f"Source: {claim['source']}")
    print(f"Created: {claim['created_at'][:16]}")

    if claim.get("evidence"):
        print("\nEvidence:")
        for i, e in enumerate(claim["evidence"], 1):
            icon = "✓" if e["type"] == "support" else "✗"
            print(f"  {icon} [{e['source_id']}] {e['text'][:60]}...")

    if claim.get("notes"):
        print("\nNotes:")
        for n in claim["notes"]:
            print(f"  • {n['text']} ({n['timestamp'][:10]})")


def cmd_extract(session_id: str):
    """Extract claims from dialogue automatically (Claude should call this)."""
    session_path = get_session_path(session_id)
    dialogue_file = session_path / "dialogue.json"

    if not dialogue_file.exists():
        print("No dialogue found.")
        return

    with open(dialogue_file, "r", encoding="utf-8") as f:
        dialogue = json.load(f)

    print("Analyzing dialogue for claims...")
    print("(In practice, Claude should analyze answers and call 'claims.py add' for each claim)")
    print()

    # Show dialogue entries that likely contain claims
    for entry in dialogue.get("entries", []):
        answer = entry.get("answer", "")
        if len(answer) > 50:  # Substantial answers likely contain claims
            print(f"Potential claim in answer to '{entry.get('type', '')}' question:")
            print(f"  \"{answer[:100]}...\"")
            print()


def main():
    if len(sys.argv) < 2:
        print("Claims Ledger - Track assertions and their evidence")
        print()
        print("Usage:")
        print("  claims.py add --session ID --text 'claim'  - Add a claim")
        print("  claims.py list --session ID [--status X]   - List claims")
        print("  claims.py show --session ID --id CX        - Show claim details")
        print("  claims.py update --session ID --id CX --status X  - Update status")
        print("  claims.py link --session ID --id CX --type support|dispute --source SX --text '...'")
        print("  claims.py extract --session ID             - Extract claims from dialogue")
        print()
        print("Statuses: unverified, supported, disputed, abandoned")
        return

    command = sys.argv[1]

    # Parse arguments
    session_id = claim_id = text = status = source_id = evidence_type = note = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]
        if arg == "--id" and i + 1 < len(sys.argv):
            claim_id = sys.argv[i + 1]
        if arg == "--text" and i + 1 < len(sys.argv):
            text = sys.argv[i + 1]
        if arg == "--status" and i + 1 < len(sys.argv):
            status = sys.argv[i + 1]
        if arg == "--source" and i + 1 < len(sys.argv):
            source_id = sys.argv[i + 1]
        if arg == "--type" and i + 1 < len(sys.argv):
            evidence_type = sys.argv[i + 1]
        if arg == "--note" and i + 1 < len(sys.argv):
            note = sys.argv[i + 1]

    if not session_id and command != "help":
        print("Error: --session is required")
        return

    if command == "add":
        if not text:
            print("Error: --text is required")
            return
        cmd_add(session_id, text)

    elif command == "list":
        cmd_list(session_id, status)

    elif command == "show":
        if not claim_id:
            print("Error: --id is required")
            return
        cmd_show(session_id, claim_id)

    elif command == "update":
        if not claim_id:
            print("Error: --id is required")
            return
        cmd_update(session_id, claim_id, status, note)

    elif command == "link":
        if not all([claim_id, evidence_type, source_id, text]):
            print("Error: --id, --type, --source, --text are all required")
            return
        cmd_link_evidence(session_id, claim_id, evidence_type, source_id, text)

    elif command == "extract":
        cmd_extract(session_id)

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()

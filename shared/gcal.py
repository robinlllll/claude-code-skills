"""Google Calendar API integration.

First-time setup:
    1. Enable Calendar API in Google Cloud Console
    2. Create OAuth client ID (Desktop app)
    3. Download credentials.json → shared/data/credentials.json
    4. Run: python gcal.py auth
       (opens browser for OAuth, saves token.json)

Usage:
    python gcal.py auth              # First-time OAuth flow
    python gcal.py events 2026-02-23 2026-03-01  # List events in date range
    python gcal.py test              # Quick connectivity test
"""

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).parent / "data"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
TOKEN_FILE = DATA_DIR / "gcal_token.json"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_credentials():
    """Load or refresh Google OAuth credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_FILE}\n"
                    "Download from Google Cloud Console → Credentials → OAuth client ID → Desktop app"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _build_service():
    """Build Calendar API service."""
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=_get_credentials())


def list_events(
    start_date: str, end_date: str, calendar_id: str = "primary"
) -> list[dict]:
    """Fetch events from Google Calendar.

    Args:
        start_date: YYYY-MM-DD (inclusive)
        end_date: YYYY-MM-DD (inclusive)
        calendar_id: Calendar ID (default: primary)

    Returns:
        List of event dicts with keys: date, time, end_time, summary, description, all_day
    """
    service = _build_service()

    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"

    results = []
    page_token = None

    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=250,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        for item in resp.get("items", []):
            start = item.get("start", {})
            end = item.get("end", {})

            if "date" in start:
                # All-day event
                event = {
                    "date": start["date"],
                    "time": "ALL_DAY",
                    "end_time": None,
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "all_day": True,
                }
            else:
                # Timed event
                dt_start = datetime.fromisoformat(start["dateTime"])
                dt_end = datetime.fromisoformat(end.get("dateTime", start["dateTime"]))
                event = {
                    "date": dt_start.strftime("%Y-%m-%d"),
                    "time": dt_start.strftime("%H:%M"),
                    "end_time": dt_end.strftime("%H:%M"),
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "all_day": False,
                }

            results.append(event)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def list_events_grouped(
    start_date: str, end_date: str, calendar_id: str = "primary"
) -> dict[str, list]:
    """Fetch events grouped by date, matching week_planner format.

    Returns: {'YYYY-MM-DD': [{'time': 'HH:MM', 'summary': '...', 'category': '...', 'ticker': '...'}]}
    """
    import re

    events = list_events(start_date, end_date, calendar_id)
    grouped: dict[str, list] = {}

    for ev in events:
        ds = ev["date"]
        summary = ev["summary"]

        # Try to extract category from [Category] prefix
        category = ""
        m = re.match(r"\[([^\]]+)\]\s*", summary)
        if m:
            category = m.group(1)

        # Try to extract ticker from summary
        ticker = None
        m_ticker = re.search(r"\b([A-Z]{1,5})(?:-(?:US|HK|CN))?\b", summary)
        if m_ticker and m_ticker.group(1) not in {
            "ALL",
            "DAY",
            "TBD",
            "AM",
            "PM",
            "CEO",
            "CFO",
            "COO",
            "CTO",
            "IPO",
            "ETF",
            "SEC",
            "GDP",
            "CPI",
            "PPI",
            "FOMC",
            "FED",
        }:
            ticker = m_ticker.group(1)

        entry = {
            "time": ev["time"],
            "summary": summary,
            "category": category,
        }
        if ticker:
            entry["ticker"] = ticker
        if ev.get("end_time"):
            entry["end_time"] = ev["end_time"]

        grouped.setdefault(ds, []).append(entry)

    # Sort each day by time
    for ds in grouped:
        grouped[ds] = sorted(grouped[ds], key=lambda e: e.get("time") or "99:99")

    return grouped


def clear_schedule_events(
    start_date: str, end_date: str, calendar_id: str = "primary", prefix: str = "[W09]"
) -> int:
    """Delete events with a specific prefix in the given date range.

    Returns number of deleted events.
    """
    service = _build_service()
    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"
    deleted = 0
    page_token = None

    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=250,
                singleEvents=True,
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("items", []):
            summary = item.get("summary", "")
            if summary.startswith(prefix):
                service.events().delete(
                    calendarId=calendar_id, eventId=item["id"]
                ).execute()
                deleted += 1

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return deleted


def create_event(
    date_str: str,
    start_time: str,
    end_time: str,
    summary: str,
    description: str = "",
    calendar_id: str = "primary",
    color_id: str | None = None,
    reminders: list[dict] | None = None,
) -> dict:
    """Create a single calendar event.

    Args:
        date_str: YYYY-MM-DD
        start_time: HH:MM
        end_time: HH:MM
        summary: Event title
        description: Event description
        calendar_id: Calendar ID
        color_id: Google Calendar color ID (1-11)
        reminders: List of reminder overrides

    Returns:
        Created event dict from API
    """
    service = _build_service()
    tz = "America/New_York"

    body = {
        "summary": summary,
        "start": {"dateTime": f"{date_str}T{start_time}:00", "timeZone": tz},
        "end": {"dateTime": f"{date_str}T{end_time}:00", "timeZone": tz},
    }
    if description:
        body["description"] = description
    if color_id:
        body["colorId"] = color_id
    if reminders:
        body["reminders"] = {"useDefault": False, "overrides": reminders}
    else:
        body["reminders"] = {"useDefault": False, "overrides": []}

    return service.events().insert(calendarId=calendar_id, body=body).execute()


def sync_schedule(
    schedule_data: dict,
    week_prefix: str = "[W09]",
    calendar_id: str = "primary",
) -> dict:
    """Sync a week schedule to Google Calendar.

    1. Deletes existing events with the week prefix
    2. Creates new events for all task blocks + PE/REST/EXERCISE

    Args:
        schedule_data: Dict with 'schedule' key containing {date: [blocks]}
        week_prefix: Prefix for event titles (for idempotent sync)
        calendar_id: Target calendar

    Returns:
        Stats dict {created, deleted, errors}
    """
    import time as _time

    schedule = schedule_data["schedule"]
    dates = sorted(schedule.keys())
    if not dates:
        return {"created": 0, "deleted": 0, "errors": []}

    start_date = dates[0]
    end_date = dates[-1]

    # Step 1: Clear old events with this prefix
    deleted = clear_schedule_events(start_date, end_date, calendar_id, week_prefix)

    # Color mapping: P1=Tomato(11), P2=Banana(5), P3=Sage(2), PE=Blueberry(9), REST=Basil(10), EXERCISE=Grape(3)
    priority_colors = {1: "11", 2: "5", 3: "2"}

    created = 0
    errors = []
    service = _build_service()
    tz = "America/New_York"

    # Batch using service
    for date_str in dates:
        blocks = schedule[date_str]

        for b in blocks:
            title = f"{week_prefix} #{b['task_id']} {b['title']}"
            pri = b.get("priority", 2)
            color = priority_colors.get(pri, "5")
            desc = f"Priority: P{pri}\nCategory: {b.get('category', '')}\nDuration: {b['duration_minutes']}m"
            if b.get("ticker"):
                desc += f"\nTicker: {b['ticker']}"

            body = {
                "summary": title,
                "description": desc,
                "start": {"dateTime": f"{date_str}T{b['start']}:00", "timeZone": tz},
                "end": {"dateTime": f"{date_str}T{b['end']}:00", "timeZone": tz},
                "colorId": color,
                "reminders": {"useDefault": False, "overrides": []},
            }
            try:
                service.events().insert(calendarId=calendar_id, body=body).execute()
                created += 1
            except Exception as e:
                errors.append(f"#{b['task_id']}: {e}")
            _time.sleep(0.05)  # Rate limit

        # Add PE block (12:35-12:55)
        body = {
            "summary": f"{week_prefix} PE Session",
            "start": {"dateTime": f"{date_str}T12:35:00", "timeZone": tz},
            "end": {"dateTime": f"{date_str}T12:55:00", "timeZone": tz},
            "colorId": "9",
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 5}],
            },
        }
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            created += 1
        except Exception as e:
            errors.append(f"PE {date_str}: {e}")

        # Add REST block (18:00-18:30)
        body = {
            "summary": f"{week_prefix} REST",
            "start": {"dateTime": f"{date_str}T18:00:00", "timeZone": tz},
            "end": {"dateTime": f"{date_str}T18:30:00", "timeZone": tz},
            "colorId": "10",
            "reminders": {"useDefault": False, "overrides": []},
        }
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            created += 1
        except Exception as e:
            errors.append(f"REST {date_str}: {e}")

        # Add EXERCISE block (22:00-23:00)
        body = {
            "summary": f"{week_prefix} EXERCISE",
            "start": {"dateTime": f"{date_str}T22:00:00", "timeZone": tz},
            "end": {"dateTime": f"{date_str}T23:00:00", "timeZone": tz},
            "colorId": "3",
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 10}],
            },
        }
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            created += 1
        except Exception as e:
            errors.append(f"EXERCISE {date_str}: {e}")

        _time.sleep(0.1)

    return {"created": created, "deleted": deleted, "errors": errors}


def is_authenticated() -> bool:
    """Check if we have valid credentials without triggering OAuth flow."""
    if not TOKEN_FILE.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            return True
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google Calendar integration")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("auth", help="Run OAuth flow (first-time setup)")

    ev_parser = sub.add_parser("events", help="List events in date range")
    ev_parser.add_argument("start_date", help="YYYY-MM-DD")
    ev_parser.add_argument("end_date", help="YYYY-MM-DD")
    ev_parser.add_argument("--calendar-id", default="primary")
    ev_parser.add_argument("--grouped", action="store_true", help="Group by date")

    sub.add_parser("test", help="Test connectivity")

    args = parser.parse_args()

    if args.command == "auth":
        print("Starting OAuth flow...")
        _get_credentials()
        print(f"Authenticated. Token saved to {TOKEN_FILE}")

    elif args.command == "events":
        if args.grouped:
            data = list_events_grouped(args.start_date, args.end_date, args.calendar_id)
        else:
            data = list_events(args.start_date, args.end_date, args.calendar_id)
        print(json.dumps(data, ensure_ascii=False, indent=2))

    elif args.command == "test":
        if is_authenticated():
            # Fetch today's events as test
            today = date.today().isoformat()
            events = list_events(today, today)
            print(f"OK — {len(events)} event(s) today")
        else:
            print("Not authenticated. Run: python gcal.py auth")

    else:
        parser.print_help()

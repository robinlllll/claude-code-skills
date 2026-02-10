---
name: calendar
description: Financial Events Calendar Converter - Convert events to iPhone-compatible .ics calendar files
---

# Financial Events Calendar Converter

Converts financial events from screenshots into iPhone-compatible .ics calendar files. Includes earnings calls, conferences, shareholder meetings.

## Project Location

`C:\Users\thisi\CALENDAR-CONVERTER`

## When to Use This Skill

- User wants to create calendar files
- User mentions earnings calendar, financial events
- User wants to convert events to .ics format
- User mentions iPhone/Outlook calendar import

## Key Files

- `generate_calendar*.py` - Scripts with embedded event data
- `*.ics` - Generated calendar files

## Commands

### Generate Calendar
```bash
cd "C:\Users\thisi\CALENDAR-CONVERTER" && python generate_calendar.py
```

### List Available Scripts
```bash
ls "C:\Users\thisi\CALENDAR-CONVERTER"\generate_calendar*.py
```

## Output

`.ics` files to import to iPhone/Outlook calendars.

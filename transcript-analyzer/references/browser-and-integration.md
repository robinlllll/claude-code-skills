# Browser & Integration Reference

## Browser Features

| Feature | Description |
|---------|-------------|
| Company Search | Search by ticker or name |
| Recently Added | New transcripts appear first with green badge |
| Company Notes | Save background notes per company |
| Follow-up Questions | Track questions for next quarter's analysis |
| Analysis History | Store AI responses and your comments |
| Quick Select | "Latest 2 Quarters" or "All Earnings" buttons |
| Direct AI Analysis | Gemini 2.5 Pro button (1-2 min) |
| Obsidian Save | Auto-saves to `研究/财报分析/{TICKER}/` |
| Open in Obsidian | Click to open analysis in Obsidian app |

## Email Delivery

Earnings analyses can be emailed after saving to Obsidian:

- **Browser API**: POST to `/api/analysis/{ticker}` with `send_email: true` and optional `email_to` field
- **Claude Code**: After analysis, call `save_and_email_analysis()` from `obsidian.py` with `email_to=""` (default recipients) or `email_to="alice@example.com"`
- **Markdown -> HTML**: Auto-converted with table/code formatting, frontmatter stripped
- **Attachments**: Original .md file attached automatically

Requires `EMAIL_USER` and `EMAIL_APP_PASSWORD` in `~/Screenshots/.env`.

## Obsidian Integration

Analyses are saved to:
```
C:\Users\thisi\Documents\Obsidian Vault\研究\财报分析\
├── {TICKER}/
│   ├── 2026-02-04 1630 TICKER Q2 2026 vs Q4 2025 Analysis.md
│   └── _TICKER Notes.md
└── _Peer Comparisons/
    └── 2026-02-11 1630 GOOG vs META vs AMZN Q4 2025 Peer Analysis.md
```

Each analysis file includes:
- YAML frontmatter with tags
- AI analysis content
- User comments
- Follow-up questions (auto-extracted)
- Source transcript references

## API Configuration

API keys in `browser/.env`:
```
GOOGLE_API_KEY=...  # For Gemini (configured)
ANTHROPIC_API_KEY=... # For Claude API (optional)
```

**Note:** Claude analysis via Claude Code doesn't need an API key!

## Input Patterns

Transcript PDFs in Downloads matching patterns:
- `CORRECTED TRANSCRIPT_*.pdf`
- `TRANSCRIPT_*.pdf`
- `CALLSTREET REPORT_*.pdf`
- `*earnings call*.pdf`

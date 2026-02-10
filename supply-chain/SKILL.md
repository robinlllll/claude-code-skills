---
name: supply-chain
description: Supply Chain Cross-Reference - Extract and index company mentions from earnings transcripts to map supply chain relationships
---

# Supply Chain Cross-Reference

Extracts company-to-company mentions from earnings call transcripts, building a mention index that maps who talks about whom. v0 scope: mention index only (who mentions whom + verbatim quote). No relationship classification yet.

## Project Location

`C:\Users\thisi\.claude\skills\supply-chain`

## When to Use This Skill

- User says `/supply-chain TICKER` — show all mentions of/by a ticker
- User says `/supply-chain scan` — process new earnings transcripts
- User says `/supply-chain stats` — show database statistics
- User asks about supply chain relationships or company mentions
- User wants to know which companies mention a specific ticker

## Commands

### `/supply-chain TICKER`

Show all mentions of a company across earnings transcripts.

**What it does:**
1. Queries the mention database for the given ticker
2. Shows two tables: "Mentioned By" (who talks about TICKER) and "Mentions" (who TICKER talks about)
3. Includes verbatim quotes and speaker roles

**Execution:**
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/supply-chain/mention_extractor.py" query TICKER
```

### `/supply-chain scan`

Process all new (unprocessed) earnings transcripts.

**What it does:**
1. Scans `Downloads/Earnings Transcripts/` for all PDF files
2. Skips already-processed transcripts
3. Extracts text with pdfplumber, chunks by speaker turn
4. Calls Gemini 2.0 Flash to extract company mentions
5. Resolves entities via shared dictionary
6. Stores in SQLite with verbatim quotes

**Execution:**
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/supply-chain/mention_extractor.py" scan
```

### `/supply-chain stats`

Show database statistics: total mentions, transcripts processed, top mentioned companies.

**Execution:**
```bash
/c/Users/thisi/AppData/Local/Python/pythoncore-3.14-64/python.exe "C:/Users/thisi/.claude/skills/supply-chain/mention_extractor.py" stats
```

## Key Files

| File | Purpose |
|------|---------|
| `supply_chain_db.py` | SQLite database layer (schema, CRUD) |
| `mention_extractor.py` | Core pipeline: PDF -> chunks -> Gemini -> mentions |
| `supply_chain_obsidian.py` | Generate Obsidian notes from mention database |
| `data/supply_chain.db` | SQLite database (auto-created) |

## Architecture

```
Downloads/Earnings Transcripts/
    └── {Company} ({Ticker})/
        └── *.pdf
              │
              ▼
    mention_extractor.py
    ├── pdfplumber (text extraction)
    ├── chunk_by_speaker (speaker turns, ~2000 tokens)
    ├── Gemini 2.0 Flash (mention extraction)
    └── entity_resolver (dictionary lookup)
              │
              ▼
    supply_chain_db.py
    └── data/supply_chain.db
              │
              ▼
    supply_chain_obsidian.py
    └── Obsidian Vault/Supply Chain/{TICKER}_mentions.md
```

## Dependencies

- `pdfplumber` — PDF text extraction
- `google-genai` — Gemini API (new SDK)
- `python-dotenv` — Load API keys
- Shared: `entity_resolver.py`, `entity_dictionary.yaml`

## v0 Scope (Mention Index)

**Included:**
- Extract explicit company name mentions from transcripts
- Verbatim quote context for each mention
- Speaker role (CEO/CFO/analyst/other)
- Entity resolution via dictionary
- Obsidian note generation with mention tables

**Not yet included (future versions):**
- Relationship classification (supplier/customer/competitor/partner)
- Sentiment analysis of mentions
- Time-series tracking of mention frequency
- Automatic entity dictionary expansion
- Cross-reference with 13F holdings data

## Output

- **Database:** `C:\Users\thisi\.claude\skills\supply-chain\data\supply_chain.db`
- **Obsidian notes:** `C:\Users\thisi\Documents\Obsidian Vault\Supply Chain\{TICKER}_mentions.md`

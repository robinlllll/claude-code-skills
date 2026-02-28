# Peer Comparison Reference

## When to Use This Skill (Peer Comparison)

- User wants to compare multiple companies' earnings: "比较 GOOG、META、AMZN"
- User mentions "peer comparison" or "同行对比"
- User says "compare [TICKER1] and [TICKER2]"

## What It Does — Peer Comparison (Cross-Company Analysis)

Compare 2-4 companies' earnings in the same quarter:
```
/transcript-analyzer peer GOOG META AMZN Q4 2025
```
Or with custom focus:
```
/transcript-analyzer peer HOOD SOFI Q4 2025 focus:crypto revenue mix
```

**Peer comparison workflow:**
1. Parse tickers and quarter from user input
2. Find each company's transcript PDF in `Downloads/Earnings Transcripts/`
3. Read all PDFs (max 4 companies due to context limits)
4. Apply peer comparison prompt template (`prompts/prompt_peer.py`)
5. Generate 6-dimension cross-company analysis
6. Auto-save to Obsidian: `研究/财报分析/_Peer Comparisons/`

**6 comparison dimensions:**
1. Competitive Landscape — who's winning market share
2. Growth Quality — organic vs acquired, sustainability
3. Profitability & Capital Efficiency — margins, FCF, ROIC
4. Management Narrative Divergence — same topic, different answers
5. Analyst Focus Cross-Check — shared questions, different quality
6. Investment Implications — "buy only one" thesis, pair trades

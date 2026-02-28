# Data Sources (12 Sources)

Scan all sources in parallel for the given date range.

## 1. Portfolio / Trades
- Read `~/PORTFOLIO/portfolio_monitor/data/trades.json`
- Or query `portfolio.db` (SQLite, via Python)
- Extract: new positions, additions, reductions, exits

## 2. Research Notes
- Scan `研究/研究笔记/` for files with dates in range
- Format: `{TICKER}_YYYY-MM-DD.md`

## 3. Earnings Analysis
- Scan `研究/财报分析/` for files with dates in range
- Check date in filename

## 4. Thesis Updates
- Check `~/PORTFOLIO/portfolio_monitor/research/companies/*/thesis.md`
- Filter by file modification time

## 5. 周会 (Weekly Meetings)
- Scan `周会/会议实录 YYYY-MM-DD.md` with dates in range
- Read first 10 lines (contains meeting summary and mentioned companies)

## 6. 收件箱
- Count new inbox entries within range
- Count `processed: true` vs `processed: false`
- Extract high-frequency tickers

## 7. Podcast
- Scan `信息源/播客/` for `publish_date` within range
- Count processed vs unprocessed

## 8. 13F Institutional Holdings (emphasize in quarterly reviews)
- Scan `~/Documents/Obsidian Vault/研究/13F 持仓/` for analysis reports
- Also check `~/13F-CLAUDE/output/*/` for CSV data
- Filter by held tickers: which institutions increased/decreased positions in your stocks
- Format as "Smart Money Activity" table

## 9. Supply Chain Mentions
- Scan `~/Documents/Obsidian Vault/研究/供应链/` for mention reports
- Also query `~/.claude/skills/supply-chain/data/supply_chain.db`:
  `SELECT * FROM mentions WHERE date >= '{start_date}' ORDER BY date`
- Summarize: new supply chain mentions this period (who mentioned what company in earnings)

## 10. ChatGPT Investment Conversations
- Scan `~/Documents/Obsidian Vault/ChatGPT/Investment Research/` for files with dates in range
- Extract ticker-related analysis discussions

## 11. NotebookLM Q&A Activity
- Read `~/.claude/skills/notebooklm/data/history.json`
- Count queries within range and tickers involved
- Summarize key Q&A (what was asked, what was answered)

## 12. Source Attribution (Research ROI)
- Call `shared/attribution_report.py` to generate attribution report
- Extract Source Efficiency Ranking + Conviction Calibration + Coverage vs Returns
- Show "which source made the most money", "does high conviction really earn more", "does deeper research mean better returns"

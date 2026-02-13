# Lessons Learned

## 2026-02-10 | Put/Call options were being merged with common stock in _merge_holdings(), causing AGIO Put (9M) to be conflated with AGIO stock (5M) as a single bullish position. Fixed by grouping on (issuer, cusip6, put_call) and adding OPTIONS ALERT section in format_notable_changes(). Always verify put_call field — a large put alongside stock = hedged/bearish, not conviction increase.

## 2026-02-12 | Synthesis prompt quality: When hardcoding a prompt from a prototype/testing session, ALWAYS audit it for production completeness. The original synthesis prompt used "消除冗余", "一段话概括", "3-5条" — all instructions that cause massive compression (16K+12K inputs → 3.7K output). Fixed by rewriting to explicitly require "全量合并不是摘要", "输出至少和较长分析同等详尽", expanding from 8 brief sections to 11 detailed sections. Rule: prototype prompts ≠ production prompts.

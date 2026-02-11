# Lessons Learned

## 2026-02-10 | Put/Call options were being merged with common stock in _merge_holdings(), causing AGIO Put (9M) to be conflated with AGIO stock (5M) as a single bullish position. Fixed by grouping on (issuer, cusip6, put_call) and adding OPTIONS ALERT section in format_notable_changes(). Always verify put_call field — a large put alongside stock = hedged/bearish, not conviction increase.

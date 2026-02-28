# Trade Log Template

```markdown
# Trade: {ACTION} {TICKER}

| Field | Value |
|-------|-------|
| Date | {YYYY-MM-DD HH:MM} |
| Action | {ACTION} |
| Ticker | {TICKER} |
| Qty | {QTY} |
| Price | ${PRICE} |
| Total | ${TOTAL} |
| % of NAV | {PCT}% |

## Position After Trade
- Shares: {NEW_SHARES}
- Avg Cost: ${AVG_COST}
- % of NAV: {POSITION_PCT}%

## Rationale
{REASON from command}

## Thesis Link
[{TICKER} Thesis](../../research/companies/{TICKER}/thesis.md)

## Risk (fill manually)
- Stop: $___
- Target: $___

---
*Logged via /trade command*
```

## Key Calculations

**Trade Total:**
```
total = qty * price
```

**Position % of NAV:**
```
pct_nav = (total_shares * current_price) / nav * 100
```

**New Average Cost (for ADD/BUY):**
```
new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
```

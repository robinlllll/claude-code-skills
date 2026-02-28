## Thesis Template

```markdown
# Investment Thesis: {TICKER}

**Company:** {Full company name}
**Last Updated:** {YYYY-MM-DD}

---

## Classification

| Field | Value |
|-------|-------|
| Industry | {Industry} |
| Strategy | {Value/Growth/GARP/Event-Driven/Momentum} |
| Driver | {Valuation/Growth/Momentum/Event/Macro/Technical/Catalyst} |
| Info Source | {Self-Research/Sell-Side/Social Media/News/Podcast/13F/Friend/Earnings/Weekly Meeting/Other} |
| Idea Source | {substack/x/podcast/13f/supply-chain/weekly-meeting/chatgpt/self-research/other} |
| Source Detail | {e.g. "投资观点周报 2025, 2025-12-15 — 首次讨论 ZYN growth"} |
| Position | {LONG/SHORT/NONE} |
| Planned Hold | {30/60/90/180/365} days |

---

## Core Thesis

{2-3 sentences on why you own this}

---

## Bull Case

**Target:** ${TARGET} (+{PCT}% from entry)

1. {Reason 1}
2. {Reason 2}
3. {Reason 3}

## Bear Case

**Stop:** ${STOP} (-{PCT}% from entry)

1. {Risk 1}
2. {Risk 2}
3. {Risk 3}

---

## Key Catalysts

| Catalyst | Expected Date | Status |
|----------|---------------|--------|
| {Event 1} | {YYYY-MM-DD} | Pending |
| {Event 2} | {YYYY-MM-DD} | Pending |
| {Event 3} | {YYYY-MM-DD} | Pending |

---

## Position History

| Date | Action | Qty | Price | Notes |
|------|--------|-----|-------|-------|
| {YYYY-MM-DD} | {BUY/SELL} | {Qty} | ${Price} | {Notes} |

**Current Position:** {X} shares @ ${avg_cost} avg ({pct}% of NAV)

---

## Thesis Log

| Date | Update |
|------|--------|
| {YYYY-MM-DD} | Thesis created |

---

## Next Review

**Date:** {30 days from now}
**Trigger:** Next earnings / Key catalyst date
```

## Example Usage

**Create new thesis:**
```
User: /thesis TSM
Claude: No thesis found for TSM. Let me create one.
        Current position: 8,800 shares @ $348.18 avg (15.3% of NAV)

        I'll need a few details:
        1. Industry? [Technology]
        2. Strategy? [Growth/GARP/Value/Event-Driven/Momentum]
        3. Primary driver? [Growth/Valuation/Catalyst/...]
        4. Info source? [Self-Research/Sell-Side/...]
        5. Core thesis?
        6. Bull case + target?
        7. Bear case + stop?
        8. Key catalysts?
        9. Planned hold period?
```

**View existing thesis:**
```
User: /thesis NVDA
Claude: [Displays thesis.md content]

        📊 Current Position Status:
        • Shares: 3,800
        • Avg Cost: $187.97
        • Current: $186.47 (-0.80%)
        • Unrealized: -$5,683
        • % of NAV: 3.2%

        Would you like to update the thesis?
```

**Quick update:**
```
User: /thesis NVDA update "Blackwell shipping ahead of schedule"
Claude: ✓ Added to NVDA thesis log:
        2026-01-27 | Blackwell shipping ahead of schedule
```

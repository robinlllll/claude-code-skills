# 13f-backtest lessons

## 2026-02-11: Backtest conclusions are GROUP-SPECIFIC
- BT-4 and BT-5 conclusions REVERSE between Biotech and TMT:
  - Biotech BT-4: EW wins (Sharpe 2.44 > CW 1.01)
  - TMT BT-4: CW-Hybrid wins (Sharpe 0.79 > EW 0.61)
  - Biotech BT-5: Variant wins (+3.2%/qtr alpha)
  - TMT BT-5: Consensus wins (+4.98% vs +1.59%/qtr)
- **Never assume Biotech rules transfer to other groups** — always re-run backtests per group
- TMT has more performance data (longer track records) → hybrid scoring more informative
- TMT sample: 50 managers, 7-8 quarters of forward returns
- Results saved to: `研究/13F/backtest/TMT_BT4_BT5_hybrid_2025-Q3.md`

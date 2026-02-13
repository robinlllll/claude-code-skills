# PM Score Skill Lessons

## 2026-02-11: Initial deployment
- Group-specific output files are critical: `_implied_returns_{group}.json` not `_implied_returns.json`
  - Without group suffix, Biotech and TMT overwrite each other
- `stock_level_skill.py` requires `--save` flag — without it, only prints to console
- Performance scorer lazy-loads data per group via `score_group()` → `_load_data(group)`
- Janus Henderson has 35K+ stock picks because it's a massive diversified firm — creates outlier in stock-level analysis
- Farallon Capital scores poorly in Biotech (25.9) because it's a multi-strategy fund — consider removing from Biotech group
- α=0.17 for 13-quarter managers means 83% performance weight — performance dominates for established managers
- SILVERARC had biggest behavioral→hybrid drop (79→40) — high tenure but poor returns
- Boxer Capital (4 quarters) has α=0.92 — almost pure behavioral, shrinkage matters most here

## 2026-02-11: score_dict hybrid integration (cross-13f fix)
- `score_dict()` now applies hybrid blending via `_load_performance_scores_all()` — loads ALL group perf data
- Group name case matters: filenames are lowercase (`_implied_returns_biotech.json`) but PMGroupManager needs proper case (`Biotech`, `TMT`, `CN_PM`) — GROUP_CASE_MAP handles this
- `_get_perf_quarters_count()` merges ALL IR files when `_current_group` is None (cross-group mode)
- Perf data cached per scorer instance via `_all_perf_cache` — first call loads all groups (~2s), subsequent calls instant
- Fresh/Deep ranking in pm_recommender uses credibility for DISPLAY only (not as multiplier) per BT-4 results — but hybrid score gives users better context on who's actually good

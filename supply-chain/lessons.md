# Lessons Learned

## 2026-02-09: First successful run

- **Gemini 3 Pro hits daily quota fast** — ~5 NVDA transcripts (~300 chunks) exhausted the per-model daily limit. Switched to `gemini-2.0-flash` for bulk processing. Flash has much higher rate limits and is fast enough for extraction.
- **Must use `--tickers` for portfolio-first approach** — 633 total folders, but only 90 portfolio tickers (631 PDFs). Full scan would take hours; portfolio-only is more practical.
- **Bug fixed: false "processed" records** — Original code marked transcripts as processed even when ALL Gemini calls failed (429 errors). Fixed by returning `None` from `extract_mentions_from_chunk` on error and checking `error_count == len(chunks)` before recording.
- **Entity dictionary only covers 46 companies** — Most mentioned companies won't resolve to a ticker. `needs_review=True` is expected for v0. Expanding the dictionary is a future task.
- **Obsidian notes generate correctly** — Frontmatter, wikilinks `[[TICKER]]`, and table formatting all work. Notes land in `研究/供应链/`.
- **Transcript folder name format**: `"Company Name (TICKER-COUNTRY)"` e.g. `"NVIDIA Corp (NVDA-US)"`. The `--ticker` flag searches for `(TICKER-` pattern.
- **Some portfolio tickers lack transcripts**: DIDI, GOOG (use GOOGL), LI, NIO, TSM (may be under different suffix), WELL, XPEV.

## 2026-02-09: Full competitor/supplier scan (527 tickers, 18 batches)

- **Final stats**: 2,511 transcripts processed, 72,312 mentions, 589 source tickers, 46 mentioned tickers.
- **Parallel subagent batches work well** — 18 batches of 30 tickers each, 3 concurrent agents at a time. SQLite WAL mode + `timeout=30` handled concurrent writes without issues.
- **88% needs_review rate** — 63,630 of 72,312 mentions. The 46-company entity dictionary is the bottleneck. Expanding it is the highest-priority v1 task.
- **Entity dictionary mapping errors spotted** — Some resolved tickers look wrong: GOOGL→"Waymo", MSFT→"Dell", APP→"Discover", DIS→"Disney Research", EFX→"Goldman Sachs International". These are likely false matches where a generic company name in the dictionary matches an unrelated context. Need to audit entity_dictionary.yaml for overly broad patterns.
- **Top mentioned companies**: GS (1,501), GOOGL (1,412), JPM (1,401), AMZN (1,169), NVDA (627). Financial sector dominates because many earnings calls reference banks/brokers.
- **Top mentioning companies**: ELF (1,306), CELH (1,067), FI (1,018), EFX (928), OR (852). High mention counts may indicate verbose transcripts or many competitor references.
- **Gemini Flash handled ~2,500 transcripts without quota issues** — Across 18 parallel batches over ~2 hours, no 429 errors. Flash rate limits are sufficient for this scale.
- **Batch size of 30 is a good sweet spot** — Each batch takes 10-20 minutes depending on transcript count per ticker. 3 concurrent batches keeps throughput high without overwhelming the API.

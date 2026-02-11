# Lessons Learned

## 2026-02-10 | Conference vs Earnings Call separation: The indexer now categorizes 12+ event types (Conference, Investor Day, M&A Call, Business Update, etc.) and extracts event_name from filename. The browser UI separates earnings calls from conferences in distinct sections (conferences collapsed by default). Backend uses typed labels (event_type|Q# YYYY) to prevent conferences from contaminating earnings analysis. Legacy quarter-only labels only match Earnings Call type.

# Lessons Learned

## 2026-02-26 | find_transcripts.py only scans Earnings Transcripts/ subfolders, not Downloads root. New transcripts land in Downloads directly. When script returns 0 results, create manifests manually. entity_resolver returned None for XYZ/CRWV/MNST/CPNG/LKNCY/OPRA/PRM - not in dictionary. Bash cannot pass Chinese paths to Python inline - use pure Python for email with Unicode vault paths.

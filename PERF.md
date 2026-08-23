# Performance baseline

Measurements use the real development SQLite database (3,694 Subject, 4,916 Episode,
449 MediaFile and 35 DownloadJob records), warm caches, and repeated in-process calls.
Wall-clock numbers are diagnostic; query-count budgets in the test suite are the stable
regression guard.

| Path | Before | After | Result |
|---|---:|---:|---|
| Library review | 312.47 ms / 1,867 SQL | 28.01 ms / 4 SQL | Kept |
| 42-Episode detail | 12.02 ms / 86 SQL | 7.07 ms / 4 SQL | Kept |
| Recent library files | 6.14 ms / 25 SQL | 3.59 ms / 4 SQL | Kept |
| 35 download jobs | 12.06 ms / 71 SQL | 2.30 ms / 3 SQL | Kept |
| Scheduler status | 15.92 ms / 7 SQL | 5.48 ms / 1 SQL | Kept |
| Scheduler tick lookup | 4.73 ms / 7 SQL | 4.94 ms / 1 SQL | Kept: latency is noise, connection churn is reduced 86% |
| Cleanup candidates | 5,776.84 ms / 15,125 SQL | 6.52 ms / 1 SQL | Kept |
| Bangumi QUICK/FULL planning | 12 / 349 SQL | 2 / 2 SQL | Kept |

The installed-style Supervisor startup was 2.17–2.49 seconds over three cold backend
process starts, inside the 3-second desktop startup budget. Subject title search measured
20.84 ms and was left unchanged: caching it would add invalidation complexity without
addressing a measured bottleneck. The library review response is currently 867 KB; it is
below the 1 MB local-response budget, so pagination is deferred until real data exceeds it.

Run the regression checks with:

```bash
.venv/bin/pytest -q backend/tests/unit/test_query_budgets.py
```

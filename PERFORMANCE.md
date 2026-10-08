# Performance Log

Measurements for the Social Empires preservation server.
Recorded with `curl` (`%{time_total}`) against a warm server on localhost
(`127.0.0.1:5050`). Lower is better.

## Environment

- Python 3.14.5, Flask 3.1.3, Werkzeug 3.1.9
- Server: threaded dev server (`app.run(..., threaded=True)`)
- Client used for measurement: `curl.exe` (PowerShell `Invoke-WebRequest` is NOT
  reliable here — its client-side parsing inflates timings ~10x)

## 2026-10-07 — baseline after optimization pass

| Endpoint | 1st request | steady state |
| --- | --- | --- |
| GET get_game_config.php (2.1 MB) | ~44 ms | ~8 ms |
| POST get_player_info.php | — | ~5 ms |
| POST command.php | ~11 ms | ~6.5 ms |
| GET asset (.swf) | ~124 ms | ~5 ms |

Notes:

- `get_game_config` is serialized once and cached server-side; only the first
  request pays serialization cost.
- The first asset request is slower due to a cold disk read; the rest are served
  from the OS cache and get `Cache-Control: public, max-age=3600`.
- The server is no longer the bottleneck for game fluidity; the client runtime
  (native Flash vs Ruffle) dominates perceived performance.

## Optimization history

- 2026-10-07 — first pass: O(n) duplicate-item removal, no per-request save
  reload, neighbor payload fix, UTF-8 file reads.
- 2026-10-07 — second pass: single item lookup per action, binary-search level
  lookup, in-memory quest cache, atomic save writes, del-by-index.
- 2026-10-07 — third pass: cached the 2 MB config response, threaded server,
  gated per-request logging (`SE_VERBOSE`), browser asset caching.

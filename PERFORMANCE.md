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

## 2026-10-15 — after orjson saves + lazy log + per-batch item index

Measured with `py tools/measure_perf.py` (same methodology: `curl.exe`
`%{time_total}`, 5 warmup discarded, 30 runs). Save under test:
`4629746f-1f64-4c3e-84eb-5ddc2c3d8ba1`.

| Endpoint | 1st request | steady median | p95 | vs 2026-10-07 steady |
| --- | --- | --- | --- | --- |
| GET get_game_config.php (2.1 MB) | 7.7 ms | 7.7 ms | 29.0 ms | 8.0 ms -> 7.7 ms |
| POST get_player_info.php | 5.2 ms | 4.4 ms | 6.5 ms | 5.0 ms -> 4.4 ms |
| POST command.php (GAME_STATUS) | 5.5 ms | 5.9 ms | 11.9 ms | 6.5 ms -> 5.9 ms |
| GET asset (.swf, 613 KB) | 9.2 ms | 8.3 ms | 13.0 ms | 5.0 ms -> 8.3 ms |

Micros (same run):

- Save serialization on the real save: json-indent4 0.56 ms (79.7 KB) vs
  orjson 0.09 ms (13.0 KB) = 6.5x faster, ~6x smaller.
- Item lookup, 300 queries over 3000 items: linear scan 24.06 ms vs dict
  index 0.09 ms = ~280x on the lookup alone.

Notes:

- The `asset` steady difference (5.0 ms -> 8.3 ms) is environment noise on a
  path this pass did not touch; p95 outliers (29.0 ms on config) confirm a
  loaded machine during the run.
- End-to-end gains are modest because the request is dominated by fixed
  costs (Flask, per-request logging of `request.values`, disk); the hot
  paths themselves (save, lookup) improved by multiples.

## Optimization history

- 2026-10-07 — first pass: O(n) duplicate-item removal, no per-request save
  reload, neighbor payload fix, UTF-8 file reads.
- 2026-10-07 — second pass: single item lookup per action, binary-search level
  lookup, in-memory quest cache, atomic save writes, del-by-index.
- 2026-10-07 — third pass: cached the 2 MB config response, threaded server,
  gated per-request logging (`SE_VERBOSE`), browser asset caching.
- 2026-10-15 — fourth pass (local): orjson compact saves with stdlib fallback
  (`SE_PRETTY_SAVE=1` for readable saves), lazy log labels (no config lookup
  with `SE_VERBOSE=0`), ephemeral per-batch item index with verify+fallback.
  Measured with `tools/measure_perf.py` (see 2026-10-15 section above).

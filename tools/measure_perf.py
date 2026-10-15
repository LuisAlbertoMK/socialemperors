"""Repeatable local performance measurement for the Social Emperors server.

Same methodology as PERFORMANCE.md (2026-10-07 baseline): ``curl.exe``
``%{time_total}`` against a warm server on localhost. Not Invoke-WebRequest
(it inflates timings ~10x client-side).

Usage (server must already run in another console):
    py tools/measure_perf.py
    py tools/measure_perf.py --host 127.0.0.1 --port 5050 --runs 30

What it measures:
  1. GET get_game_config.php (2 MB, cached server-side)
  2. POST get_player_info.php (full player payload)
  3. POST command.php with a no-op GAME_STATUS (exercises save path)
  4. GET bundled .swf asset (disk + OS cache path)
  5. Micro: save serialization json-indent4 vs orjson (real save file)
  6. Micro: item lookup linear scan vs dict index (synthetic 3000 items)

Protocol per endpoint: 5 warmup requests (discarded), then N timed runs.
Reports 1st request, steady-state median and p95. Lower is better.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES_DIR = os.path.join(BASE_DIR, "saves")

BASELINE_20261007 = {
    "config": {"first": 44.0, "steady": 8.0},
    "player": {"first": None, "steady": 5.0},
    "command": {"first": 11.0, "steady": 6.5},
    "asset": {"first": 124.0, "steady": 5.0},
}

DYN = "/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires"
ASSET_PATH = (
    "/default01.static.socialpointgames.com/static/socialempires/swf/"
    "05122012_dynamic.swf"
)


def pick_userid():
    """Most recently modified save; the filename (minus suffix) is the USERID."""
    candidates = [
        f for f in os.listdir(SAVES_DIR) if f.endswith(".save.json")
    ]
    if not candidates:
        sys.exit("No saves found in saves/ — play once or create one first.")
    candidates.sort(
        key=lambda f: os.path.getmtime(os.path.join(SAVES_DIR, f)),
        reverse=True,
    )
    return candidates[0][: -len(".save.json")]


def curl_measure(url, post_fields=None):
    """One request via curl.exe; returns (ms, bytes, http_code)."""
    cmd = [
        "curl.exe", "-s", "-o", "NUL",
        "-w", "%{time_total} %{size_download} %{http_code}",
    ]
    if post_fields:
        for key, value in post_fields.items():
            cmd += ["--data-urlencode", f"{key}={value}"]
    cmd.append(url)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.exit("curl.exe not found — run from a console with curl.exe available.")
    parts = out.stdout.strip().split()
    if len(parts) != 3:
        sys.exit(f"curl failed for {url}: {out.stdout!r} {out.stderr!r}")
    seconds, size, code = float(parts[0]), int(parts[1]), parts[2]
    if code != "200":
        sys.exit(f"{url} returned HTTP {code} - is the server running?")
    return seconds * 1000.0, size


def measure_endpoint(name, url, runs, post_fields=None):
    for _ in range(5):  # warmup, discarded
        curl_measure(url, post_fields)
    first, _ = curl_measure(url, post_fields)
    samples = []
    sizes = []
    for _ in range(runs):
        ms, size = curl_measure(url, post_fields)
        samples.append(ms)
        sizes.append(size)
    samples.sort()
    median = statistics.median(samples)
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    return {"first": first, "median": median, "p95": p95, "bytes": sizes[-1]}


def micro_save(userid):
    """Serialization only: stdlib indent4 vs orjson, on the real save file."""
    path = os.path.join(SAVES_DIR, f"{userid}.save.json")
    with open(path, "rb") as handle:
        village = json.loads(handle.read().decode("utf-8"))
    reps = 20
    start = time.perf_counter()
    for _ in range(reps):
        text = json.dumps(village, indent=4)
    pretty_ms = (time.perf_counter() - start) / reps * 1000.0
    try:
        import orjson
    except ImportError:
        return {"pretty_ms": pretty_ms, "orjson_ms": None}
    start = time.perf_counter()
    for _ in range(reps):
        blob = orjson.dumps(village)
    orjson_ms = (time.perf_counter() - start) / reps * 1000.0
    return {
        "pretty_ms": pretty_ms,
        "pretty_kb": len(text.encode("utf-8")) / 1024.0,
        "orjson_ms": orjson_ms,
        "orjson_kb": len(blob) / 1024.0,
    }


def micro_lookup():
    """Lookup only: linear scan vs dict index, synthetic 3000 items."""
    import random

    random.seed(7)
    items = [[i % 500, i, i + 1, 0, 0, 0] for i in range(3000)]
    queries = [
        (items[i][0], items[i][1], items[i][2])
        for i in random.sample(range(3000), 300)
    ]

    def scan(iid, x, y):
        for it in items:  # noqa: SIM110 — mirrors the old production loop on purpose
            if it[0] == iid and it[1] == x and it[2] == y:
                return True
        return False

    start = time.perf_counter()
    for iid, x, y in queries:
        scan(iid, x, y)
    scan_ms = (time.perf_counter() - start) * 1000.0

    index = {}
    for pos, it in enumerate(items):
        index.setdefault((it[0], it[1], it[2]), pos)
    start = time.perf_counter()
    for iid, x, y in queries:
        index.get((iid, x, y))
    index_ms = (time.perf_counter() - start) * 1000.0
    return {"scan_ms": scan_ms, "index_ms": index_ms}


def game_status_envelope():
    payload = {
        "ts": 0,
        "first_number": 0,
        "accessToken": "token",
        "tries": 0,
        "publishActions": 0,
        "commands": [{"cmd": "game_status", "args": ["ok"]}],
    }
    return "0" * 64 + ";" + json.dumps(payload)


def main():
    parser = argparse.ArgumentParser(description="Measure local server performance.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"
    userid = pick_userid()
    print(f"USERID under test: {userid} (most recent save)")

    endpoints = {
        "config": (f"{base}{DYN}/get_game_config.php", None),
        "player": (f"{base}{DYN}/get_player_info.php", {"USERID": userid}),
        "command": (
            f"{base}{DYN}/command.php",
            {"USERID": userid, "data": game_status_envelope()},
        ),
        "asset": (f"{base}{ASSET_PATH}", None),
    }
    results = {}
    for name, (url, fields) in endpoints.items():
        results[name] = measure_endpoint(name, url, args.runs, fields)
        res = results[name]
        print(
            f"{name:8s} 1st {res['first']:7.1f} ms | "
            f"steady median {res['median']:6.1f} ms p95 {res['p95']:6.1f} ms "
            f"({res['bytes'] / 1024.0:.1f} KB)"
        )

    save = micro_save(userid)
    if save["orjson_ms"] is None:
        print("micro-save: orjson not installed, stdlib only "
              f"({save['pretty_ms']:.2f} ms)")
    else:
        print(
            f"micro-save: json-indent4 {save['pretty_ms']:.2f} ms "
            f"({save['pretty_kb']:.1f} KB) vs orjson {save['orjson_ms']:.2f} ms "
            f"({save['orjson_kb']:.1f} KB) = "
            f"{save['pretty_ms'] / max(save['orjson_ms'], 1e-9):.1f}x"
        )
    lookup = micro_lookup()
    print(
        f"micro-lookup (300 queries / 3000 items): scan {lookup['scan_ms']:.2f} ms "
        f"vs index {lookup['index_ms']:.2f} ms = "
        f"{lookup['scan_ms'] / max(lookup['index_ms'], 1e-9):.1f}x"
    )

    print("\nPaste-ready row for PERFORMANCE.md "
          f"(env: {sys.version.split()[0]}, runs={args.runs}):")
    print("| Endpoint | 1st | steady median | p95 | vs 2026-10-07 steady |")
    print("| --- | --- | --- | --- | --- |")
    for name in ("config", "player", "command", "asset"):
        res = results[name]
        old = BASELINE_20261007[name]["steady"]
        print(
            f"| {name} | {res['first']:.1f} ms | {res['median']:.1f} ms | "
            f"{res['p95']:.1f} ms | {old:.1f} ms -> {res['median']:.1f} ms |"
        )


if __name__ == "__main__":
    main()

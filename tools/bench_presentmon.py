"""Eval harness for PresentMon v1-metric CSVs (Ruffle desktop fluidez).

Usage:
    python tools/bench_presentmon.py <csv> [--pid 1234] [--skip 25]

Prints standard metrics (avg_fps, median, p95, janks/s) plus a Karpathy-style
CPU-vs-GPU split (median msGPUActive vs frame gap) and the anatomy of the
single worst frame. Pin the baseline numbers in docs/benchmarks/ODD-bitacora.md
before claiming any optimization.
"""
import argparse
import csv
import statistics
import sys


def load(path, pid=None, skip=25.0):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if pid is not None:
        rows = [r for r in rows if r.get("ProcessID") == str(pid)]
    rows = [r for r in rows if r.get("Dropped", "0") == "0"]
    if not rows:
        return []
    t0 = float(rows[0]["TimeInSeconds"]) + skip
    return [r for r in rows if float(r["TimeInSeconds"]) >= t0]


def col(rows, name, lo=0.0, hi=2000.0):
    out = []
    for r in rows:
        try:
            v = float(r[name])
        except (TypeError, ValueError):
            continue
        if lo < v < hi:
            out.append(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--pid", default=None)
    ap.add_argument("--skip", type=float, default=25.0)
    args = ap.parse_args()

    seg = load(args.csv, args.pid, args.skip)
    gap = sorted(col(seg, "msBetweenPresents"))
    if not gap:
        print("no frames")
        return 1
    n = len(gap)
    dur = sum(gap) / 1000.0
    j50 = sum(1 for x in gap if x > 50)
    gpu = col(seg, "msGPUActive")
    dsp = col(seg, "msUntilDisplayed")
    print(f"n={n} dur_s={dur:.0f} avg_fps={n / dur:.1f} "
          f"med={statistics.median(gap):.1f} p95={gap[int(n * 0.95)]:.1f} "
          f"max={gap[-1]:.1f} j50={j50} ({j50 / dur:.2f}/s) "
          f"j100={sum(1 for x in gap if x > 100)}")
    if gpu:
        print(f"gpu_med={statistics.median(gpu):.2f} "
              f"(share of median frame: {statistics.median(gpu) / statistics.median(gap) * 100:.0f}%)")
    if dsp:
        print(f"displayed_med={statistics.median(dsp):.2f}")
    wi = max(range(len(gap)), key=lambda i: gap[i])
    print(f"worst frame: gap={gap[wi]:.1f}ms")
    print(f"modes={sorted(set(r.get('PresentMode', '?') for r in seg))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

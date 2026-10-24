"""The resyn2 baseline across the route corpus, at real sign-off.

Runs the reference resyn2 recipe through the FULL ORFS (OpenROAD Flow Scripts) flow
(synthesis plus place-and-route to finish) on each design and records post-route QoR
(Quality of Results). This does two jobs at once:
  1. confirms each design routes end-to-end under our injected-recipe regime, and
  2. records the baseline number every learned recipe must beat.

Runs are independent (each design writes its own log tree), so they go in parallel.
Results stream to JSONL as they finish and a table is printed at the end.

Usage:
    python3 baseline.py                          # resyn2 over the route corpus
    python3 baseline.py --designs gcd aes ibex --workers 3
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

import recipes as rc
from harness import run_recipe
from patch_orfs import DEFAULT_ORFS, apply as apply_patch

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

# The ten small-to-medium designs verified synthesis-clean in results/DESIGN_SET.md.
# cva6 and swerv_wrapper are held out of the default corpus (route cost); pass them
# explicitly with --designs to include the stretch set.
ROUTE_CORPUS = [
    "gcd", "uart", "mock-alu", "aes", "ibex",
    "riscv32i", "aes-block", "jpeg", "mock-cpu", "ethmac",
]


def main():
    ap = argparse.ArgumentParser(description="resyn2 baseline across the route corpus.")
    ap.add_argument("--designs", nargs="+", default=ROUTE_CORPUS)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=7200)
    args = ap.parse_args()

    print(apply_patch(args.orfs))
    recipe = rc.resyn2()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"baseline_resyn2_{stamp}.jsonl")
    print(f"resyn2 full-flow baseline on {len(args.designs)} designs, "
          f"{args.workers} workers, {args.num_cores} cores each")
    print(f"results -> {out_path}")

    results = []
    with open(out_path, "w") as out, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(run_recipe, recipe, design=d, orfs=args.orfs,
                      timeout_s=args.timeout, num_cores=args.num_cores): d
            for d in args.designs
        }
        done = 0
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            out.write(json.dumps(asdict(res), default=list) + "\n")
            out.flush()
            done += 1
            status = (f"area={res.area:.1f} wns={res.wns:.1f} ({res.runtime_s}s)"
                      if res.ok else f"FAILED ({res.runtime_s}s)")
            print(f"[{done}/{len(args.designs)}] {res.design}: {status}", flush=True)

    table(results)


def table(results):
    rows = sorted(results, key=lambda r: (not r.ok, r.design))
    print("\n===== resyn2 baseline (full flow, post-route sign-off) =====")
    hdr = f"{'design':<14} {'ok':>3} {'area':>10} {'wns':>9} {'tns':>10} {'power':>10} {'sec':>7}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r.ok:
            print(f"{r.design:<14} {'OK':>3} {r.area:>10.1f} {r.wns:>9.2f} "
                  f"{r.tns:>10.1f} {r.power:>10.4g} {r.runtime_s:>7}")
        else:
            print(f"{r.design:<14} {'x':>3} {'-':>10} {'-':>9} {'-':>10} {'-':>10} {r.runtime_s:>7}")
    clean = [r.design for r in rows if r.ok]
    print(f"\n{len(clean)}/{len(rows)} routed end-to-end: {', '.join(clean)}")


if __name__ == "__main__":
    main()

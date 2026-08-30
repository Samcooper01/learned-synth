"""Sweep driver: run resyn2 plus N random classic recipes on a design.

Runs are independent (each recipe has its own FLOW_VARIANT output tree), so they
execute in parallel. Results stream to a JSONL file as they finish, and a
leaderboard is printed at the end: does any searched recipe beat resyn2?
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

import recipes as rc
from harness import run_recipe
from patch_orfs import DEFAULT_ORFS, apply as apply_patch

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def build_recipes(n_random: int, seed: int) -> list[rc.Recipe]:
    rng = random.Random(seed)
    batch = [rc.resyn2()]
    batch += [rc.random_recipe(rng) for _ in range(n_random)]
    return batch


def sweep(design: str, recipes_list, orfs: str, workers: int, out_path: str):
    results = []
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as out, ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(run_recipe, r, design=design, orfs=orfs): r
            for r in recipes_list
        }
        done = 0
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            out.write(json.dumps(asdict(res), default=list) + "\n")
            out.flush()
            done += 1
            tag = res.variant
            status = f"fom={res.fom:.2f} area={res.area}" if res.ok else "FAILED"
            print(f"[{done}/{len(recipes_list)}] {tag}: {status}", flush=True)
    return results


def leaderboard(results):
    ok = [r for r in results if r.ok and r.fom is not None]
    failed = [r for r in results if not r.ok]
    ok.sort(key=lambda r: r.fom)
    base = next((r for r in ok if r.variant.startswith("resyn2")), None)

    print("\n===== leaderboard (lower fom is better) =====")
    print(f"{'rank':>4}  {'variant':<18} {'fom':>8} {'area':>8} {'wns':>9} {'delta_vs_resyn2':>16}")
    for i, r in enumerate(ok, 1):
        delta = ""
        if base and base.fom:
            d = 100.0 * (r.fom - base.fom) / base.fom
            delta = f"{d:+.2f}%"
        mark = "  <-- resyn2" if r is base else ""
        print(f"{i:>4}  {r.variant:<18} {r.fom:>8.2f} {r.area:>8.2f} {r.wns:>9.2f} {delta:>16}{mark}")
    if failed:
        print(f"\n{len(failed)} failed: {', '.join(r.variant for r in failed)}")
    if base and ok and ok[0] is not base:
        win = 100.0 * (ok[0].fom - base.fom) / base.fom
        print(f"\nBEST beats resyn2 by {abs(win):.2f}% on fom ({ok[0].variant}).")
    elif base:
        print("\nNo random recipe beat resyn2 in this batch.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="gcd")
    ap.add_argument("--n", type=int, default=20, help="number of random recipes")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    args = ap.parse_args()

    print(apply_patch(args.orfs))
    batch = build_recipes(args.n, args.seed)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"{args.design}_{stamp}.jsonl")
    print(f"running {len(batch)} recipes on {args.design}, {args.workers} workers")
    print(f"results -> {out_path}")

    t0 = time.time()
    results = sweep(args.design, batch, args.orfs, args.workers, out_path)
    print(f"\nsweep wall-clock: {time.time() - t0:.0f}s")
    leaderboard(results)

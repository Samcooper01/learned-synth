"""Step 3: the label factory. Search recipes at each design's matched-delay clock.

For every design in the corpus this runs resyn2 plus N random classic recipes
through the FULL ORFS (OpenROAD Flow Scripts) flow at the design's calibrated clock
period (from results/clocks.json), and logs real post-route QoR (Quality of Results)
for each. It produces two deliverables at once:
  1. the headline: per design, does any searched recipe beat resyn2 on area while
     meeting timing (iso-timing / matched-delay comparison)?
  2. the dataset: (design, recipe) -> real QoR rows for training the Rung 3 predictor.

Every raw metric is logged, so the figure of merit or the comparison rule can change
later without re-running anything.

Usage:
    python3 labelsweep.py --designs gcd uart aes --n 15        # pilot
    python3 labelsweep.py --n 50 --workers 4                   # full corpus
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
from calibrate_clocks import write_sdc

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def load_clocks():
    with open(os.path.join(RESULTS_DIR, "clocks.json")) as f:
        return json.load(f)


def done_pairs(paths):
    """Set of (design, variant) already routed OK across prior sweep JSONL files, so
    a resumed run skips them. Enables crash recovery: rerun and only gaps re-route."""
    done = set()
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok"):
                done.add((r["design"], r["variant"]))
    return done


def build_tasks(designs, clocks, n, seed, orfs, skip=None, force_classic_abc=False):
    """Flatten to independent (design, recipe, extra_vars) tasks for wide parallelism.

    The per-design SDC (calibrated clock) is written once here; every recipe on that
    design reuses it. The "md" (matched-delay) label prefix keeps FLOW_VARIANT
    distinct from the shipped-clock baseline runs so make rebuilds these fresh.

    force_classic_abc empties SWAP_ARITH_OPERATORS / SYNTH_WRAPPED_OPERATORS so
    synthesis takes the classic `abc -script` path (which honors our recipe) instead
    of `abc_new`/ABC9 (which crops out -script and ignores the recipe entirely).
    """
    tasks = []
    for d in designs:
        clk = clocks[d]
        period = clk["calibrated_period"]
        sdc = write_sdc(orfs, d, period, scale_all=clk.get("mode") == "scale_all")
        extra = {"SDC_FILE": sdc}
        if force_classic_abc:
            extra["SWAP_ARITH_OPERATORS"] = ""
            extra["SYNTH_WRAPPED_OPERATORS"] = ""
        rng = random.Random(f"{d}:{seed}")  # deterministic per (design, seed)
        # The clock period is folded into the label (hence FLOW_VARIANT), so runs at
        # different clocks never reuse each other's stale ORFS output directories.
        specs = [(rc.Recipe(steps=rc.RESYN2, label=f"md{period}r2"), True)]
        specs += [(rc.Recipe(steps=rc.random_recipe(rng).steps, label=f"md{period}rr"),
                   False) for _ in range(n)]
        for recipe, is_resyn2 in specs:
            if skip and (d, recipe.variant) in skip:
                continue
            tasks.append((d, recipe, extra, period, is_resyn2))
    return tasks


def run_one(design, recipe, extra, period, is_resyn2, orfs, num_cores, timeout_s):
    res = run_recipe(recipe, design=design, orfs=orfs, num_cores=num_cores,
                     timeout_s=timeout_s, extra_vars=extra)
    row = asdict(res)
    row["calibrated_period"] = period
    row["is_resyn2"] = is_resyn2
    row["meets_timing"] = bool(res.ok and res.wns is not None and res.wns >= 0)
    return design, row


def leaderboard(design, rows):
    if not rows:
        # a resumed run may route zero recipes for a design already complete
        print(f"\n----- {design}: no routes this run (already complete) -----")
        return None
    resyn2 = next((r for r in rows if r["is_resyn2"]), None)
    ok = [r for r in rows if r["ok"] and r["area"] is not None]
    met = [r for r in ok if r["meets_timing"]]
    print(f"\n----- {design} (period {rows[0]['calibrated_period']} ps, "
          f"{len(rows)} recipes, {len(met)} meet timing) -----")
    if not resyn2 or not resyn2["ok"]:
        print("  resyn2 FAILED; cannot compare")
        return None
    base_area = resyn2["area"]
    base_meets = resyn2["meets_timing"]
    pool = met if met else ok
    best = min(pool, key=lambda r: r["area"])
    delta = 100.0 * (best["area"] - base_area) / base_area
    print(f"  resyn2 : area {base_area:.1f}  wns {resyn2['wns']:.2f}"
          f"{'' if base_meets else '  (misses timing)'}")
    tag = "meets timing" if best["meets_timing"] else "best available (none meet timing)"
    print(f"  best   : area {best['area']:.1f}  wns {best['wns']:.2f}  ({tag})")
    if best is resyn2 or delta >= 0:
        print(f"  => resyn2 not beaten (best is {delta:+.2f}% area)")
    else:
        print(f"  => searched recipe beats resyn2 by {abs(delta):.2f}% area at matched delay")
    return {"design": design, "resyn2_area": base_area, "best_area": best["area"],
            "delta_pct": delta, "n_meet_timing": len(met)}


def main():
    ap = argparse.ArgumentParser(description="Recipe search at matched-delay clocks.")
    ap.add_argument("--designs", nargs="+", default=None,
                    help="default: all designs in clocks.json")
    ap.add_argument("--n", type=int, default=30, help="random recipes per design")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--resume", action="store_true",
                    help="skip (design, recipe) pairs already routed OK in existing "
                         "results/labelsweep_*.jsonl files")
    ap.add_argument("--force-classic-abc", action="store_true",
                    help="empty SWAP_ARITH_OPERATORS/SYNTH_WRAPPED_OPERATORS so the "
                         "classic abc -script path runs (recipes apply); needed for "
                         "designs that otherwise use abc_new and ignore the recipe")
    args = ap.parse_args()

    print(apply_patch(args.orfs))
    clocks = load_clocks()
    designs = args.designs or sorted(clocks)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"labelsweep_{stamp}.jsonl")
    import glob as _glob
    skip = done_pairs(_glob.glob(os.path.join(RESULTS_DIR, "labelsweep_*.jsonl"))) \
        if args.resume else None
    if skip:
        print(f"resume: skipping {len(skip)} already-routed (design, recipe) pairs")
    tasks = build_tasks(designs, clocks, args.n, args.seed, args.orfs, skip=skip,
                        force_classic_abc=args.force_classic_abc)
    print(f"label sweep: {len(designs)} designs x (1 resyn2 + {args.n} random) "
          f"= {len(tasks)} routes at matched-delay clocks, {args.workers} workers")
    print(f"results -> {out_path}")

    import threading
    lock = threading.Lock()
    by_design = {d: [] for d in designs}
    t0 = time.time()
    with open(out_path, "w") as out, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [
            ex.submit(run_one, d, recipe, extra, period, is_resyn2,
                      args.orfs, args.num_cores, args.timeout)
            for (d, recipe, extra, period, is_resyn2) in tasks
        ]
        done = 0
        for fut in as_completed(futs):
            design, row = fut.result()
            by_design[design].append(row)
            with lock:
                out.write(json.dumps(row, default=list) + "\n")
                out.flush()
            done += 1
            if done % 5 == 0 or done == len(futs):
                print(f"[{done}/{len(futs)}] routes done", flush=True)

    print(f"\nsweep wall-clock: {time.time() - t0:.0f}s")
    print("\n===== matched-delay leaderboard (area, lower is better) =====")
    summary = []
    for d in designs:
        if d in by_design:
            s = leaderboard(d, by_design[d])
            if s:
                summary.append(s)
    wins = [s for s in summary if s["delta_pct"] < 0]
    if summary:
        avg = sum(s["delta_pct"] for s in summary) / len(summary)
        print(f"\nsearched recipe beats resyn2 on {len(wins)}/{len(summary)} designs; "
              f"mean area delta {avg:+.2f}% (negative = smaller than resyn2)")


if __name__ == "__main__":
    main()

"""Load-managed re-run of the abc_new-fixed designs.

Instead of a fixed worker pool, this sizes concurrency to the machine's *available*
memory every cycle, so it shares the host with other jobs (e.g. a co-running Systole
route) without thrashing. It launches individual full-flow routes as memory permits,
records each result, and scales up as memory frees and down as it tightens.

Concurrency rule:
    allowed = clamp(0, MAX, floor((MemAvailable_MB - RESERVE_MB) / PER_ROUTE_MB))
A new route starts only when there is at least one PER_ROUTE_MB slot free beyond the
reserve, and launches are staggered so several routes do not hit their detailed-route
memory peak at the same instant. Because available memory drops as routes ramp, the
rule is self-limiting.

Resumable: skips (design, recipe) pairs already routed OK. Exits when all done.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import threading
import time
from dataclasses import asdict

from harness import run_recipe
from labelsweep import build_tasks, done_pairs, load_clocks

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
LOG = os.path.join(RESULTS_DIR, "loadmanaged_rerun.log")


def mem_available_mb() -> int:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) // 1024
    return 0


def log(msg):
    line = f"{time.strftime('%F %T')} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", nargs="+", default=["ibex", "mock-alu", "riscv32i"])
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--orfs", default=None)
    ap.add_argument("--max-workers", type=int, default=6)
    ap.add_argument("--reserve-mb", type=int, default=8000,
                    help="memory kept free for other jobs (Systole) + OS")
    ap.add_argument("--per-route-mb", type=int, default=4000,
                    help="budgeted peak memory per route (measured ~3.6GB, rounded up)")
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=7200)
    args = ap.parse_args()

    from patch_orfs import DEFAULT_ORFS, apply as apply_patch
    orfs = args.orfs or DEFAULT_ORFS
    apply_patch(orfs)
    clocks = load_clocks()
    skip = done_pairs(glob.glob(os.path.join(RESULTS_DIR, "labelsweep_*.jsonl")))
    tasks = build_tasks(args.designs, clocks, args.n, args.seed, orfs,
                        skip=skip, force_classic_abc=True)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"labelsweep_lm_{stamp}.jsonl")
    out = open(out_path, "a")
    lock = threading.Lock()
    state = {"active": 0, "done": 0}
    log(f"start: {len(tasks)} tasks, max_workers={args.max_workers}, "
        f"reserve={args.reserve_mb}MB, per_route={args.per_route_mb}MB -> {out_path}")

    def worker(task):
        d, recipe, extra, period, is_resyn2 = task
        try:
            res = run_recipe(recipe, design=d, orfs=orfs, num_cores=args.num_cores,
                             timeout_s=args.timeout, extra_vars=extra)
            row = asdict(res)
            row["calibrated_period"] = period
            row["is_resyn2"] = is_resyn2
            row["meets_timing"] = bool(res.ok and res.wns is not None and res.wns >= 0)
            with lock:
                out.write(json.dumps(row, default=list) + "\n")
                out.flush()
                state["done"] += 1
                status = f"area={res.area}" if res.ok else "FAILED"
                log(f"  route done: {d} {recipe.variant} {status} "
                    f"({state['done']} total)")
        finally:
            with lock:
                state["active"] -= 1

    pending = list(tasks)
    while pending or state["active"] > 0:
        avail = mem_available_mb()
        allowed = max(0, min(args.max_workers,
                             (avail - args.reserve_mb) // args.per_route_mb))
        with lock:
            active = state["active"]
        while active < allowed and pending:
            threading.Thread(target=worker, args=(pending.pop(0),), daemon=True).start()
            with lock:
                state["active"] += 1
                active = state["active"]
            time.sleep(3)  # stagger so detailed-route peaks do not align
        log(f"avail={avail}MB allowed={allowed} active={state['active']} "
            f"pending={len(pending)} done={state['done']}")
        time.sleep(20)

    out.close()
    log(f"COMPLETE: {state['done']} routes done, output {out_path}")


if __name__ == "__main__":
    main()

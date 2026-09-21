"""Step 2: calibrate a per-design clock period so resyn2 meets timing with a small
positive slack, putting every design in a clean iso-timing (matched-delay) regime.

Why: raw post-route area is only a fair objective when timing is met. At each
design's shipped clock, six of the nine corpus designs miss timing, so the flow
burns area chasing slack and area comparisons are contaminated. We instead find,
per design, the clock period at which resyn2 just meets timing (Worst Negative Slack
slightly >= 0), then every recipe is compared at that fixed period. The result is a
single defensible headline: area reduction at matched delay.

Method: fixed-point search. The achievable data-path delay is roughly period minus
Worst Negative Slack, so period_next = period - wns drives Worst Negative Slack
toward zero; a small margin biases it slightly positive. Each step is one full route
(the only honest signal, since routing parasitics matter), so we seed the first
estimate from the recorded resyn2 baseline to save an iteration and cap the search.

Output: results/clocks.json, consumed by the label sweep so every recipe runs at the
calibrated period.

Usage:
    python3 calibrate_clocks.py                 # calibrate the whole corpus
    python3 calibrate_clocks.py --designs gcd aes --max-iters 4
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import recipes as rc
from harness import run_recipe
from patch_orfs import DEFAULT_ORFS, apply as apply_patch

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
SCRATCH = os.environ.get(
    "LEARNED_SYNTH_SCRATCH",
    os.path.join(tempfile.gettempdir(), "learned-synth", "sdc"),
)

# The exact base SDC (Synopsys Design Constraints) file the resyn2 baseline used,
# relative to the design directory. ibex has a variant-conditional SDC; the baseline
# used constraint.sdc, so we pin that. The first `set clk_period <N>` line in each
# is the critical clock; multi-clock designs (ethmac, mock-cpu) keep their other
# clocks untouched.
BASE_SDC = {
    "gcd": "constraint.sdc",
    "uart": "constraint.sdc",
    "mock-alu": "constraints.sdc",
    "aes": "constraint.sdc",
    "ibex": "constraint.sdc",
    "riscv32i": "constraint.sdc",
    "jpeg": "jpeg_encoder15_7nm.sdc",
    "mock-cpu": "constraint.sdc",
    "ethmac": "constraint.sdc",
}

# The critical clock line (the first `set clk_period`), scaled in absolute mode.
PERIOD_RE = re.compile(r"^(\s*set\s+clk_period\s+)(\d+)", re.MULTILINE)
# Every clock-period variable (clk_period, clk2_period, tx_clk_period, ...), scaled
# together in scale-all mode. Needed for a design whose binding path is on a clock
# other than the one we tune (e.g. ethmac's tx clock): scaling only the core clock
# never moves that design's Worst Negative Slack, so we relax the whole design by a
# common factor instead.
ALL_PERIOD_RE = re.compile(r"^(\s*set\s+\w*period\s+)(\d+)", re.MULTILINE)


def base_sdc_path(orfs, design):
    return os.path.join(orfs, "flow", "designs", "asap7", design, BASE_SDC[design])


def shipped_period(orfs, design):
    with open(base_sdc_path(orfs, design)) as f:
        m = PERIOD_RE.search(f.read())
    if not m:
        raise SystemExit(f"no 'set clk_period' in base SDC for {design}")
    return int(m.group(2))


def write_sdc(orfs, design, period, scale_all=False):
    """Copy the base SDC with the clock relaxed to a core-equivalent `period` (ps).

    In absolute mode only the critical clk_period is set to `period`. In scale-all
    mode every clock-period variable is scaled by period / shipped_core, so all
    clock domains relax together (for designs whose binding clock is not the core).
    """
    with open(base_sdc_path(orfs, design)) as f:
        text = f.read()
    if scale_all:
        p0 = shipped_period(orfs, design)
        factor = period / p0
        new_text, n = ALL_PERIOD_RE.subn(
            lambda m: f"{m.group(1)}{max(1, round(int(m.group(2)) * factor))}", text)
        if n < 1:
            raise SystemExit(f"no period vars to scale for {design}")
    else:
        new_text, n = PERIOD_RE.subn(rf"\g<1>{period}", text, count=1)
        if n != 1:
            raise SystemExit(f"failed to rewrite clk_period for {design}")
    os.makedirs(SCRATCH, exist_ok=True)
    out = os.path.join(SCRATCH, f"{design}_p{period}{'_all' if scale_all else ''}.sdc")
    with open(out, "w") as f:
        f.write(new_text)
    return out


def _baseline_wns():
    """Most recent resyn2 baseline Worst Negative Slack per design, to seed step 1."""
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "baseline_resyn2_*.jsonl")))
    wns = {}
    if files:
        with open(files[-1]) as f:
            for line in f:
                r = json.loads(line)
                if r.get("ok") and r.get("wns") is not None:
                    wns[r["design"]] = r["wns"]
    return wns


def run_at(orfs, design, period, num_cores, timeout_s, scale_all):
    """Run resyn2 at `period` and return (wns, area, ok). Distinct label per period
    so each run gets a fresh ORFS output directory."""
    sdc = write_sdc(orfs, design, period, scale_all=scale_all)
    tag = f"cal{period}{'a' if scale_all else ''}"
    recipe = rc.Recipe(steps=rc.RESYN2, label=tag)
    res = run_recipe(recipe, design=design, orfs=orfs, num_cores=num_cores,
                     timeout_s=timeout_s, extra_vars={"SDC_FILE": sdc})
    return res.wns, res.area, res.ok


def calibrate_one(orfs, design, seed_wns, max_iters, num_cores, timeout_s,
                  margin, scale_all, seed_period=None):
    p0 = shipped_period(orfs, design)
    # Target band: accept positive slack from 0 up to ~2x the aimed margin, so we
    # stop once resyn2 comfortably meets timing without over-relaxing.
    def band_hi(p):
        return max(3.0, 2.0 * margin * p)

    # Seed the first period. An explicit seed_period (from prior calibration data)
    # beats the baseline seed for designs that converge slowly or bind on a clock
    # the baseline could not see. Otherwise: delay ~= p0 - wns0, plus the margin.
    if seed_period is not None:
        period = seed_period
    elif seed_wns is not None:
        period = max(1, round(p0 - seed_wns + margin * p0))
    else:
        period = p0

    history = []
    for _ in range(max_iters):
        wns, area, ok = run_at(orfs, design, period, num_cores, timeout_s, scale_all)
        history.append({"period": period, "wns": wns, "area": area, "ok": ok})
        if not ok or wns is None:
            # Route failed at this period; relax further and retry.
            period = round(period * 1.10)
            continue
        if 0.0 <= wns <= band_hi(period):
            break
        period = max(1, round(period - wns + margin * period))

    met = [h for h in history if h["ok"] and h["wns"] is not None and h["wns"] >= 0]
    if met:
        chosen = min(met, key=lambda h: h["wns"])  # tightest that still meets timing
        converged = True
    else:
        ok_hist = [h for h in history if h["ok"] and h["wns"] is not None]
        chosen = max(ok_hist, key=lambda h: h["wns"]) if ok_hist else history[-1]
        converged = False

    return {
        "design": design,
        "shipped_period": p0,
        "calibrated_period": chosen["period"],
        "wns_at_calibrated": chosen["wns"],
        "area_at_calibrated": chosen["area"],
        "converged": converged,
        "mode": "scale_all" if scale_all else "absolute",
        "iters": len(history),
        "history": history,
    }


def main():
    ap = argparse.ArgumentParser(description="Calibrate per-design clocks to WNS~0 under resyn2.")
    ap.add_argument("--designs", nargs="+", default=list(BASE_SDC.keys()))
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--max-iters", type=int, default=4)
    ap.add_argument("--margin", type=float, default=0.02,
                    help="aimed positive slack as a fraction of the period")
    ap.add_argument("--scale-all", action="store_true",
                    help="scale every clock domain together (multi-clock designs)")
    ap.add_argument("--seed-period", type=int, default=None,
                    help="explicit starting period (ps); applies to all --designs")
    ap.add_argument("--timeout", type=int, default=7200)
    args = ap.parse_args()

    print(apply_patch(args.orfs))
    seed = _baseline_wns()
    print(f"calibrating {len(args.designs)} designs "
          f"(margin {args.margin}, scale_all={args.scale_all}, "
          f"seeded from baseline where available)")

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(calibrate_one, args.orfs, d, seed.get(d),
                      args.max_iters, args.num_cores, args.timeout,
                      args.margin, args.scale_all, args.seed_period): d
            for d in args.designs
        }
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            done += 1
            tag = "converged" if r["converged"] else "NOT converged"
            print(f"[{done}/{len(args.designs)}] {r['design']}: "
                  f"{r['shipped_period']} -> {r['calibrated_period']} ps "
                  f"(wns {r['wns_at_calibrated']}, {r['iters']} iters, {tag})", flush=True)

    # Merge into the existing clocks.json so re-running a subset preserves the rest.
    out_path = os.path.join(RESULTS_DIR, "clocks.json")
    try:
        with open(out_path) as f:
            out = json.load(f)
    except (OSError, json.JSONDecodeError):
        out = {}
    for r in rows:
        out[r["design"]] = r
    out = {k: out[k] for k in sorted(out)}
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {out_path} ({len(rows)} updated, {len(out)} total)")

    print("\n===== calibrated clocks (resyn2 at matched delay) =====")
    hdr = f"{'design':<12} {'shipped':>8} {'calib':>8} {'wns@calib':>10} {'iters':>6}  conv"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['design']:<12} {r['shipped_period']:>8} {r['calibrated_period']:>8} "
              f"{r['wns_at_calibrated']:>10} {r['iters']:>6}  {r['converged']}")


if __name__ == "__main__":
    main()

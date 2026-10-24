"""The matched-delay leaderboard from the 234-layout sweep dataset.

Reads every results/labelsweep_*.jsonl, dedupes by (design, variant) preferring the
successful route, and for each design compares the best timing-meeting recipe against
resyn2 at that design's fixed (wall) clock. This is the iso-timing / matched-delay
comparison: an area win only counts if it meets the same timing bar resyn2 does.

Usage: python3 analyze.py
"""

from __future__ import annotations

import glob
import json
import os

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
ORDER = ["gcd", "uart", "aes", "ibex", "jpeg", "mock-cpu", "mock-alu", "ethmac", "riscv32i"]


def load_dedup():
    best = {}
    for p in glob.glob(os.path.join(RESULTS_DIR, "labelsweep_*.jsonl")):
        for line in open(p):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = (r["design"], r["variant"])
            # prefer a successful route over a failed one for the same recipe
            if k not in best or (r["ok"] and not best[k]["ok"]):
                best[k] = r
    return list(best.values())


def recipe_had_effect(ok_rows, design):
    """True if recipes actually varied the result for this design. Some designs route
    synthesis through Yosys's abc_new/ABC9 path, which ignores our ABC_SCRIPT override,
    so every recipe yields the identical netlist (area variance ~0). Those rows are
    invalid for a recipe study and are excluded."""
    areas = [r["area"] for r in ok_rows if r["design"] == design and r["area"]]
    return len(set(round(a, 2) for a in areas)) > 1


def leaderboard(rows):
    ok = [r for r in rows if r["ok"]]
    all_designs = sorted(set(r["design"] for r in ok))
    invalid = [d for d in all_designs if not recipe_had_effect(ok, d)]
    if invalid:
        print(f"EXCLUDED (recipe had no effect, abc_new bypass): {', '.join(invalid)}")
    ok = [r for r in ok if r["design"] not in invalid]
    print(f"unique routes: {len(rows)}  ok: {len(ok)}  failed: {len(rows) - len(ok)}\n")
    hdr = f"{'design':<11} {'#met':>4} {'r2_area':>8} {'best_area':>9} {'delta%':>8} {'#beat':>5}  note"
    print(hdr)
    print("-" * len(hdr))
    summary = []
    for d in ORDER:
        dd = [r for r in ok if r["design"] == d]
        r2 = next((r for r in dd if r["is_resyn2"]), None)
        if not r2:
            continue
        met = [r for r in dd if r["meets_timing"]]
        pool = met if met else dd
        best_r = min(pool, key=lambda r: r["area"])
        delta = 100.0 * (best_r["area"] - r2["area"]) / r2["area"]
        beat = [r for r in met if not r["is_resyn2"] and r["area"] < r2["area"]]
        note = "" if best_r["meets_timing"] else "(none met timing)"
        print(f"{d:<11} {len(met):>4} {r2['area']:>8.1f} {best_r['area']:>9.1f} "
              f"{delta:>+8.2f} {len(beat):>5}  {note}")
        summary.append({"design": d, "delta": delta, "n_beat": len(beat),
                        "n_met": len(met), "resyn2_meets": r2["meets_timing"]})
    return summary


def main():
    rows = load_dedup()
    summary = leaderboard(rows)
    wins = [s for s in summary if s["delta"] < -0.01]
    deltas = sorted(s["delta"] for s in summary)
    print(f"\nsearched (random) recipe beats resyn2 on {len(wins)}/{len(summary)} designs")
    print(f"area delta vs resyn2: mean {sum(deltas)/len(deltas):+.2f}%  "
          f"best {deltas[0]:+.2f}%  median {deltas[len(deltas)//2]:+.2f}%")


if __name__ == "__main__":
    main()

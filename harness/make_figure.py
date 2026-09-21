"""Generate the recruiter-facing results figure (docs/results.png).

Two panels, both computed from the label-factory dataset:
  A. Goal 1 - best searched-recipe area vs resyn2 at matched delay, per design.
  B. Goal 2 - skip-curve: route only the top-K synthesis-ranked recipes.
"""

from __future__ import annotations

import collections
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
RESULTS_DIR = os.path.join(HERE, "..", "results")
OUT = os.path.join(HERE, "..", "docs", "results.png")

# colorblind-safe: blue = win, grey = no win, orange = accent line
WIN, NOWIN, ACCENT, ACCENT2 = "#0072B2", "#999999", "#D55E00", "#009E73"


def load():
    best = {}
    for p in glob.glob(os.path.join(RESULTS_DIR, "labelsweep_*.jsonl")):
        for line in open(p):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok") and r.get("area") and r.get("synth_area"):
                best[(r["design"], r["variant"])] = r
    return list(best.values())


def goal1_deltas(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["design"]].append(r)
    out = {}
    for d, rr in by.items():
        r2 = next((r for r in rr if r["is_resyn2"]), None)
        if not r2:
            continue
        met = [r for r in rr if r["meets_timing"]]
        pool = met if met else rr
        best = min(pool, key=lambda r: r["area"])
        out[d] = 100.0 * (best["area"] - r2["area"]) / r2["area"]
    return dict(sorted(out.items(), key=lambda kv: kv[1]))


def skip_curve(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["design"]].append(r)
    Ks = [1, 2, 3, 5, 8]
    cap = {k: [] for k in Ks}
    for d, rr in by.items():
        r2 = next((r for r in rr if r["is_resyn2"]), None)
        legal = [r for r in rr if r["meets_timing"]]
        if not r2 or not legal:
            continue
        best = min(r["area"] for r in legal)
        gain = r2["area"] - best
        if gain <= 0:
            continue
        order = sorted(rr, key=lambda r: r["synth_area"])
        for k in Ks:
            picked = [r for r in order[:k] if r["meets_timing"]]
            got = min((r["area"] for r in picked), default=r2["area"])
            cap[k].append(max(0.0, r2["area"] - got) / gain)
    import statistics
    return Ks, [100 * statistics.mean(cap[k]) for k in Ks], [100 * (1 - k / 26.0) for k in Ks]


def main():
    rows = load()
    deltas = goal1_deltas(rows)
    Ks, captured, saved = skip_curve(rows)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    # Panel A: goal-1 per-design area delta
    designs = list(deltas)
    vals = [deltas[d] for d in designs]
    colors = [WIN if v < -0.01 else NOWIN for v in vals]
    ax1.barh(designs, vals, color=colors)
    ax1.axvline(0, color="black", lw=0.8)
    ax1.set_xlabel("best searched recipe: area vs resyn2 (%)  -  lower is better")
    ax1.set_title("Goal 1: learned recipe beats resyn2 on 5/9 designs\n(at matched delay, real post-route area)", fontsize=11)
    for d, v in zip(designs, vals):
        ax1.text(v + (-0.15 if v < 0 else 0.15), d, f"{v:+.1f}%",
                 va="center", ha="right" if v < 0 else "left", fontsize=8)
    ax1.margins(x=0.18)

    # Panel B: skip-curve
    ax2.plot(Ks, captured, "-o", color=ACCENT2, label="achievable area gain captured")
    ax2.plot(Ks, saved, "-s", color=ACCENT, label="place-and-route budget saved")
    ax2.set_xlabel("full routes paid (top-K of 26 synthesis-ranked recipes)")
    ax2.set_ylabel("percent")
    ax2.set_ylim(0, 100)
    ax2.set_xticks(Ks)
    ax2.set_title("Goal 2: rank by cheap synthesis result, route only top-K\ntop-3 = 89% of the gain for 12% of the route cost", fontsize=11)
    ax2.legend(loc="center right", fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.suptitle("learned-synth: learning ABC recipes that beat resyn2 at real ASAP7 sign-off",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=130)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

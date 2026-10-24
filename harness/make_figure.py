"""Generate the recruiter-facing results figure (docs/results.png).

Two panels, both computed from the label-factory dataset:
  A. best searched-recipe area vs resyn2 at matched delay, per design.
  B. skip-curve: route only the top-K synthesis-ranked recipes.
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

# colors match the project page (docs/index.html): green = win, warm grey = no win,
# oxblood = the accent line; ink and rule colors for text and axes
WIN, NOWIN, ACCENT, ACCENT2 = "#2e6f40", "#b8b0a1", "#9c2a20", "#9c2a20"
INK, MUTED, RULE = "#151413", "#55524b", "#e7e2d7"

# The page sets its charts in Inter. If FIGURE_FONT_DIR points at a folder of .ttf
# files (for example Inter's static fonts), register them; otherwise matplotlib
# falls back to its default sans-serif.
from matplotlib import font_manager
for _f in glob.glob(os.path.join(os.environ.get("FIGURE_FONT_DIR", ""), "*.ttf")):
    font_manager.fontManager.addfont(_f)
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "DejaVu Sans"],
    "text.color": INK, "axes.labelcolor": MUTED, "axes.edgecolor": RULE,
    "xtick.color": MUTED, "ytick.color": INK, "axes.titlecolor": INK,
    "axes.titleweight": "semibold", "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


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


def plot_goal1(ax, deltas):
    designs = list(deltas)
    vals = [deltas[d] for d in designs]
    colors = [WIN if v < -0.01 else NOWIN for v in vals]
    ax.barh(designs, vals, color=colors)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel("best searched recipe: area vs resyn2 (%)  -  lower is better")
    ax.set_title("The best of 25 random recipes beats resyn2 on 5 of 9 designs\n(at matched timing, real post-layout area)", fontsize=11)
    for d, v in zip(designs, vals):
        ax.text(v + (-0.15 if v < 0 else 0.15), d, f"{v:+.1f}%",
                va="center", ha="right" if v < 0 else "left", fontsize=8,
                color=WIN if v < -0.01 else MUTED, fontweight="semibold" if v < -0.01 else "normal")
    ax.margins(x=0.18)


def plot_goal2(ax, Ks, captured, saved):
    ax.plot(Ks, captured, "-o", color=ACCENT2, lw=2)
    ax.axhline(100, ls="--", color=NOWIN, lw=1)
    ax.text(Ks[-1], 102, "lay out all 26 = 100% of the benefit",
            ha="right", va="bottom", fontsize=8, color=MUTED)
    i3 = Ks.index(3)
    ax.annotate("lay out just 3 of 26\n= 89% of the benefit", xy=(3, captured[i3]),
                xytext=(4.0, 58), fontsize=9.5,
                arrowprops=dict(arrowstyle="->", color=ACCENT2, lw=1.4))
    ax.set_xlabel("number of recipes you actually lay out (of 26)")
    ax.set_ylabel("share of the best possible area gain (%)")
    ax.set_ylim(0, 114)
    ax.set_xticks(Ks)
    ax.set_title("Lay out only the top few recipes, keep almost all the benefit\n(recipes ranked cheaply by synthesis first)", fontsize=11)
    ax.grid(True, color=RULE, lw=0.8)


def main():
    rows = load()
    deltas = goal1_deltas(rows)
    Ks, captured, saved = skip_curve(rows)
    outdir = os.path.dirname(OUT)
    os.makedirs(outdir, exist_ok=True)

    # combined (kept for the repository README)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))
    plot_goal1(ax1, deltas)
    plot_goal2(ax2, Ks, captured, saved)
    fig.suptitle("learned-synth: searching for ABC recipes that beat resyn2 at real ASAP7 sign-off",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT, dpi=130)

    # standalone panels for the project page (one per section)
    f1, a1 = plt.subplots(figsize=(6.6, 4.6)); plot_goal1(a1, deltas)
    f1.tight_layout(); f1.savefig(os.path.join(outdir, "results_goal1.png"), dpi=130)
    f2, a2 = plt.subplots(figsize=(6.6, 4.6)); plot_goal2(a2, Ks, captured, saved)
    f2.tight_layout(); f2.savefig(os.path.join(outdir, "results_goal2.png"), dpi=130)
    print(f"wrote {OUT}, results_goal1.png, results_goal2.png")


if __name__ == "__main__":
    main()

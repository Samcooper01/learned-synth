"""Goal 2: a cheap QoR (Quality of Results) predictor that prunes the recipe search.

The pitch: place-and-route is expensive; synthesis is cheap. If a cheap,
synthesis-only signal predicts the post-route result, we can rank candidate recipes
after synthesis and pay for a full route on only the top few.

This script shows, on the 234-route label-factory dataset, that:
  1. a recipe's post-synthesis cell area predicts its post-route area strongly
     within a design (Spearman ~0.8), so it is a good cheap ranker;
  2. a small model on synthesis-only features (recipe command counts + length +
     post-synth area) ranks recipes about as well; and
  3. routing only the top-K synthesis-ranked recipes recovers most of the achievable
     area improvement while paying a fraction of the full-route budget (the
     route-budget-saved / skip-curve).

Everything here is numpy on ~234 rows: no routing, seconds to run.

Usage: python3 predict_qor.py
"""

from __future__ import annotations

import glob
import json
import os
import collections

import numpy as np

import recipes as rc

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
ALPHABET = list(rc.ALPHABET)


def load_rows():
    best = {}
    for p in glob.glob(os.path.join(RESULTS_DIR, "labelsweep_*.jsonl")):
        for line in open(p):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok") and r.get("area") and r.get("synth_area"):
                best[(r["design"], r["variant"])] = r
    rows = list(best.values())
    # Exclude any design whose recipes had no effect (abc_new bypass); after the
    # --force-classic-abc fix none should, but keep the guard.
    areas = {}
    for r in rows:
        areas.setdefault(r["design"], set()).add(round(r["area"], 2))
    valid = {d for d, s in areas.items() if len(s) > 1}
    return [r for r in rows if r["design"] in valid]


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def features(rows):
    """Synthesis-only features per row: recipe command counts, length, post-synth
    area. All available after synthesis, before any place-and-route."""
    X = []
    for r in rows:
        steps = list(r["steps"])
        counts = [steps.count(cmd) for cmd in ALPHABET]
        X.append(counts + [len(steps), r["synth_area"]])
    return np.array(X, float)


def ridge_cv_rank(rows):
    """Leave-one-design-out ridge on synthesis-only features; report the per-design
    rank correlation of predicted vs actual routed area."""
    designs = np.array([r["design"] for r in rows])
    X = features(rows)
    y = np.array([r["area"] for r in rows], float)
    rhos = {}
    for d in np.unique(designs):
        te = designs == d; tr = ~te
        mu, sd = X[tr].mean(0), X[tr].std(0); sd[sd == 0] = 1
        Xtr = np.hstack([(X[tr]-mu)/sd, np.ones((tr.sum(), 1))])
        Xte = np.hstack([(X[te]-mu)/sd, np.ones((te.sum(), 1))])
        # normalize y within train designs per-design to learn recipe effect, but
        # here we predict absolute area and only care about within-design ranking.
        w = np.linalg.solve(Xtr.T@Xtr + np.eye(Xtr.shape[1]), Xtr.T@y[tr])
        pred = Xte@w
        rhos[d] = spearman(pred, y[te])
    return rhos


def skip_curve(rows, ranker):
    """For each design, rank its recipes by `ranker` (a cheap, synth-only score),
    route only the top-K, and measure the fraction of the achievable area gain
    captured. 'Achievable' = best routed area among recipes that meet timing.
    ranker(row) -> score (lower routed area expected for lower score)."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["design"]].append(r)
    Ks = [1, 2, 3, 5, 8]
    cap = {k: [] for k in Ks}
    resyn2_baseline_beaten = {k: [] for k in Ks}
    improvable = []
    for d, rr in by.items():
        resyn2 = next((r for r in rr if r["is_resyn2"]), None)
        if not resyn2:
            continue
        legal = [r for r in rr if r["meets_timing"]]
        if not legal:
            continue
        best_area = min(r["area"] for r in legal)
        base = resyn2["area"]
        gain = base - best_area                 # achievable area reduction vs resyn2
        if gain <= 0:
            continue                            # nothing to capture on this design
        improvable.append(d)
        order = sorted(rr, key=ranker)          # cheap ranking, ascending score
        for k in Ks:
            picked = order[:k]
            legal_picked = [r for r in picked if r["meets_timing"]]
            got = min((r["area"] for r in legal_picked), default=base)
            cap[k].append(max(0.0, (base - got)) / gain)
            resyn2_baseline_beaten[k].append(1.0 if got < base else 0.0)
    return Ks, cap, resyn2_baseline_beaten, improvable


def main():
    rows = load_rows()
    designs = sorted(set(r["design"] for r in rows))
    n_designs = len(designs)
    print(f"dataset: {len(rows)} routes, {n_designs} designs\n")

    # 1. the cheap signal: post-synth area vs routed area, within design
    by = collections.defaultdict(list)
    for r in rows:
        by[r["design"]].append(r)
    print("1) within-design Spearman(post-synth area, routed area) - the cheap signal")
    rhos = []
    for d in designs:
        rr = by[d]
        rho = spearman([r["synth_area"] for r in rr], [r["area"] for r in rr])
        rhos.append(rho)
        print(f"     {d:<12} rho={rho:+.3f}")
    print(f"     mean rho = {np.mean(rhos):+.3f}\n")

    # 2. a trained synth-only predictor (leave-one-design-out) ranks about as well
    print("2) leave-one-design-out ridge on synth-only features: per-design rank corr")
    r2 = ridge_cv_rank(rows)
    for d in designs:
        print(f"     {d:<12} rho={r2[d]:+.3f}")
    print(f"     mean rho = {np.mean([r2[d] for d in designs]):+.3f}\n")

    # 3. skip-curve: rank by post-synth area, route only top-K
    print("3) skip-curve: rank by post-synth area, route only the top-K per design")
    Ks, cap, beaten, improvable = skip_curve(rows, ranker=lambda r: r["synth_area"])
    print(f"     (over {len(improvable)} designs where a better recipe than resyn2 exists: "
          f"{', '.join(improvable)})")
    print(f"     {'K':>3}  {'routes':>7}  {'route budget saved':>18}  {'gain captured':>13}  {'designs beaten':>14}")
    for k in Ks:
        saved = 100.0 * (1 - k / 26.0)
        print(f"     {k:>3}  {k:>2}/26   {saved:>16.0f}%  {100*np.mean(cap[k]):>11.0f}%  "
              f"{int(sum(beaten[k]))}/{len(improvable)}")


if __name__ == "__main__":
    main()

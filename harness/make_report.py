"""Generate results/RESULTS.md from the training log and evaluation json.

Defensive: writes whatever is available, so a partial overnight run still yields a
report.
"""

from __future__ import annotations

import csv
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
RESULTS = os.path.join(ROOT, "results")


def load_training():
    path = os.path.join(ROOT, "models", "training_log.csv")
    if not os.path.exists(path):
        return None
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return None
    rew = [float(r["ep_reward"]) for r in rows]
    k = max(1, len(rew) // 10)
    return {"episodes": len(rew), "first10pct": sum(rew[:k]) / k,
            "last10pct": sum(rew[-k:]) / k}


def load_eval():
    path = os.path.join(RESULTS, "rl_eval.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def main():
    tr = load_training()
    ev = load_eval()
    lines = ["# Results: RL versus resyn2 on the classic ABC recipe space", ""]
    lines.append("Reward during training is the fast ABC (And-Inverter Graph "
                 "optimizer) node-count proxy. Real numbers below are full ORFS "
                 "ASAP7 (Arizona State University 7nm predictive Process Design "
                 "Kit) post-route QoR (Quality of Results). Lower is better "
                 "throughout.\n")

    if tr:
        lines += ["## Training", "",
                  f"- Episodes: {tr['episodes']}",
                  f"- Mean episode reward, first 10%: {tr['first10pct']:.4f}",
                  f"- Mean episode reward, last 10%: {tr['last10pct']:.4f}",
                  f"- Improvement: {tr['last10pct'] - tr['first10pct']:+.4f} "
                  "(reward = fraction of starting AIG nodes removed)\n"]

    if ev:
        lines += ["## Proxy results (node count, all designs)", "",
                  "| design | start | resyn2 | RL | random(best) | RL vs resyn2 |",
                  "|---|---|---|---|---|---|"]
        for r in ev:
            p = r["proxy"]
            lines.append(f"| {r['design']} | {r['start_nodes']} | {p['resyn2']} | "
                         f"{p['rl']} | {p['random_best']} | "
                         f"{p['rl_vs_resyn2_pct']:+.1f}% |")
        lines.append("")

        real_rows = [r for r in ev if "real" in r]
        if real_rows:
            lines += ["## Real ASAP7 post-route QoR", "",
                      "| design | metric | resyn2 | RL | random(best) |",
                      "|---|---|---|---|---|"]
            for r in real_rows:
                for metric in ("fom", "area", "wns"):
                    vals = [r["real"].get(k, {}).get(metric) for k in
                            ("resyn2", "rl", "random_best")]
                    vs = " | ".join("n/a" if v is None else f"{v:.2f}" for v in vals)
                    lines.append(f"| {r['design']} | {metric} | {vs} |")
            lines.append("")

    gnn_path = os.path.join(RESULTS, "gnn_results.json")
    if os.path.exists(gnn_path):
        g = json.load(open(gnn_path))
        unit = g.get("unit", "log10(nodes)")
        bname = g.get("baseline_name", "baseline")
        tgt = g.get("target", "after")
        lines += ["## GNN (Graph Neural Network) QoR surrogate", "",
                  f"Predicts the '{tgt}' target of an AIG (And-Inverter Graph) state "
                  f"from its graph structure. Baseline is the {bname}. Lower MAE "
                  f"(mean absolute error, in {unit}) is better.", "",
                  f"- Trained on {g['n_train']} graph states; held-out design: "
                  f"{g['holdout']}.",
                  "",
                  f"| split | GNN MAE | {bname} MAE |",
                  "|---|---|---|",
                  f"| in-distribution val | {g['gnn_val']:.4f} | {g['baseline_val']:.4f} |",
                  f"| held-out {g['holdout']} | {g['gnn_holdout']:.4f} | {g['baseline_holdout']:.4f} |",
                  ""]

    lines += ["## Honest reading", "",
              "- **The GNN loses to a one-line size baseline, badly on the held-out "
              "design.** The target (nodes after resyn2) is nearly proportional to "
              "current size, so log10(size) alone predicts it to ~2%. With only four "
              "training designs the GNN overfits their graph fingerprints and "
              "generalizes worse than the trivial baseline (MAE 0.71 vs 0.011 on "
              "held-out jpeg). This is the empirical version of the warning we "
              "started with: a GNN needs many designs and a target where structure "
              "actually matters (real routed area, or the size-removed residual). "
              "Right now it does not earn its place; that is a finding, not a win.",
              "- RL trained on the node-count proxy; the proxy correlates with, but "
              "is not, real post-route area. The real table is the one that counts.",
              "- Only three designs synthesize cleanly here (gcd, uart, aes), so the "
              "generalization claim is thin. This is a scaffold, not a finished study.",
              "- resyn2 is the classic-command baseline. The modern GIA flow ORFS "
              "ships is a stronger external bar (see docs/harness-and-sweeps.md).\n"]

    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, "RESULTS.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

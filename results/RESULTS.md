> **Prior work (proxy-metric era).** This documents the earlier reinforcement-learning study graded largely on the fast ABC (And-Inverter Graph optimizer) node-count proxy, on a 3-design proxy-extraction subset. The current real-QoR (Quality of Results) results on the full 9-design corpus are in [HEADLINE.md](HEADLINE.md) (Goal 1) and [PREDICTOR.md](PREDICTOR.md) (Goal 2). Kept for provenance.

# Results: RL versus resyn2 on the classic ABC recipe space

Reward during training is the fast ABC (And-Inverter Graph optimizer) node-count proxy. Real numbers below are full ORFS ASAP7 (Arizona State University 7nm predictive Process Design Kit) post-route QoR (Quality of Results). Lower is better throughout.

## Training

- Episodes: 4180
- Mean episode reward, first 10%: 0.0929
- Mean episode reward, last 10%: 0.1046
- Improvement: +0.0117 (reward = fraction of starting AIG nodes removed)

## Proxy results (node count, all designs)

| design | start | resyn2 | RL | random(best) | RL vs resyn2 |
|---|---|---|---|---|---|
| gcd | 389 | 357 | 350 | 349 | -2.0% |
| uart | 753 | 700 | 687 | 669 | -1.9% |
| aes | 17762 | 17289 | 16936 | 16921 | -2.0% |

## Real ASAP7 post-route QoR

| design | metric | resyn2 | RL | random(best) |
|---|---|---|---|---|
| gcd | fom | 80.34 | 67.74 | 73.41 |
| gcd | area | 59.53 | 64.14 | 63.26 |
| gcd | wns | -20.81 | -3.60 | -10.14 |
| uart | fom | 139.22 | 141.81 | 151.08 |
| uart | area | 115.14 | 109.57 | 112.28 |
| uart | wns | -24.08 | -32.24 | -38.80 |

## GNN (Graph Neural Network) QoR surrogate

Predicts log10(node count after resyn2) of an AIG (And-Inverter Graph) state from its graph structure. Baseline is a size-only linear fit. Lower MAE (mean absolute error, in log10 units) is better.

- Trained on 480 graph states; held-out design: jpeg.

| split | GNN MAE | size-baseline MAE |
|---|---|---|
| in-distribution val | 0.0242 | 0.0076 |
| held-out jpeg | 0.7142 | 0.0110 |

## Honest reading

- **The GNN loses to a one-line size baseline, badly on the held-out design.** The target (nodes after resyn2) is nearly proportional to current size, so log10(size) alone predicts it to ~2%. With only four training designs the GNN overfits their graph fingerprints and generalizes worse than the trivial baseline (MAE 0.71 vs 0.011 on held-out jpeg). This is the empirical version of the warning we started with: a GNN needs many designs and a target where structure actually matters (real routed area, or the size-removed residual). Right now it does not earn its place; that is a finding, not a win.
- RL trained on the node-count proxy; the proxy correlates with, but is not, real post-route area. The real table is the one that counts.
- Only three designs synthesize cleanly here (gcd, uart, aes), so the generalization claim is thin. This is a scaffold, not a finished study.
- resyn2 is the classic-command baseline. The modern GIA flow ORFS ships is a stronger external bar (see docs/archive/harness-and-sweeps.md).

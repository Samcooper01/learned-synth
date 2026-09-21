> **Prior work (proxy-metric era).** Greedy picker on the ABC node-count proxy. The current real-QoR predictor / route-pruning result is in [PREDICTOR.md](PREDICTOR.md). Kept for provenance.

# From predictor to picker: does the GNN choose good transforms?

## Goal

Turn the GNN (Graph Neural Network) value model (a good *judge* of AIG (And-Inverter
Graph) states) into a *picker* that actually chooses the sequence of transforms.
One-step lookahead: at each step apply every classic transform, score each
resulting state, keep the best, repeat.

Two scorers, plus the fixed `resyn2` baseline:
- **greedy-immediate**: score by the actual node count of each candidate (measured
  directly, no GNN).
- **GNN-lookahead**: score by `current_nodes x (1 - GNN-predicted reachable
  reduction)`.

## Results (final proxy node count on held-out designs; lower is better)

| design | resyn2 | greedy-immediate | GNN-lookahead |
|---|---|---|---|
| mult_18 | 2596 | 2595 | 2604 |
| addchain_24 | 2847 | **2714 (-4.7%)** | 3130 |
| decoder_9 | 1022 | **1022** | 1532 (stuck) |
| cmptree_24 | 3090 | **3055** | 3056 |
| lfsr_64 | 73 | **73** | 136 (stuck) |
| muxtree_7 | 6096 | 6096 | 6096 |
| crossbar_16 | 5760 | 5760 | 5760 |
| xortree_48 | 4512 | 4512 | 4512 |

## Findings

1. **greedy-immediate is a real, working picker.** It matches or beats `resyn2` on
   every design, best case 4.7% fewer nodes (addchain). It needs no GNN and no
   learning - just one-step lookahead scored by the actual proxy.
2. **The GNN-lookahead picker fails.** On compressible designs (decoder, lfsr) it
   stalls at the starting node count, choosing a no-op transform repeatedly.
3. **Incompressible designs tie.** muxtree/crossbar/xortree are already minimal
   after `aigmap`, so no method reduces them - correct, not a failure.

## Why the GNN picker fails (the real lesson)

The GNN predicts *reachable* value - the eventual optimum. But that value is nearly
**invariant to progress**: every state on the path to the optimum has roughly the
same reachable value. So `predicted_final` is nearly constant across candidates and
gives the greedy picker **no gradient to descend**. It cannot tell a real-progress
move from a no-op, so it drifts and stalls.

This is prediction versus control. A good *judge* of states is not automatically a
good greedy *picker*. Greedy needs an *immediate-progress* signal (which
greedy-immediate has and the reachable-value does not). The GNN's value prediction
is genuinely good (it predicts reachable reduction ~4-5x better than baseline); it
is simply the wrong quantity to greedily descend.

## What this means for where a GNN picker is actually worth it

- **On the proxy, a GNN picker adds nothing.** greedy-immediate measures each
  candidate's node count for free and works. There is no expensive quantity to
  predict.
- **A GNN picker earns its place only on an expensive objective**, above all
  **real routed area / QoR (Quality of Results)**, where measuring each candidate
  needs a full place-and-route. There a GNN predicting per-candidate quality guides
  a search that could not otherwise afford to look. That requires the real-area
  target and is the genuine next step.
- **The correct way to use a value predictor for control is value iteration / RL
  (Reinforcement Learning)** - learn cost-to-go under the policy, with reward credit
  assignment - which is exactly what the RL policy elsewhere in this project does.
  The greedy-value shortcut tried here is the naive version, and it does not work.

## Honest bottom line

We now have a working non-learned picker (greedy-immediate, beats `resyn2` by up to
4.7%) and a clear, demonstrated reason the naive GNN picker does not work. The GNN
remains an excellent state *judge*; making it a *picker* needs either an expensive
objective it can predict cheaply, or proper RL value iteration - not one-step greedy
on a reachability value.

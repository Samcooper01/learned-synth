> **Prior work (proxy-metric era).** GNN (Graph Neural Network) surrogate on the ABC node-count proxy. The current real-QoR predictor result is in [PREDICTOR.md](PREDICTOR.md). Kept for provenance.

# GNN (Graph Neural Network) surrogate: when does it earn its place?

## Question

Can a GNN read an AIG (And-Inverter Graph) state's structure and predict how much
`resyn2` will optimize it, better than a trivial baseline? The first attempt (on
five ORFS designs, predicting node count after `resyn2`) failed: the target was
size-dominated, so a one-line size fit won and the GNN overfit with too few
designs. This study fixes both problems and finds exactly where the GNN wins.

## What changed

1. **A structure-sensitive, size-invariant target.** Predict the *reduction
   fraction* `(nodes_now - nodes_after_resyn2) / nodes_now`, not absolute size.
   The baseline is no longer "size" (useless for a normalized target) but "predict
   the training-set mean." The GNN beats that only by reading structure.
2. **Extreme, controlled structure.** Eight synthetic microbenchmarks with
   deliberately extreme structural signatures (deep arithmetic `mult`/`addchain`,
   shallow high-fanout `muxtree`/`crossbar`/`decoder`, linear `xortree`, deep
   comparison `cmptree`, sparse-sequential `lfsr`). Depth/size ranges 70x across
   them; max fanout 18 to 2055.
3. **Minimal Yosys pre-optimization** so `resyn2` has real headroom. The reduction
   target now spans 0% to 47% across structures (vs 1-3% on the pre-optimized ORFS
   designs), and it is clearly structure-driven.
4. **Size variants.** Each structure type is generated at three sizes (24 designs
   total), so we can hold out a *size* (seen type, unseen scale) separately from a
   *type* (unseen structure).

## Results (MAE of the reduction fraction; lower is better)

| regime | GNN | mean-baseline | GNN vs baseline |
|---|---|---|---|
| in-distribution (held-out states of seen designs) | 0.0063 | 0.057 | **~9x better** |
| size-generalization (unseen size of a seen type) | 0.0113 | 0.053 | **~4.7x better** |
| type-generalization (an entirely unseen structure type) | 0.131 | 0.021 | ~6x worse |

## Reading

- **The GNN earns its place.** In-distribution it predicts the optimization
  outcome ~9x better than the baseline, purely from graph structure. Structure
  carries real, learnable signal for how optimizable an AIG state is.
- **It generalizes across scale within a structure family.** Held out the largest
  size of every type, trained only on smaller ones, and it still beats the
  baseline ~4.7x. It learned structure-type response independent of size, which is
  the useful kind of generalization.
- **It does not extrapolate to a novel structure type.** Hold out every size of
  `cmptree` (a deep comparator chain unlike any training design) and the GNN is
  ~6x worse than just guessing the mean. With seven other types seen, an eighth,
  structurally-unrelated one is out of distribution.

## The honest one-line conclusion

A GNN reads AIG structure well enough to predict optimization outcome and to
generalize across the *scale* of a structure it has seen, but it needs structural
*coverage* to generalize to new structure types. The practical implication for the
larger project: a GNN surrogate is worth using once the training corpus spans the
structure families you will actually synthesize; it is not a substitute for that
coverage.

## Reproduce

```
python3 harness/gnn_data.py --source micro --preopt min --sized \
  --designs mult addchain muxtree decoder xortree cmptree crossbar lfsr \
  --per-design 100 --out models/gnn_sized_dataset.pkl
# in-distribution / size-generalization: hold out largest size of each type
python3 harness/gnn_train.py --data models/gnn_sized_dataset.pkl --target reduction \
  --holdout mult_18 addchain_24 muxtree_7 decoder_9 xortree_48 cmptree_24 crossbar_16 lfsr_64
# type-generalization: hold out a whole type
python3 harness/gnn_train.py --data models/gnn_sized_dataset.pkl --target reduction \
  --holdout cmptree_12 cmptree_18 cmptree_24
```

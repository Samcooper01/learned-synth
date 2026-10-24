# learned-synth

**Is the standard recipe for open-source logic synthesis good enough? For most
designs, it can be improved: on 6 of 9 designs, a recipe chosen for that design beats
the standard recipe, `resyn2`, with up to 5.8% less chip area at the same clock speed,
verified by full chip layouts.**

<p align="center">
  <a href="https://samcooper01.github.io/learned-synth/"><img src="docs/banner.png" width="800" alt="Project page: Is the standard recipe for open-source logic synthesis good enough? A better recipe on 6 of 9 designs. Read the walkthrough."></a>
  <br>
  <b><a href="https://samcooper01.github.io/learned-synth/">&#8594; Read the full walkthrough</a></b>
</p>

Logic synthesis optimizes a design's logic one small step at a time, following a
recipe. [Yosys](https://yosyshq.net/yosys/) hands this job to
[ABC (And-Inverter Graph optimizer)](https://github.com/berkeley-abc/abc), and the
recipe never changes: a tiny controller and a large processor get exactly the same
steps. [`resyn2`](https://github.com/berkeley-abc/abc/blob/master/abc.rc#L111) is the
standard hand-tuned recipe that ships with ABC. This
project builds new recipes from the same classic transforms and grades every result on
a full chip layout through sign-off, with the open [OpenROAD](https://theopenroadproject.org/)
flow ([OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts))
on the [ASAP7 (Arizona State University 7nm predictive Process Design Kit)](https://github.com/The-OpenROAD-Project/asap7)
technology, instead of on the usual gate-count shortcut.

![results](docs/results.png)

## The project in brief

1. **Machine learning on a proxy metric.** A PPO (Proximal Policy Optimization)
   reinforcement learning agent that builds a recipe one transform at a time, rewarded
   by AIG (And-Inverter Graph) node count; a GNN (Graph Neural Network) surrogate that
   predicts how much of an AIG `resyn2` would remove; and a greedy
   policy that picks each transform by the GNN's prediction.
   The learned recipes were then checked against post-route QoR (Quality of Results).
2. **Sign-off-graded design space exploration.** A harness that runs any recipe
   through the full RTL (Register Transfer Level)-to-sign-off flow (synthesis,
   placement, CTS (Clock Tree Synthesis), routing) at an iso-timing operating point: a
   per-design clock constraint calibrated so `resyn2` sits at near-zero slack. 25
   random recipes plus `resyn2` per design, 234 full layouts in total.
3. **A low-cost QoR predictor for search pruning.**
   Post-synthesis cell area, available in seconds, ranks candidate recipes before place
   and route, so only the top few are laid out.
4. **Surrogate-guided evolutionary search.** A genetic algorithm (tournament
   selection, crossover, mutation) that uses the post-synthesis surrogate as its
   fitness function, about 180 evaluations per design, then verifies its top 3
   candidates post-route.

## Results

| Design | Size (cells) | Best recipe versus `resyn2` |
|---|---|---|
| gcd | ~400 | 5.8% less area |
| jpeg | ~58,000 | 2.2% less area |
| ethmac | ~56,000 | 2.1% less area |
| riscv32i | ~8,600 | 0.8% less area, and meets timing where `resyn2` misses |
| mock-alu | ~11,000 | 0.7% less area, and meets timing where `resyn2` misses |
| mock-cpu | ~39,000 | 0.2% less area |
| aes | ~14,000 | no better recipe (a near miss: 5% smaller, under 1% of the clock late) |
| uart | ~750 | no better recipe |
| ibex | ~17,000 | no better recipe |

Every number comes from a full layout to sign-off at each design's iso-timing
clock: a recipe counts as better only if it meets timing and uses less area than
`resyn2` on the finished layout.

## How it works

1. **Recipe injection** ([patch_orfs.py](harness/patch_orfs.py)): a reversible patch
   lets the flow run any recipe file.
2. **Harness** ([harness.py](harness/harness.py)): `run_recipe(design, recipe)` runs
   the full flow and records area, timing and power.
3. **Design set** ([probe_designs.py](harness/probe_designs.py)): 9 designs, from 418
   to 58,336 cells.
4. **Iso-timing clocks** ([calibrate_clocks.py](harness/calibrate_clocks.py)): each
   design's clock is calibrated so `resyn2` just meets timing.
5. **Sweep** ([labelsweep.py](harness/labelsweep.py)): `resyn2` plus 25 random recipes
   per design, 234 layouts and about 79 hours of compute.
6. **Memory-aware runner** ([loadmanaged_rerun.py](harness/loadmanaged_rerun.py)):
   starts a layout only when it fits in free memory.
7. **Predictor and search** ([predict_qor.py](harness/predict_qor.py),
   [flagship_search.py](harness/flagship_search.py)): ranks recipes by post-synthesis
   area and runs the genetic algorithm.

## Repository map

| Path | What |
|---|---|
| `docs/` | the project page and its images, plus a walkthrough of the default flow |
| `harness/harness.py` | runs one recipe through the full flow; the other scripts loop over it |
| `harness/` pipeline scripts | design selection through directed search, in the order under Reproduce |
| `harness/` `aig*`, `rl_env`, `train_rl`, `eval_policy`, `gnn_*`, `picker` | the earlier machine-learning studies |
| `results/` | every data file and write-up |
| `models/` | trained weights from the machine-learning studies |

## Reproduce

Needs [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
with the ASAP7 platform (point `LEARNED_SYNTH_ORFS` at it), plus the Python packages in
[requirements.txt](requirements.txt). From `harness/`, run in order:

```bash
python3 probe_designs.py
python3 baseline.py
python3 calibrate_clocks.py
python3 labelsweep.py --n 25 --force-classic-abc
python3 analyze.py
python3 predict_qor.py
python3 flagship_search.py --designs riscv32i aes uart ibex --pop 20 --gens 12
python3 make_figure.py
```

## Limitations

- The search optimizes area only, so its smallest recipes tend to miss timing.
- Each search ran once, and random sampling never got the same budget.
- Nine designs are too few to predict a good recipe for a brand-new design.
- riscv32i's timing is noisy, so its result is the least clean.

## Future work

1. Close near misses like aes with extra timing repair.
2. Repeat each search with more seeds and an equal-budget random baseline.
3. Add a post-synthesis timing estimate to the search score.
4. Run some layouts during the search, not only at the end.
5. Train a reinforcement learning policy on the real sign-off result.
6. Add more designs.

## Design detail: where the first logic graph comes from

Yosys hands the design's combinational logic to ABC, which turns it into an AIG and
runs the recipe on it. The Yosys front end is held fixed across recipes, so every
recipe starts from the same graph. More in [docs/default-abc-flow.md](docs/default-abc-flow.md).

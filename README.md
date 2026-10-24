# learned-synth

**Searching for logic-synthesis recipes that beat `resyn2`, the standard recipe of
this flow's logic optimizer, graded on real chip sign-off (post-place-and-route), not
proxy metrics.**

**Project page (the walkthrough, with diagrams):** https://samcooper01.github.io/learned-synth/

The open RTL (Register Transfer Level) to layout flow optimizes every design's logic
with one fixed recipe of ABC (And-Inverter Graph optimizer) transforms, the same for a
tiny controller and a large processor. `resyn2` is the standard hand-tuned recipe
that ships with ABC (And-Inverter Graph optimizer), built from the same classic
transforms this project searches over, so it is the baseline every result is compared
against. This project searches for a better per-design transformation sequence and measures the
payoff where it actually counts: post-detailed-route area at matched timing, produced
by the real OpenROAD flow on the ASAP7 (Arizona State University 7nm predictive
Process Design Kit) platform.

![results](docs/results.png)

## Headline results

Measured on 9 designs (gcd, uart, aes, ibex, jpeg, ethmac, riscv32i, mock-alu,
mock-cpu), every recipe run through the full flow at each design's matched-delay
clock, 234 clean place-and-route runs.

- **Goal 1 - `resyn2` is beatable.** A searched recipe beats `resyn2` on **5 of 9
  designs, by up to 5.8% cell area at matched delay** (real post-route sign-off), with
  pure random search. resyn2 is not optimal per design. See
  [results/HEADLINE.md](results/HEADLINE.md).
- **Goal 2 - the search is cheap.** A recipe's post-synthesis area predicts its
  post-route area strongly (Spearman +0.79 within a design), so recipes can be ranked
  after cheap synthesis and only the best few sent to full routing. **Routing only the
  top-3 of 26 candidates recovers 89% of the achievable area gain while skipping 88%
  of the place-and-route runs.** See [results/PREDICTOR.md](results/PREDICTOR.md).
- **Goal 3 (flagship) - directed search reaches recipes random misses.** A genetic
  algorithm over recipes with a cheap synthesis-only fitness found, on **riscv32i**, a
  recipe that **meets timing where resyn2 itself fails** and uses less area - a legal
  solution neither resyn2 nor random search reached. It also surfaced an honest limit:
  a pure area objective overshoots into timing violation on the other tight designs, so
  the search needs a timing-aware fitness (the concrete next step). See
  [results/FLAGSHIP.md](results/FLAGSHIP.md).

## Why this is the interesting version of the problem

Almost all recipe-learning work grades on AIG (And-Inverter Graph) node count and
logic depth, because the authors have no downstream flow. Grading on real
post-technology-mapping and post-route Quality of Results (QoR) is the differentiator,
and it changes the answer: the project's own earlier proxy-only study is kept as
[prior work](results/RESULTS.md) precisely to show the gap. The open OpenROAD plus
ASAP7 flow turns into a label factory that emits exactly the sign-off signal the field
usually lacks.

## How it works

1. **Recipe injection ([harness/patch_orfs.py](harness/patch_orfs.py)).** A reversible
   one-line patch makes the flow honor an `ABC_SCRIPT` override, so any recipe is just
   a text file fed to the classic `abc -script` path. (Three designs route through a
   newer `abc_new` path that ignores the override; `--force-classic-abc` keeps them on
   the classic path - see [results/HEADLINE.md](results/HEADLINE.md).)
2. **The harness ([harness/harness.py](harness/harness.py)).** `run_recipe(design,
   recipe)` runs the full flow and scrapes post-route area, timing, and power into one
   record. Everything else is a loop over this.
3. **Matched-delay clocks ([harness/calibrate_clocks.py](harness/calibrate_clocks.py)).**
   To compare area fairly, each design's clock is calibrated so `resyn2` sits at its
   timing wall (Worst Negative Slack near zero). Area is only comparable at a common
   timing bar. Loosening the clock does not help: the tool simply optimizes less and
   the delay grows to fill the slack ([results/CLOCKS.md](results/CLOCKS.md)).
4. **The label factory ([harness/labelsweep.py](harness/labelsweep.py)).** For each
   design, `resyn2` plus 25 random recipes are run through the full flow at the
   matched-delay clock, logging real QoR per recipe. This is both the Goal 1
   leaderboard and the Goal 2 training data.
5. **The predictor ([harness/predict_qor.py](harness/predict_qor.py)).** A cheap,
   synthesis-only signal ranks recipes so only the top few are routed.

There is also a load-aware runner ([harness/loadmanaged_rerun.py](harness/loadmanaged_rerun.py))
that sizes route concurrency to available memory, so the sweeps can share a machine
with other jobs without thrashing.

## Repository map

| path | what |
|---|---|
| `harness/harness.py` | `run_recipe(design, recipe) -> real post-route QoR` |
| `harness/recipes.py` | classic-ABC recipe representation + random generator |
| `harness/patch_orfs.py` | reversible `ABC_SCRIPT` override into the flow |
| `harness/probe_designs.py` | which designs synthesize cleanly (design curation) |
| `harness/baseline.py` | `resyn2` baseline across the corpus (Rung 1) |
| `harness/calibrate_clocks.py` | per-design matched-delay clock calibration |
| `harness/labelsweep.py` | the label factory: recipes -> real QoR |
| `harness/analyze.py` | Goal 1 matched-delay leaderboard |
| `harness/predict_qor.py` | Goal 2 predictor + route-budget skip-curve |
| `harness/flagship_search.py` | Goal 3 directed (genetic-algorithm) recipe search |
| `harness/make_figure.py` | the results figure above |
| `results/DESIGN_SET.md`, `BASELINE.md`, `CLOCKS.md` | corpus, baseline, clock calibration |
| `results/HEADLINE.md`, `PREDICTOR.md`, `FLAGSHIP.md` | the Goal 1, 2, and 3 results |
| `results/RESULTS.md`, `GNN_STUDY.md`, `PICKER_STUDY.md` | prior proxy-metric studies |

## Reproduce

Requires an OpenROAD-flow-scripts checkout with the ASAP7 platform (set
`LEARNED_SYNTH_ORFS`, or edit `patch_orfs.DEFAULT_ORFS`), plus `numpy` and
`matplotlib`.

```bash
cd harness
python3 probe_designs.py            # which designs synthesize cleanly
python3 baseline.py                 # resyn2 baseline (full flow)
python3 calibrate_clocks.py         # matched-delay clocks -> results/clocks.json
python3 labelsweep.py --n 25 --force-classic-abc   # the label factory
python3 analyze.py                  # Goal 1 leaderboard
python3 predict_qor.py              # Goal 2 predictor + skip-curve
python3 flagship_search.py --designs riscv32i --pop 20 --gens 12 --verify-k 3   # Goal 3 directed search
python3 make_figure.py              # regenerate docs/results.png
```

## Honest limitations

- **The predictor prunes; it does not invent wins.** On tight designs where no random
  recipe beats `resyn2`, there is no gain for the ranker to capture. The Goal 3 directed
  search (see [results/FLAGSHIP.md](results/FLAGSHIP.md)) does reach a legal win on
  riscv32i that random missed, but its area-only objective overshoots timing on the
  other tight designs. The concrete next step is a timing-aware fitness (minimize area
  subject to meeting timing), which needs a cheap post-synthesis slack signal the open
  flow does not currently expose, and then a reinforcement-learning policy over the
  recipe space with a sign-off-graded, timing-aware reward.
- **9 designs is enough for per-design results, thin for cross-design generalization.**
  The signal lives in what a recipe does to a specific netlist, not in the recipe
  string, so predicting for a brand-new design would need a much larger design corpus.
- **riscv32i** is noisy at its timing wall (many balanced critical paths), so its
  matched-delay comparison is the least clean of the nine.

## Design detail: where the first AIG comes from

Yosys parses and bit-blasts the RTL and hands the entire combinational network to
ABC (And-Inverter Graph optimizer); ABC builds the AIG (And-Inverter Graph) via
structural hashing and runs the recipe on it. The starting AIG depends on how Yosys
pre-optimized upstream, so the Yosys front-end script is held fixed across recipes,
and registers are excluded (the recipe reshapes combinational logic between
flip-flops). See [docs/default-abc-flow.md](docs/default-abc-flow.md) and
[docs/harness-and-sweeps.md](docs/harness-and-sweeps.md) for the full walkthrough.

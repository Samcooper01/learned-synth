# harness

The scripts behind every result in this repository. Each one runs a recipe through
the real OpenROAD Flow Scripts flow on the ASAP7 (Arizona State University 7nm
predictive Process Design Kit) platform, or analyzes the results. Point them at your
flow checkout with `LEARNED_SYNTH_ORFS` (or `--orfs`).

## The pipeline, in run order

| Script | What it does | Writes |
|---|---|---|
| `patch_orfs.py` | reversible patch so the flow runs a recipe file (`--revert` undoes it) | the flow's `synth_preamble.tcl` |
| `recipes.py` | the recipe representation, `resyn2`, and the random-recipe generator | (library) |
| `harness.py` | `run_recipe(design, recipe)`: one recipe through the full flow, metrics scraped | (library and command line) |
| `probe_designs.py` | which example designs synthesize cleanly | `results/design_probe_*.jsonl` |
| `baseline.py` | `resyn2` through the full flow on every design | `results/baseline_resyn2_*.jsonl` |
| `calibrate_clocks.py` | each design's iso-timing clock, by repeated full layouts | `results/clocks.json` |
| `labelsweep.py` | `resyn2` plus random recipes per design at that clock | `results/labelsweep_*.jsonl` |
| `loadmanaged_rerun.py` | the same sweep, launching layouts only when memory allows | `results/labelsweep_lm_*.jsonl` |
| `analyze.py` | the per-design leaderboard against `resyn2` | (printed) |
| `predict_qor.py` | how well post-synthesis area ranks recipes, and the skip curve | (printed) |
| `flagship_search.py` | the genetic-algorithm search, with its top picks laid out | `results/flagship_*.json` |
| `make_figure.py` | the charts for the project page and README | `docs/*.png` |

## The earlier machine-learning studies

| Script | What it does | Writes |
|---|---|---|
| `aig.py` | fast gate-count scoring of a recipe, without layout | (library) |
| `rl_env.py`, `train_rl.py`, `eval_policy.py` | the reinforcement learning agent: environment, training, evaluation | `models/ppo_abc.zip`, `results/rl_eval.json` |
| `aig_graph.py`, `gnn_data.py`, `gnn_train.py` | the graph neural network: graph extraction, dataset, training | `models/*.pt`, `results/gnn_results.json` |
| `picker.py` | step-by-step recipe pickers, model-guided and plain | `results/picker_results.json` |
| `make_report.py` | the write-up for the agent study | `results/RESULTS.md` |
| `overnight.sh`, `gnn_run.sh` | the run scripts for those studies | logs |
| `sweep.py` | the first sweep driver, before `labelsweep.py` | `results/<design>_*.jsonl` |
| `microbench/` | the 8 small test designs used by the graph neural network study | |

## How a recipe gets into the flow

The flow's synthesis step calls ABC (And-Inverter Graph optimizer) with a script file.
The patch adds one branch: if `ABC_SCRIPT` is set, that file is used instead. The
harness writes each recipe to a file and passes its path. Two settings are forced so
every run is comparable:

- **`SYNTH_USE_SYN=0`**, which keeps synthesis on the classic path that the recipe
  file controls. Some designs ship with a newer path that ignores it.
- **One `FLOW_VARIANT` per recipe**, named from a fingerprint of its steps, so each
  recipe builds fresh in its own folder and runs can go in parallel.

`labelsweep.py --force-classic-abc` also clears two settings that would otherwise send
three designs (ibex, mock-alu, riscv32i) down a path that ignores the recipe.

## Metrics recorded

From the flow's final report (`logs/asap7/<design>/<variant>/6_report.json`): area in
square micrometers, worst and total negative slack in picoseconds, and total power in
watts. Post-synthesis area comes from `1_synth.json`. All raw metrics are kept, so the
definition of a win can change without re-running anything.

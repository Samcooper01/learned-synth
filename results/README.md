# results

The data and write-ups behind every number on the [project page](https://samcooper01.github.io/learned-synth/).
The write-ups still use the project's original working labels (Goal 1, 2 and 3).

| Write-up | What it covers | Page section |
|---|---|---|
| [RESULTS.md](RESULTS.md) | the reinforcement learning agent, graded on gate count and then on the real chip | 3, first attempt |
| [GNN_STUDY.md](GNN_STUDY.md) | the graph neural network and its baselines | 3, first attempt |
| [PICKER_STUDY.md](PICKER_STUDY.md) | letting the model choose the steps, against a plain gate-count picker | 3, first attempt |
| [DESIGN_SET.md](DESIGN_SET.md) | which designs were used and why | 7, engineering |
| [BASELINE.md](BASELINE.md) | `resyn2` on every design at its shipped clock | 7, engineering |
| [CLOCKS.md](CLOCKS.md) | the iso-timing clock calibration, and why a looser clock does not help | 4 and 7 |
| [HEADLINE.md](HEADLINE.md) | random recipes against `resyn2` on full layouts ("Goal 1") | 4, second attempt |
| [PREDICTOR.md](PREDICTOR.md) | post-synthesis area as a cheap ranking score ("Goal 2") | 5, the cost |
| [FLAGSHIP.md](FLAGSHIP.md) | the genetic-algorithm search ("Goal 3") | 6, the final method |

## Data files

| File | Contents |
|---|---|
| `labelsweep_dataset.jsonl` | all 234 layouts: one record per design and recipe |
| `baseline_resyn2_*.jsonl` | the `resyn2` baseline at shipped clocks |
| `clocks.json` | each design's iso-timing clock |
| `flagship_*.json` | the genetic-algorithm searches and their laid-out picks |
| `rl_eval.json`, `gnn_results.json`, `picker_results.json` | the machine-learning studies |

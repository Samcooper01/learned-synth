# learned-synth: project plan

## One-line thesis

The open synthesis flow runs a fixed ABC (And-Inverter Graph optimizer) script
for every design. Learn a better transformation sequence per design, and grade
it on real downstream QoR (Quality of Results) from OpenROAD on the ASAP7
(Arizona State University 7nm predictive Process Design Kit) flow, not on the
usual proxy metrics.

## Why this is worth doing

- The default ABC (And-Inverter Graph optimizer) recipes (`resyn2`, `resyn3`)
  are hand-tuned heuristics from the 2000s. They are not optimal for any
  specific netlist, and they were never tuned against a modern standard-cell
  library.
- Almost all prior recipe-learning work grades on AIG (And-Inverter Graph) node
  count and logic depth, because the authors have no downstream flow. Grading on
  real post-technology-mapping and post-detailed-route QoR (Quality of Results)
  is the differentiator, and the open OpenROAD + ASAP7 (Arizona State University
  7nm predictive Process Design Kit) flow makes it a label factory that produces
  exactly that signal.

## Differentiator, stated precisely

The novel-and-defensible piece is a QoR (Quality of Results) predictor that
prunes candidate recipes so the agent rarely pays for a full route, with the
whole search graded at real sign-off rather than at AIG (And-Inverter Graph)
proxy metrics. The reproducible open benchmark half is safe to publish as-is;
the predictor-pruned search is the part to run a patentability read on before
publishing or filing, and the employer invention-assignment question applies.

## The build, as a ladder (a result at every rung)

### Rung 0: the evaluation harness (the reusable asset)

A single command that takes `(design, ABC recipe)` and returns real QoR (Quality
of Results).

- Inputs: an RTL (Register Transfer Level) design, an ABC (And-Inverter Graph
  optimizer) recipe expressed as an ordered list of optimization commands.
- Pipeline: Yosys front end reads RTL and emits an AIG (And-Inverter Graph);
  ABC runs the recipe and does technology mapping to the ASAP7 (Arizona State
  University 7nm predictive Process Design Kit) standard-cell library; OpenROAD
  runs place and route.
- Outputs logged per run: area, worst-negative-slack and total-negative-slack
  timing, power, plus cheap proxies (AIG node count and depth) for comparison,
  plus wall-clock runtime of each stage.
- This harness is the load-bearing deliverable. Everything else consumes it.

### Rung 1: baselines

Record `resyn2` (and a couple of other fixed scripts) numbers across the design
set. This is the bar every learned recipe must beat.

### Rung 2: naive search (prove the reward has signal)

Random search and a genetic algorithm over recipe strings. If this already beats
the fixed script, the reward signal is real and the harder rungs are justified.
Report win rate and average QoR (Quality of Results) delta versus `resyn2`.

### Rung 3: the QoR (Quality of Results) predictor (the interesting engineering)

Train a model to predict downstream QoR from a candidate recipe plus cheap
features of the AIG (And-Inverter Graph), so the agent can rank and prune
candidates without paying for a full place and route each time.

- Start simple: a regressor on hand-built features (AIG size and depth after
  each transformation, design statistics).
- Then a GNN (Graph Neural Network) directly on the AIG (And-Inverter Graph) if
  the simple model leaves accuracy on the table.
- The headline is the prediction-to-skip-the-expensive-evaluation move: how much
  route budget the predictor saves at what accuracy cost.

### Rung 4 (optional flagship): reinforcement learning policy

A reinforcement-learning policy over the recipe action space (the roughly 7 to
10 ABC optimization commands), using the Rung 3 predictor as a fast critic. This
is the rung that turns a resume project into a paper.

## Design set

Start small and fixed for reproducibility: a handful of OpenROAD flow designs
and/or the EPFL and ISCAS combinational benchmarks. Expand only once the harness
is stable.

## Headline result to aim for

"Learned recipes beat the `resyn2` baseline by X% area at matched delay across N
designs, evaluated at real sign-off rather than proxy metrics, while the QoR
(Quality of Results) predictor cuts full-route evaluations by Y%."

## Stopping points

- Stop at Rung 2 and you have a legitimate, demonstrable result.
- Rung 3 is the strongest single talking point.
- Rung 4 is the flagship and the natural on-ramp to physically-aware synthesis
  (feeding placement feedback back into synthesis), which is deliberately out of
  scope for this repo.

## Out of scope (on purpose)

Timing-driven / physically-aware synthesis for Yosys. It is the larger gap
versus commercial tools, but it is a deep multi-stage integration with a fuzzy
success metric and a long time-to-first-result. This project is the on-ramp to
it, not the thing itself.

# Harness and sweeps (Rung 0, and what we actually launch)

This document pins down the concrete mechanics: how a searched recipe is injected
into the real flow on this machine, what a QoR (Quality of Results) number is, and
exactly which sweeps get launched and in what order. It reflects the classic-ABC
(And-Inverter Graph optimizer) command-space decision.

## The environment we are targeting (verified)

- **OpenROAD-flow-scripts (ORFS)**: `/home/sam/Geetus2.0/Flow/OpenROAD-flow-scripts`
  (with `env.sh`).
- **OpenROAD**: `.../tools/install/OpenROAD/bin/openroad`, version `26Q3-173`.
- **Yosys** (with ABC (And-Inverter Graph optimizer) bundled):
  `.../dependencies/bin/yosys`.
- **Platform**: ASAP7 (Arizona State University 7nm predictive Process Design Kit),
  a built-in ORFS platform.
- Not yet installed, and not needed for the first sweeps: FlowTune, and
  `torch_geometric` for the GNN (Graph Neural Network).

The whole RTL (Register Transfer Level) to GDS (Graphic Design System) flow already
runs here and emits metrics. The harness drives that, it does not rebuild it.

## How a recipe is injected (the mechanism)

ORFS synthesis (`flow/scripts/synth_preamble.tcl`) selects an ABC script *file* and
calls `abc -script <file> -liberty ... -constr ...`. The recipe is therefore just a
text file we generate. A tiny patch to honor an `ABC_SCRIPT` environment override
(or swapping the file per run) is all that is required. No code surgery.

**Every generated recipe file has three parts, and only the middle is searched:**

```
# prologue (fixed): build the AIG
strash

# optimization (SEARCHED): the classic-command sequence we vary
balance ; rewrite ; refactor ; rewrite -z ; balance ; ...

# epilogue (fixed): map to ASAP7 cells and finish, mirroring abc_area.script's tail
map ; topo ; buffer -c ; stime -c ; upsize -c ; dnsize -c
```

Holding the prologue and epilogue fixed keeps every comparison apples-to-apples and
guarantees a mapped netlist OpenROAD can place and route. `resyn2` is one specific
optimization middle, and it is our classic baseline.

## What a QoR (Quality of Results) number is

ORFS produces per-design metrics (area, worst-negative-slack and total-negative-
slack timing, power) that the harness scrapes into a single scalar figure of merit.

- **Default figure of merit**: at a fixed clock period (from the design's SDC
  (Synopsys Design Constraints)), minimize total cell area, with a large penalty
  when worst-negative-slack is below zero. In words: prefer timing-legal results,
  then prefer smaller area.
- Always log the raw components too (area, worst-negative-slack, total-negative-
  slack, power, runtime), so the figure of merit can be redefined later without
  re-running anything.

## The harness contract (Rung 0)

One command:

```
harness(design, recipe) -> { fom, area, wns, tns, power, runtime, mapped }
```

It writes the recipe file, runs ORFS synthesis plus place and route for the design,
scrapes the metrics, and returns the record. Everything else in this project is a
loop over this function.

## The sweeps, concretely, in launch order

1. **Baseline sweep.** Run each design in the set twice: once with the flow's real
   default (the GIA (the scalable And-Inverter Graph engine) `abc_speed.script`),
   and once with `resyn2` (the classic reference). This gives two honest bars:
   the flow's actual default, and the classic starting point our search improves on.
2. **Random classic-recipe sweep (the workhorse).** For each design, sample many
   random classic optimization middles, run the full flow, and log
   `(design, recipe) -> QoR`. This does double duty: it proves whether search beats
   the baselines at all, and it is the training dataset for the GNN QoR surrogate.
3. **FlowTune sweep (Approach A).** Per-design multi-armed-bandit search under a
   fixed budget, once FlowTune is installed and our OpenROAD objective is wired in
   as its custom evaluator.
4. **RL (Reinforcement Learning) training and hyperparameter sweep (Approach B).**
   Train the policy against the surrogate, then sweep its knobs (learning rate,
   reward shaping, recipe horizon), once `torch_geometric` and the surrogate exist.

**Cross-cutting knob sweeps** that apply to several of the above: maximum recipe
length, per-design search budget, the clock-period target, and the figure-of-merit
definition.

## The smallest thing runnable right now

Before OpenROAD is in the loop at all, a **proxy-only recipe sweep** is launchable
with just Yosys and its bundled ABC: search classic recipes and grade them on ABC-
level node count and logic depth instead of real QoR. This shakes out the search
harness and confirms search beats `resyn2` on the proxy, using nothing that is not
already installed. Then bolt OpenROAD on and swap the proxy grader for the real
figure of merit from ORFS.

## Open prerequisites before the real (OpenROAD-graded) sweeps

1. Curate a small fixed design set (start with a handful of ASAP7 ORFS example
   designs) and pin the Yosys front-end script so the starting AIG is stable.
2. Build the Rung 0 harness above (recipe-file injection, ORFS run, metrics scrape).
3. Then: baseline sweep, then the random sweep.

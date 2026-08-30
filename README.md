# learned-synth

Learning better logic-synthesis recipes for the open ASAP7 (Arizona State
University 7nm predictive Process Design Kit) flow, graded on real downstream
QoR (Quality of Results) instead of proxy metrics.

The open flow runs a fixed, hand-tuned ABC (And-Inverter Graph optimizer)
script (`resyn2`) for every design. This project learns a better transformation
sequence per design and measures the payoff at technology mapping and, where it
matters, at post-detailed-route sign-off using OpenROAD.

## How the flow gets to its first AIG (And-Inverter Graph)

Two tools split the work, and it is worth being precise about the boundary:
Yosys produces the bit-level logic, but the AIG (And-Inverter Graph) data
structure itself is built by ABC (And-Inverter Graph optimizer).

1. **Parse and elaborate (Yosys).** Read the Verilog, resolve parameters, unroll
   generate blocks, and build word-level operators (adders, multiplexers, and so
   on).
2. **Coarse synthesis (Yosys).** Optimize at the word level, then bit-blast:
   break those word-level operators down into single-bit generic gates and
   flip-flops.
3. **Handoff (Yosys `abc` pass).** Yosys separates the combinational logic from
   the registers and hands the *entire* combinational network between the
   registers to ABC (And-Inverter Graph optimizer) as a single multi-input,
   multi-output block. It is not handed over one cone at a time (see below).
4. **Build the first AIG (ABC).** ABC runs structural hashing (`strash`), which
   is the step that actually constructs the AIG (And-Inverter Graph): everything
   becomes 2-input AND nodes with complemented edges. This strashed graph is the
   first AIG.
5. **Optimize (ABC).** The `resyn2` recipe runs on that AIG. This is the step
   `learned-synth` replaces.

So Yosys hands over logic; ABC (And-Inverter Graph optimizer) turns it into an
AIG (And-Inverter Graph) and optimizes it. Two consequences that matter here:

- **The first AIG is not unique to the RTL (Register Transfer Level).** Its shape
  depends on how Yosys bit-blasted and pre-optimized upstream, so the Yosys
  front-end script must be held fixed when comparing recipes, or the recipes are
  not being compared on the same starting graph.
- **Registers are not in the AIG.** ABC (And-Inverter Graph optimizer) optimizes
  the combinational logic *between* flip-flops, so a recipe reshapes logic
  clouds, not the sequential structure.

### What "the combinational network" means, and why it is not one cone

A **logic cone** (a fan-in cone) is defined relative to one endpoint: pick a
flip-flop data input or a primary output, trace backward through the
combinational gates that feed it, and stop at every startpoint (a flip-flop
output or a primary input). Everything swept up along the way is that endpoint's
cone. A cone is therefore bounded by registers and ports, and it is exactly the
combinational cloud that one timing path lives in.

A real design has many cones, and they **overlap**: two endpoints usually share
gates in their fan-in. ABC (And-Inverter Graph optimizer) does not process these
one at a time. It ingests the whole combinational network as a single AIG
(And-Inverter Graph), and structural hashing (`strash`) merges the shared gates
so a node used by several cones exists only once. The recipe then optimizes that
whole shared graph globally.

The word "cone" also appears at a much smaller scale *inside* the recipe:
`rewrite` and `refactor` each grab a tiny local cut (a handful of nodes) around
one node, swap in a better implementation, and move on. So there are two scales:
the design-level fan-in cone (all of which ABC ingests at once), and the small
local cut the recipe edits during optimization.

See [PLAN.md](PLAN.md) for the full project plan,
[docs/default-abc-flow.md](docs/default-abc-flow.md) for a diagrammed walkthrough
of the default flow and the `resyn2` recipe this project replaces, and
[docs/experiment-pipeline.md](docs/experiment-pipeline.md) for the head-to-head
experiment (FlowTune search versus an RL (Reinforcement Learning) policy with a
GNN (Graph Neural Network)) and its training and testing pipelines.

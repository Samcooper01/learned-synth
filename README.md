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
   the registers and hands each combinational cone to ABC (And-Inverter Graph
   optimizer).
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

See [PLAN.md](PLAN.md) for the full project plan, and
[docs/default-abc-flow.md](docs/default-abc-flow.md) for a diagrammed walkthrough
of the default flow and the `resyn2` recipe this project replaces.

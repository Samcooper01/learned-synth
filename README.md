# learned-synth

Learning better logic-synthesis recipes for the open ASAP7 (Arizona State
University 7nm predictive Process Design Kit) flow, graded on real downstream
QoR (Quality of Results) instead of proxy metrics.

The open flow runs a fixed, hand-tuned ABC (And-Inverter Graph optimizer)
script (`resyn2`) for every design. This project learns a better transformation
sequence per design and measures the payoff at technology mapping and, where it
matters, at post-detailed-route sign-off using OpenROAD.

See [PLAN.md](PLAN.md) for the full project plan.

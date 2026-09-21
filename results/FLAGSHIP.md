# Goal 3 (flagship): directed recipe search

Random search (Goal 1) beats resyn2 on some designs by luck; the Goal 2 predictor
prunes the search cheaply. Goal 3 asks whether a *directed* search can beat resyn2 on
the tight designs where random found nothing legal - the designs where the feasible
region is small.

Method: a genetic algorithm over ABC (And-Inverter Graph optimizer) recipes, scored by
the cheap post-synthesis cell area (Spearman ~0.8 with routed area, and smaller for
timing-legal recipes). Population 20, 12 generations, ~180 synthesis evaluations per
design (each ~2-6 minutes of light, low-memory synthesis - no place-and-route in the
loop). The top-3 candidates by post-synth area are then route-verified through the
full flow. Run with `harness/flagship_search.py`; results in `results/flagship_*.json`.

Targeted the 4 tight designs where random search found no win.

## Result

| design | resyn2 (area / timing) | random best legal | directed search best legal | outcome |
|---|---|---|---|---|
| **riscv32i** | 2683.7 / **misses** (WNS -9.4) | 2717.2 (worse) | **2661.8, meets (WNS +11.5)** | **WIN** |
| aes | 1618.5 / meets (+1.3) | 1625.2 (worse) | none of top-3 meet timing | no win |
| uart | 107.0 / meets (+1.3) | 109.7 (worse) | none of top-3 meet timing | no win |
| ibex | 2558.3 / misses (-32) | 2588.9 | none of top-3 meet timing | no win |

**The win (riscv32i).** resyn2 itself misses timing at riscv32i's wall clock, and
random search found no legal recipe better than resyn2. Directed search found a recipe
that **both meets timing (WNS +11.5) and has smaller area (2661.8 vs 2683.7)** - a
legal solution where both resyn2 and random failed. That is the flagship's point:
directed search reaches a good corner of the recipe space that blind sampling misses.

## The honest finding (aes, uart, ibex)

On the other three, the directed search minimized post-synth area effectively (it
found recipes ~5% smaller than resyn2), but those recipes **miss timing at route**: on
aes it traded resyn2's +1.3 ps slack for -3.6 ps. Minimizing area alone overshoots
into timing violation on timing-tight designs. Post-synth area is a good ranker among
already-legal recipes (Goal 2), but a poor *objective* to minimize freely, because the
smallest-area restructurings are often the slowest.

The fix is a **timing-aware fitness**: minimize area subject to meeting timing, i.e.
`area + penalty * max(0, -slack)`. The obstacle is that the open flow does not expose a
cheap post-synthesis slack: `1_synth.json` has no timing, and ABC's mapper timing is
not captured in the logs. Getting there needs one of:
- a cheap post-synthesis static-timing pass (OpenROAD static timing on the
  pre-route netlist - optimistic without parasitics, so its predictiveness must be
  checked first), or
- capturing ABC's own post-mapping delay (it maps against the clock already), or
- a logic-depth proxy from the And-Inverter Graph.

## So what

Directed search demonstrably reaches legal recipes that random search and resyn2 miss
(riscv32i), so the search space has real structure worth exploiting. But a cheap,
purely area-based objective is not enough on timing-tight designs - it needs a timing
term. That is the concrete next step, and the natural on-ramp to a reinforcement-
learning policy over the recipe space with a timing-aware, sign-off-graded reward.

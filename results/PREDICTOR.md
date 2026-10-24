# A cheap QoR (Quality of Results) predictor that prunes the recipe search

The random-recipe study ([HEADLINE.md](HEADLINE.md)) showed a searched recipe can beat resyn2, but finding one by brute force means
a full place-and-route per candidate. This study is the project's differentiator: a
cheap predictor that ranks candidates so we pay for a full route on only the best few.

Reproduce with `python3 harness/predict_qor.py` on the 234-route dataset.

## The cheap signal: post-synthesis area predicts post-route area

Place-and-route is the expensive stage; synthesis is comparatively cheap. A recipe's
post-synthesis cell area (available after synthesis, before any routing) predicts its
post-route area strongly, within a design:

| design | Spearman(post-synth area, routed area) |
|---|---|
| ethmac | +0.958 |
| jpeg | +0.945 |
| riscv32i | +0.895 |
| gcd | +0.863 |
| aes | +0.845 |
| ibex | +0.836 |
| uart | +0.686 |
| mock-alu | +0.671 |
| mock-cpu | +0.377 |
| **mean** | **+0.786** |

So ranking the candidate recipes by their (cheap) synthesis result closely matches
ranking them by the (expensive) routed result. mock-cpu is the weak case: its recipes
barely move area (0.3% spread), so the ranking is noise-dominated but also low-stakes.

A leave-one-design-out ridge model on synthesis-only features (recipe command counts,
length, post-synth area) reproduces this ranking (mean per-design Spearman +0.59;
lower than the raw signal because predicting absolute area across designs of very
different scale is harder than the within-design ranking that matters for pruning).

## The payoff: route-budget-saved (skip-curve)

Rank each design's 26 recipes by post-synth area, route only the top-K, and keep the
best timing-legal result. Measured over the 5 designs where a recipe better than
resyn2 exists (gcd, jpeg, ethmac, mock-cpu, mock-alu):

| routes paid | route budget saved | achievable area gain captured | designs where resyn2 is beaten |
|---|---|---|---|
| top-1 / 26 | 96% | 76% | 4 / 5 |
| top-2 / 26 | 92% | 77% | 4 / 5 |
| **top-3 / 26** | **88%** | **89%** | **5 / 5** |
| top-5 / 26 | 81% | 92% | 5 / 5 |
| top-8 / 26 | 69% | 96% | 5 / 5 |

**Routing only the top-3 synthesis-ranked recipes recovers 89% of the achievable
area improvement and beats resyn2 on every improvable design, while skipping 88% of
the place-and-route runs.** That is the "predict to skip the expensive evaluation"
result the project set out to demonstrate.

## Honest limits

- **This prunes; it does not invent wins.** On the tight designs where no random
  recipe beats resyn2 (aes, uart, ibex, riscv32i), there is no gain for the ranker to
  capture. Extending wins to those designs needs a stronger search (directed or
  reinforcement-learning over the recipe space), not just a better ranker. That is the
  natural next step beyond this project's scope.
- **Recipe features alone are weak.** Predicting routed QoR from the recipe command
  mix without the synthesis result gives only ~+0.1 rank correlation: the signal lives
  in what the recipe *did to this netlist* (captured cheaply by post-synth area), not
  in the recipe string itself. This matches the earlier `GNN_STUDY.md` finding that
  structure, not recipe identity, carries the signal.
- **Timing legality** is assumed measured at route here. A fuller predictor would also
  predict meets-timing from a synthesis-stage timing estimate; that is not yet wired
  in.

## So what

Combined with the random-recipe result (resyn2 is beatable on 5/9 designs), this shows the search is
cheap to run: a synthesis-only ranker turns "route all 26 candidates" into "route the
best 3," an ~88% cut in place-and-route cost at ~90% of the benefit.

# Random recipes versus resyn2 at matched delay

The sweep ran resyn2 plus 25 random classic recipes through the full ORFS
(OpenROAD Flow Scripts) ASAP7 (Arizona State University 7nm predictive Process Design
Kit) flow on all 9 corpus designs, every recipe at that design's fixed wall clock
(resyn2 at Worst Negative Slack ~ 0; see `results/CLOCKS.md`). 234 clean routes, all 9
designs with recipes genuinely applied. Regenerate with `python3 harness/analyze.py`.

The comparison is iso-timing: an area win only counts if the recipe meets the same
timing bar resyn2 does. Lower area is better.

| design | recipes meeting timing | resyn2 area (um^2) | best area | delta vs resyn2 | # beating resyn2 |
|---|---|---|---|---|---|
| gcd | 21 | 58.1 | 54.7 | **-5.77%** | 8 |
| jpeg | 26 | 6757.6 | 6609.7 | **-2.19%** | 10 |
| ethmac | 2 | 8130.6 | 7960.8 | **-2.09%** | 1 |
| mock-alu | 12 | 1638.1 | 1626.6 | **-0.70%** | 10 |
| mock-cpu | 16 | 7013.8 | 6998.4 | **-0.22%** | 12 |
| uart | 4 | 107.0 | 107.0 | 0.00% | 0 |
| aes | 2 | 1618.5 | 1618.5 | 0.00% | 0 |
| ibex | 4 | 2558.3 | 2588.9 | +1.20% | 0 |
| riscv32i | 1 | 2683.7 | 2717.2 | +1.25% | 0 |

**Random search beats resyn2 on 5 of 9 designs, by up to 5.77% area at matched
delay** (mean across designs -0.95%). This is with pure random search, the weakest
possible optimizer, and it already shows resyn2 is not optimal per design.

## The abc_new data-validity fix

ibex, mock-alu and riscv32i initially produced identical area for every recipe: they
route synthesis through Yosys's `abc_new`/ABC9 path, which crops out `-script` and
ignores our recipe. Forcing the classic `abc -script` path (emptying
SWAP_ARITH_OPERATORS / SYNTH_WRAPPED_OPERATORS, the `--force-classic-abc` flag in
`labelsweep.py`) recovered all three. After the fix, mock-alu became a real -0.70%
win (10 recipes beat resyn2), and ibex / riscv32i give honest non-winning results
(they were artifacts before, now they are real).

## Reading

- **The win is real.** On gcd, jpeg, ethmac, mock-alu and mock-cpu a random classic
  recipe meets the same timing and uses less area than the hand-tuned resyn2.
- **Where random fails shows what comes next.** Two failure modes:
  1. *Tight designs* (aes 2, uart 4, ethmac 2, ibex 4, riscv32i 1 recipes meet
     timing): the feasible region is small, so random rarely lands a legal recipe.
     Finding one needs more candidates, which a predictor that ranks recipes before
     routing ([PREDICTOR.md](PREDICTOR.md)) makes affordable.
  2. *Already-strong resyn2* (ibex): recipes meet timing but none beat area, so
     beating it needs directed search, not more random samples.
- **riscv32i** is the noisy design: at its wall clock resyn2 itself sits at -9.4 ps,
  so almost nothing meets timing. Its area numbers are valid labels; it just is not a
  clean matched-delay win. A small timing margin would move it into the comparison.

## So what

resyn2 is beatable, even by random search, on the majority of the corpus. The next
steps are a cheap QoR (Quality of Results) predictor that ranks recipes before routing,
so far fewer full routes are needed ([PREDICTOR.md](PREDICTOR.md)), and a directed
search for the tight designs where random sampling found nothing
([FLAGSHIP.md](FLAGSHIP.md)).

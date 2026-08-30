# Rung 0 harness

`harness(design, recipe) -> QoR (Quality of Results)` against the real
OpenROAD-flow-scripts (ORFS) ASAP7 (Arizona State University 7nm predictive
Process Design Kit) flow. Every sweep in this project is a loop over this.

## Files

- `recipes.py` - the classic-ABC (And-Inverter Graph optimizer) recipe: the
  searched optimization middle, the fixed `strash` prologue and mapping epilogue,
  `resyn2` as the reference point, and a random-recipe generator.
- `patch_orfs.py` - idempotent, reversible patch so ORFS honors an `ABC_SCRIPT`
  env override. Backs up `synth_preamble.tcl` to `.orig`. Revert with
  `python3 patch_orfs.py --revert`.
- `harness.py` - writes the recipe file, runs ORFS, scrapes finish-stage metrics
  into a `Result`. Command-line entry point included.

## Usage

```
python3 harness.py --design gcd --recipe resyn2      # classic baseline
python3 harness.py --design gcd --recipe random --seed 7
```

Point at a different ORFS install with `--orfs` or the `LEARNED_SYNTH_ORFS`
environment variable.

## How injection works

ORFS synthesis calls `abc -script <file>`. The patch adds one branch: if
`ABC_SCRIPT` is set, ABC uses that file. The harness writes each recipe to a file
and passes its path.

Two decisions baked in:

- **`SYNTH_USE_SYN=0` is forced.** That routes synthesis through `synth.tcl` ->
  `abc -script`, the classic path the override controls. Some designs (for example
  `gcd`) ship with `SYNTH_USE_SYN=1`, a newer integrated path that does not use the
  script file, so the harness overrides it for a single, consistent regime.
- **Each recipe runs under its own `FLOW_VARIANT`.** Output lands in
  `logs/asap7/<design>/<variant>/`, so make builds each recipe fresh (no stale
  caching from a prior run) and sweeps are parallel-safe.

## Metrics scraped

From `logs/asap7/<design>/<variant>/6_report.json` (post-route sign-off):

- `finish__design__instance__area` -> `area` (square micrometers)
- `finish__timing__setup__ws` -> `wns` (worst negative slack, picoseconds)
- `finish__timing__setup__tns` -> `tns` (total negative slack)
- `finish__power__total` -> `power` (watts)

Plus `synth__design__instance__area` from `1_synth.json` as a cheaper
post-synthesis signal. The figure of merit is a placeholder
(`area + wns_penalty * max(0, -wns)`); all raw metrics are logged so it can be
redefined later without re-running anything.

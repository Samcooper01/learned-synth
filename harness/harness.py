"""Rung 0 harness: harness(design, recipe) -> QoR (Quality of Results).

Writes a classic-ABC recipe to a script file, runs the real ORFS ASAP7 (Arizona
State University 7nm predictive Process Design Kit) flow with that recipe injected,
and scrapes the finish-stage metrics into a single record. Everything else in the
project is a loop over run_recipe().

Design notes:
- SYNTH_USE_SYN is forced to 0 so synthesis goes through synth.tcl -> abc -script,
  the classic path our ABC_SCRIPT override controls. (Some designs, e.g. gcd, ship
  with SYNTH_USE_SYN=1, a newer path that bypasses the script file.)
- Each recipe runs under its own FLOW_VARIANT so make builds it fresh (no stale
  caching) and sweeps are parallel-safe.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass

import recipes as rc
from patch_orfs import DEFAULT_ORFS, apply as apply_patch

RECIPE_DIR = os.environ.get(
    "LEARNED_SYNTH_RECIPE_DIR",
    "/tmp/claude-1000/-home-sam/8a61cee1-e8a5-4953-8fd4-94c275ab8888/scratchpad/recipes",
)


@dataclass
class Result:
    design: str
    variant: str
    ok: bool
    fom: float | None
    area: float | None          # finish__design__instance__area (um^2)
    wns: float | None           # finish__timing__setup__ws (ps)
    tns: float | None           # finish__timing__setup__tns (ps)
    power: float | None         # finish__power__total (W)
    synth_area: float | None    # 1_synth.json instance area (cheaper signal)
    runtime_s: float
    steps: tuple[str, ...]


def _report_path(orfs: str, design: str, variant: str, name: str) -> str:
    return os.path.join(orfs, "flow", "logs", "asap7", design, variant, name)


def _fom(area: float | None, wns: float | None, wns_penalty: float) -> float | None:
    """Figure of merit: minimize area, penalize timing violation. Placeholder.

    fom = area + wns_penalty * max(0, -wns). Both raw metrics are logged so the
    figure of merit can be redefined later without re-running anything.
    """
    if area is None:
        return None
    pen = wns_penalty * max(0.0, -(wns or 0.0))
    return area + pen


def run_recipe(
    recipe: rc.Recipe,
    design: str = "gcd",
    orfs: str = DEFAULT_ORFS,
    wns_penalty: float = 1.0,
    timeout_s: int = 3600,
) -> Result:
    os.makedirs(RECIPE_DIR, exist_ok=True)
    script_path = os.path.join(RECIPE_DIR, f"{recipe.variant}.script")
    with open(script_path, "w") as f:
        f.write(recipe.to_script())

    cmd = (
        f"source {orfs}/env.sh >/dev/null 2>&1 && cd {orfs}/flow && "
        f"make DESIGN_CONFIG=./designs/asap7/{design}/config.mk "
        f"FLOW_VARIANT={recipe.variant} ABC_SCRIPT={script_path} SYNTH_USE_SYN=0"
    )
    t0 = time.time()
    proc = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout_s
    )
    runtime = time.time() - t0

    finish = _load(_report_path(orfs, design, recipe.variant, "6_report.json"))
    synth = _load(_report_path(orfs, design, recipe.variant, "1_synth.json"))

    ok = proc.returncode == 0 and finish is not None
    area = finish.get("finish__design__instance__area") if finish else None
    wns = finish.get("finish__timing__setup__ws") if finish else None
    tns = finish.get("finish__timing__setup__tns") if finish else None
    power = finish.get("finish__power__total") if finish else None
    synth_area = synth.get("synth__design__instance__area") if synth else None

    return Result(
        design=design,
        variant=recipe.variant,
        ok=ok,
        fom=_fom(area, wns, wns_penalty),
        area=area,
        wns=wns,
        tns=tns,
        power=power,
        synth_area=synth_area,
        runtime_s=round(runtime, 1),
        steps=recipe.steps,
    )


def _load(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _make_recipe(kind: str, seed: int) -> rc.Recipe:
    if kind == "resyn2":
        return rc.resyn2()
    if kind == "random":
        return rc.random_recipe(random.Random(seed))
    raise SystemExit(f"unknown recipe kind: {kind}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run one (design, recipe) through ORFS.")
    ap.add_argument("--design", default="gcd")
    ap.add_argument("--recipe", default="resyn2", help="resyn2 | random")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--wns-penalty", type=float, default=1.0)
    args = ap.parse_args()

    print(apply_patch(args.orfs))  # ensure the ABC_SCRIPT override is in place
    recipe = _make_recipe(args.recipe, args.seed)
    res = run_recipe(recipe, design=args.design, orfs=args.orfs,
                     wns_penalty=args.wns_penalty)
    print(json.dumps(asdict(res), indent=2, default=list))

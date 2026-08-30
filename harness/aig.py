"""Fast ABC (And-Inverter Graph optimizer) proxy: the RL reward source.

Two jobs:
  1. make_start_aig(design): use Yosys once to emit a fixed starting AIG
     (And-Inverter Graph) for a design.
  2. proxy_eval(aig, steps): run a classic recipe on that AIG with yosys-abc and
     return (nodes, levels) from print_stats. No place-and-route, so it is fast
     enough to be an RL (Reinforcement Learning) per-step reward.

nodes is the area proxy; levels is the delay proxy. The real post-route QoR
(Quality of Results) is measured separately by harness.py on the final recipes.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess

from patch_orfs import DEFAULT_ORFS

YOSYS = os.path.join(DEFAULT_ORFS, "tools", "install", "yosys", "bin", "yosys")
YOSYS_ABC = os.path.join(DEFAULT_ORFS, "tools", "install", "yosys", "bin", "yosys-abc")
AIG_DIR = os.environ.get(
    "LEARNED_SYNTH_AIG_DIR",
    "/tmp/claude-1000/-home-sam/8a61cee1-e8a5-4953-8fd4-94c275ab8888/scratchpad/aigs",
)
_STATS = re.compile(r"and\s*=\s*(\d+)\s*lev\s*=\s*(\d+)")
_FULL = re.compile(
    r"i/o\s*=\s*(\d+)\s*/\s*(\d+)\s*lat\s*=\s*(\d+)\s*and\s*=\s*(\d+)\s*lev\s*=\s*(\d+)"
)


def design_top(design: str, orfs: str = DEFAULT_ORFS) -> str:
    cfg = os.path.join(orfs, "flow", "designs", "asap7", design, "config.mk")
    with open(cfg) as f:
        for line in f:
            m = re.search(r"DESIGN_NAME\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    return design


def _make_var(design: str, var: str, orfs: str) -> str:
    """Ask ORFS's own make to resolve a design variable (files, incdirs, defines)."""
    cfg = f"./designs/asap7/{design}/config.mk"
    proc = subprocess.run(
        ["make", f"DESIGN_CONFIG={cfg}", f"print-{var}"],
        cwd=os.path.join(orfs, "flow"), capture_output=True, text=True, timeout=120)
    out = proc.stdout.strip()
    # ORFS's print-% target emits "VAR: value ..."; strip the label.
    if out.startswith(var + ":"):
        out = out[len(var) + 1:].strip()
    return out


def resolve_design(design: str, orfs: str = DEFAULT_ORFS) -> dict:
    """Resolved sources, include dirs, and defines for a design, via ORFS make."""
    return {
        "top": _make_var(design, "DESIGN_NAME", orfs) or design,
        "files": _make_var(design, "VERILOG_FILES", orfs).split(),
        "incdirs": _make_var(design, "VERILOG_INCLUDE_DIRS", orfs).split(),
        "defines": _make_var(design, "VERILOG_DEFINES", orfs).split(),
    }


def design_sources(design: str, orfs: str = DEFAULT_ORFS) -> list[str]:
    return resolve_design(design, orfs)["files"]


MICRO_DIR = os.path.join(os.path.dirname(__file__), "microbench")


def _build_aig(name: str, files: list[str], top: str, incdirs, defines,
               preopt: str) -> str:
    """Emit a BLIF starting network. preopt='min' keeps redundancy (headroom for
    recipes); preopt='synth' runs full Yosys synthesis first."""
    os.makedirs(AIG_DIR, exist_ok=True)
    out = os.path.join(AIG_DIR, f"{name}_{preopt}.blif")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    if not files:
        raise FileNotFoundError(f"no Verilog sources for {name}")
    incs = " ".join(f"-I{i}" for i in incdirs)
    defs = " ".join(f"-D{v}" for v in defines)
    if preopt == "synth":
        core = f"synth -top {top} -flatten; "
    else:
        # minimal: to bit-level gates without the optimization passes, so recipes
        # have real room to differ.
        core = f"proc; flatten; techmap; "
    # ABC's read_blif only models simple .latch; async2sync + dfflegalize lower
    # all sequential cells to plain posedge DFFs. aigmap gives a pure AIG.
    script = (
        f"read_verilog -sv {incs} {defs} {' '.join(files)}; "
        f"hierarchy -top {top}; proc; flatten; "
        f"{core}"
        f"async2sync; dfflegalize -cell $_DFF_P_ 01; aigmap; "
        f"write_blif {out}"
    )
    proc = subprocess.run([YOSYS, "-p", script], capture_output=True, text=True,
                          timeout=600)
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"yosys failed to emit BLIF for {name}:\n{proc.stderr[-2000:]}")
    return out


def make_start_aig(design: str, orfs: str = DEFAULT_ORFS, preopt: str = "synth") -> str:
    """Starting BLIF for an ORFS design (cached, keyed by preopt level)."""
    d = resolve_design(design, orfs)
    return _build_aig(design, d["files"], d["top"], d["incdirs"], d["defines"], preopt)


def make_micro_aig(name: str, preopt: str = "min") -> str:
    """Starting BLIF for a synthetic microbenchmark in harness/microbench/."""
    f = os.path.join(MICRO_DIR, f"{name}.v")
    return _build_aig(name, [f], name, [], [], preopt)


def proxy_eval(aig_path: str, steps, timeout_s: int = 60) -> tuple[int, int] | None:
    """Run classic recipe `steps` on the network; return (nodes, levels) or None."""
    cmds = "; ".join(["strash", *steps, "print_stats"])
    script = f"read_blif {aig_path}; {cmds}"
    try:
        proc = subprocess.run([YOSYS_ABC, "-c", script], capture_output=True,
                              text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None
    matches = _STATS.findall(proc.stdout)
    if not matches:
        return None
    nodes, levels = matches[-1]          # last print_stats = final state
    return int(nodes), int(levels)


def start_features(aig_path: str) -> tuple[int, int, int, int, int] | None:
    """Static descriptors of the starting network: (pi, po, lat, nodes, levels)."""
    script = f"read_blif {aig_path}; strash; print_stats"
    proc = subprocess.run([YOSYS_ABC, "-c", script], capture_output=True,
                          text=True, timeout=60)
    m = _FULL.findall(proc.stdout)
    if not m:
        return None
    pi, po, lat, nodes, lev = m[-1]
    return int(pi), int(po), int(lat), int(nodes), int(lev)


if __name__ == "__main__":
    import sys
    import recipes as rc
    d = sys.argv[1] if len(sys.argv) > 1 else "gcd"
    aig = make_start_aig(d)
    print(f"start AIG: {aig}")
    base = proxy_eval(aig, [])
    r2 = proxy_eval(aig, rc.RESYN2)
    print(f"{d}: start nodes/levels = {base}, after resyn2 = {r2}")

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


def design_nickname(design: str, orfs: str = DEFAULT_ORFS) -> str | None:
    cfg = os.path.join(orfs, "flow", "designs", "asap7", design, "config.mk")
    with open(cfg) as f:
        for line in f:
            m = re.search(r"DESIGN_NICKNAME\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    return None


def design_sources(design: str, orfs: str = DEFAULT_ORFS) -> list[str]:
    """Sources live under src/<nickname>, which is not always the design name."""
    srcroot = os.path.join(orfs, "flow", "designs", "src")
    candidates = [
        design_nickname(design, orfs),
        design,
        f"{design}_sv",
        design_top(design, orfs),
    ]
    for c in candidates:
        if not c:
            continue
        d = os.path.join(srcroot, c)
        files = sorted(glob.glob(os.path.join(d, "*.v")))
        files += sorted(glob.glob(os.path.join(d, "*.sv")))
        if files:
            return files
    return []


def make_start_aig(design: str, orfs: str = DEFAULT_ORFS) -> str:
    """Emit a fixed starting network (BLIF) for a design; returns its path.

    Cached on disk. BLIF (Berkeley Logic Interchange Format), not AIGER, because
    AIGER's backend rejects enable flip-flops; dfflegalize lowers all sequential
    cells to plain posedge DFFs first.
    """
    os.makedirs(AIG_DIR, exist_ok=True)
    out = os.path.join(AIG_DIR, f"{design}.blif")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    top = design_top(design, orfs)
    files = design_sources(design, orfs)
    if not files:
        raise FileNotFoundError(f"no Verilog sources found for {design}")
    script = (
        f"read_verilog -sv {' '.join(files)}; "
        f"hierarchy -top {top}; proc; flatten; "
        f"synth -top {top} -flatten; "
        f"dfflegalize -cell $_DFF_P_ 01 -cell $_DFF_PP0_ 01 -cell $_DFF_PP1_ 01 "
        f"-cell $_DFF_PN0_ 01 -cell $_DFF_PN1_ 01; "
        f"write_blif {out}"
    )
    proc = subprocess.run([YOSYS, "-p", script], capture_output=True, text=True,
                          timeout=600)
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"yosys failed to emit BLIF for {design}:\n{proc.stderr[-2000:]}")
    return out


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

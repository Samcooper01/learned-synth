"""Classic ABC (And-Inverter Graph optimizer) recipe representation.

A recipe is the SEARCHED optimization middle only. The harness wraps it with a
fixed prologue (build the AIG) and a fixed epilogue (map to standard cells and
finish) so the netlist stays valid for OpenROAD and every comparison is
apples-to-apples. See harness/README.md.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

# The classic-ABC optimization alphabet the search draws from. These are pure
# technology-independent logic-optimization commands (no mapping here; mapping is
# in the fixed epilogue). Matches the command set FlowTune and DRiLLS use.
#
# NOTE: canonical command names, not the abc.rc aliases (b/rw/rf/rs). Yosys runs
# `abc -script <file>` without loading abc.rc, so the aliases are undefined; the
# full names always resolve.
ALPHABET: tuple[str, ...] = (
    "balance",       # reduce depth
    "rewrite",       # reduce nodes
    "rewrite -z",    # rewrite, zero-cost (escape local minima)
    "refactor",      # reduce nodes over larger cones
    "refactor -z",   # refactor, zero-cost
    "resub",         # resubstitution, reduce nodes
    "resub -z",      # resub, zero-cost
)

# Fixed prologue: structural hashing builds the AIG from the network ABC is given.
PROLOGUE: tuple[str, ...] = ("strash",)

# Fixed epilogue: technology-map to the loaded standard-cell library and finish,
# mirroring the tail of ORFS's own abc_area.script. The library and constraints
# are supplied by ORFS on the abc command line (-liberty / -constr), so these
# commands see them. Kept constant so the searched middle owns all optimization.
EPILOGUE: tuple[str, ...] = (
    "map -B 0.9",
    "topo",
    "stime -c",
    "buffer -c",
    "upsize -c",
    "dnsize -c",
)

# The canonical classic reference recipe, resyn2, as one point in the search space.
# resyn2 = b; rw; rf; b; rw; rwz; b; rfz; rwz; b  (canonical names below)
RESYN2: tuple[str, ...] = (
    "balance", "rewrite", "refactor", "balance", "rewrite", "rewrite -z",
    "balance", "refactor -z", "rewrite -z", "balance",
)


@dataclass(frozen=True)
class Recipe:
    """An optimization middle plus a stable identity for FLOW_VARIANT / logging."""

    steps: tuple[str, ...]
    label: str = ""

    @property
    def variant(self) -> str:
        """Short, stable id used as the ORFS FLOW_VARIANT (fresh output subdir)."""
        base = self.label or "r"
        digest = hashlib.sha1(";".join(self.steps).encode()).hexdigest()[:8]
        return f"{base}_{digest}"

    def to_script(self) -> str:
        """Render the full ABC script file: prologue + searched middle + epilogue."""
        lines = list(PROLOGUE) + list(self.steps) + list(EPILOGUE)
        return "\n".join(lines) + "\n"


def resyn2() -> Recipe:
    return Recipe(steps=RESYN2, label="resyn2")


def random_recipe(rng: random.Random, min_len: int = 6, max_len: int = 14) -> Recipe:
    """Sample a random classic optimization middle (the workhorse-sweep generator)."""
    n = rng.randint(min_len, max_len)
    steps = tuple(rng.choice(ALPHABET) for _ in range(n))
    return Recipe(steps=steps, label="rand")


if __name__ == "__main__":
    # Quick visual check of what gets written to the ABC script file.
    r = resyn2()
    print(f"# variant: {r.variant}")
    print(r.to_script())

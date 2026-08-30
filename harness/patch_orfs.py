"""Idempotent, reversible patch so ORFS honors an ABC_SCRIPT env override.

ORFS's synth_preamble.tcl hardcodes the ABC (And-Inverter Graph optimizer) recipe
to abc_speed.script or abc_area.script. To inject an arbitrary classic recipe we
add one branch: if ABC_SCRIPT is set, use that file. The original is backed up to
synth_preamble.tcl.orig so the change is fully reversible (see --revert).

This modifies a file inside the user's ORFS install, not this repo. It is additive
and reversible.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

DEFAULT_ORFS = os.environ.get(
    "LEARNED_SYNTH_ORFS", "/home/sam/Geetus2.0/Flow/OpenROAD-flow-scripts"
)

ANCHOR = 'if { $::env(ABC_AREA) } {\n  puts "Using ABC area script."'
REPLACEMENT = (
    'if { [env_var_exists_and_non_empty ABC_SCRIPT] } {\n'
    '  puts "learned-synth: using custom ABC script $::env(ABC_SCRIPT)."\n'
    '  set abc_script $::env(ABC_SCRIPT)\n'
    '} elseif { $::env(ABC_AREA) } {\n'
    '  puts "Using ABC area script."'
)
MARKER = "learned-synth: using custom ABC script"


def preamble_path(orfs: str) -> str:
    return os.path.join(orfs, "flow", "scripts", "synth_preamble.tcl")


def apply(orfs: str) -> str:
    path = preamble_path(orfs)
    with open(path) as f:
        text = f.read()
    if MARKER in text:
        return "already patched"
    if ANCHOR not in text:
        raise SystemExit(
            f"anchor not found in {path}; ORFS layout differs from expectation, "
            "inspect synth_preamble.tcl before patching"
        )
    backup = path + ".orig"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    with open(path, "w") as f:
        f.write(text.replace(ANCHOR, REPLACEMENT, 1))
    return f"patched (backup at {backup})"


def revert(orfs: str) -> str:
    path = preamble_path(orfs)
    backup = path + ".orig"
    if not os.path.exists(backup):
        return "no backup found, nothing to revert"
    shutil.copy2(backup, path)
    return "reverted from backup"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    print(revert(args.orfs) if args.revert else apply(args.orfs))
    sys.exit(0)

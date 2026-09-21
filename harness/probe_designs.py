"""Step 1 tool: find which ASAP7 (Arizona State University 7nm predictive Process
Design Kit) designs synthesize cleanly through the learned-synth harness.

For each candidate design it runs ORFS (OpenROAD Flow Scripts) synthesis ONLY
(the `synth` make target, seconds to minutes) with the reference resyn2 recipe
injected via the ABC (And-Inverter Graph optimizer) script override. Synthesis is
cheap; a full place-and-route is not. So we curate the design set at the synthesis
stage first, then spend route budget only on designs that already pass here.

Per design it records: whether synthesis succeeded, whether our recipe override was
actually honored (the marker in the Yosys log), post-synthesis instance area and
count, the synth error/warning counts, and wall-clock time. The output is the
clean-design table the real-QoR (Quality of Results) sweeps consume.

Usage:
    python3 probe_designs.py                       # probe the default set
    python3 probe_designs.py --designs gcd aes ibex
    python3 probe_designs.py --workers 4 --timeout 1800
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import recipes as rc
from patch_orfs import DEFAULT_ORFS, apply as apply_patch

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
MARKER = "learned-synth: using custom ABC script"

# Distinct-RTL (Register Transfer Level) ASAP7 designs shipped with ORFS. The
# library variants (aes_lvt, ethmac_lvt, jpeg_lvt), the flop/constraint variants
# (aes-mbff, gcd-ccs, riscv32i-mock-sram) and the trivial `minimal` design are left
# out on purpose: they add no logic-structure diversity for a recipe study.
DEFAULT_DESIGNS = [
    "gcd", "uart", "aes", "ibex", "jpeg", "ethmac",
    "riscv32i", "mock-alu", "mock-cpu", "aes-block",
    "swerv_wrapper", "cva6",
]


def _log_dir(orfs: str, design: str, variant: str) -> str:
    return os.path.join(orfs, "flow", "logs", "asap7", design, variant)


def _override_honored(orfs: str, design: str, variant: str) -> bool:
    """True if a Yosys log for this run contains our custom-ABC-script marker."""
    ldir = _log_dir(orfs, design, variant)
    try:
        for name in os.listdir(ldir):
            if name.endswith(".log"):
                with open(os.path.join(ldir, name), errors="ignore") as f:
                    if MARKER in f.read():
                        return True
    except OSError:
        pass
    return False


def probe_one(design, orfs, script_path, variant, timeout_s, num_cores):
    cmd = (
        f"source {orfs}/env.sh >/dev/null 2>&1 && cd {orfs}/flow && "
        f"make DESIGN_CONFIG=./designs/asap7/{design}/config.mk "
        f"FLOW_VARIANT={variant} ABC_SCRIPT={script_path} "
        f"SYNTH_USE_SYN=0 NUM_CORES={num_cores} synth"
    )
    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout_s
        )
        rc_code = proc.returncode
    except subprocess.TimeoutExpired:
        rc_code = -1
        timed_out = True
    runtime = round(time.time() - t0, 1)

    synth = _load(os.path.join(_log_dir(orfs, design, variant), "1_synth.json"))
    honored = _override_honored(orfs, design, variant)
    ok = (rc_code == 0) and (synth is not None) and honored

    return {
        "design": design,
        "ok": ok,
        "timed_out": timed_out,
        "returncode": rc_code,
        "override_honored": honored,
        "synth_area": synth.get("synth__design__instance__area") if synth else None,
        "synth_insts": synth.get("synth__design__instance__count") if synth else None,
        "synth_errors": synth.get("synth__flow__errors__count") if synth else None,
        "synth_warnings": synth.get("synth__flow__warnings__count") if synth else None,
        "runtime_s": runtime,
    }


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def table(rows):
    rows = sorted(rows, key=lambda r: (not r["ok"], r["design"]))
    print("\n===== design probe (synthesis-only, resyn2 injected) =====")
    hdr = f"{'design':<14} {'ok':>3} {'area':>10} {'insts':>8} {'err':>4} {'warn':>5} {'sec':>7}  note"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        note = ""
        if not r["ok"]:
            if r["timed_out"]:
                note = "TIMEOUT"
            elif not r["override_honored"]:
                note = "override NOT honored"
            elif r["returncode"] != 0:
                note = f"synth failed (rc={r['returncode']})"
            else:
                note = "no metrics"
        area = f"{r['synth_area']:.1f}" if r["synth_area"] is not None else "-"
        insts = r["synth_insts"] if r["synth_insts"] is not None else "-"
        err = r["synth_errors"] if r["synth_errors"] is not None else "-"
        warn = r["synth_warnings"] if r["synth_warnings"] is not None else "-"
        mark = "OK" if r["ok"] else "x"
        print(f"{r['design']:<14} {mark:>3} {area:>10} {insts:>8} {err:>4} {warn:>5} {r['runtime_s']:>7}  {note}")
    clean = [r["design"] for r in rows if r["ok"]]
    print(f"\n{len(clean)}/{len(rows)} synthesize cleanly: {', '.join(clean)}")
    return clean


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Probe which ASAP7 designs synthesize cleanly.")
    ap.add_argument("--designs", nargs="+", default=DEFAULT_DESIGNS)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    ap.add_argument("--variant", default="probe_ls")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--num-cores", type=int, default=4)
    args = ap.parse_args()

    print(apply_patch(args.orfs))
    script_path = os.path.join(RESULTS_DIR, "..", "harness", "_probe_resyn2.script")
    script_path = os.path.abspath(script_path)
    with open(script_path, "w") as f:
        f.write(rc.resyn2().to_script())

    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"design_probe_{stamp}.jsonl")
    print(f"probing {len(args.designs)} designs, {args.workers} workers, "
          f"timeout {args.timeout}s each")
    print(f"results -> {out_path}")

    rows = []
    with open(out_path, "w") as out, ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(probe_one, d, args.orfs, script_path, args.variant,
                      args.timeout, args.num_cores): d
            for d in args.designs
        }
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            out.write(json.dumps(r) + "\n")
            out.flush()
            done += 1
            print(f"[{done}/{len(args.designs)}] {r['design']}: "
                  f"{'OK' if r['ok'] else 'FAIL'} ({r['runtime_s']}s)", flush=True)

    table(rows)

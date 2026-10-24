"""Directed recipe search (genetic algorithm) with a cheap synthesis-only fitness.

Random search (results/HEADLINE.md) beats resyn2 on some designs but samples blindly. This runs a
genetic algorithm over ABC (And-Inverter Graph optimizer) recipes, scored by the
cheap post-synthesis cell area (which predicts routed area at Spearman ~0.8 and, on the
tight designs, is smaller for timing-legal recipes). Synthesis is seconds per design
and low-memory, so a few hundred evaluations are cheap. The best candidates are then
route-verified through the full flow to confirm real post-route area and timing.

Fitness = post-synth instance area (lower is better), evaluated with the classic
`abc -script` path (SWAP_ARITH_OPERATORS / SYNTH_WRAPPED_OPERATORS forced empty) at the
design's calibrated matched-delay clock.

Usage:
    python3 flagship_search.py --designs aes --pop 16 --gens 8 --workers 6 --verify-k 3
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import recipes as rc
from harness import run_recipe, RECIPE_DIR
from patch_orfs import DEFAULT_ORFS, apply as apply_patch
from calibrate_clocks import write_sdc

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
CLASSIC = {"SWAP_ARITH_OPERATORS": "", "SYNTH_WRAPPED_OPERATORS": ""}


def load_clocks():
    with open(os.path.join(RESULTS_DIR, "clocks.json")) as f:
        return json.load(f)


def synth_area(design, steps, orfs, sdc, num_cores=4, timeout=1200):
    """Run synthesis only for one recipe and return post-synth instance area (or None
    on failure). Cheap: seconds to a couple of minutes, no place-and-route."""
    recipe = rc.Recipe(steps=tuple(steps), label="ga")
    os.makedirs(RECIPE_DIR, exist_ok=True)
    script = os.path.join(RECIPE_DIR, f"{recipe.variant}.script")
    with open(script, "w") as f:
        f.write(recipe.to_script())
    extra = f" SDC_FILE={sdc}" + "".join(f" {k}={v}" for k, v in CLASSIC.items())
    cmd = (f"source {orfs}/env.sh >/dev/null 2>&1 && cd {orfs}/flow && "
           f"make DESIGN_CONFIG=./designs/asap7/{design}/config.mk "
           f"FLOW_VARIANT={recipe.variant} ABC_SCRIPT={script} SYNTH_USE_SYN=0 "
           f"NUM_CORES={num_cores}{extra} synth")
    try:
        subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    j = os.path.join(orfs, "flow", "logs", "asap7", design, recipe.variant, "1_synth.json")
    try:
        return json.load(open(j)).get("synth__design__instance__area")
    except (OSError, json.JSONDecodeError):
        return None


# ---- genetic algorithm over recipe step lists ----

def random_steps(rng, lo=6, hi=14):
    return [rng.choice(rc.ALPHABET) for _ in range(rng.randint(lo, hi))]


def crossover(a, b, rng):
    ca = rng.randint(1, max(1, len(a) - 1))
    cb = rng.randint(1, max(1, len(b) - 1))
    child = a[:ca] + b[cb:]
    return child[:20] or list(a)


def mutate(steps, rng, p=0.3):
    steps = list(steps)
    if rng.random() < p and len(steps) > 4:
        del steps[rng.randrange(len(steps))]      # delete
    if rng.random() < p and len(steps) < 20:
        steps.insert(rng.randrange(len(steps) + 1), rng.choice(rc.ALPHABET))  # insert
    if rng.random() < p:
        steps[rng.randrange(len(steps))] = rng.choice(rc.ALPHABET)            # swap
    return steps


def ga_search(design, clocks, orfs, pop_size, gens, workers, seed, num_cores):
    rng = random.Random(f"ga:{design}:{seed}")
    clk = clocks[design]
    sdc = write_sdc(orfs, design, clk["calibrated_period"],
                    scale_all=clk.get("mode") == "scale_all")
    cache = {}

    def evaluate(pop):
        todo = [s for s in pop if tuple(s) not in cache]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(synth_area, design, s, orfs, sdc, num_cores): tuple(s)
                    for s in todo}
            for fut in futs:
                cache[futs[fut]] = fut.result()
        # score: area, with None (synth failure) as +inf
        return [(s, cache[tuple(s)] if cache[tuple(s)] is not None else float("inf"))
                for s in pop]

    # seed population: resyn2 + random
    pop = [list(rc.RESYN2)] + [random_steps(rng) for _ in range(pop_size - 1)]
    best = None
    history = []
    for g in range(gens):
        scored = sorted(evaluate(pop), key=lambda t: t[1])
        if best is None or scored[0][1] < best[1]:
            best = scored[0]
        history.append({"gen": g, "best_synth_area": scored[0][1],
                        "best_steps": scored[0][0]})
        print(f"  [{design}] gen {g}: best synth area = {scored[0][1]:.1f} "
              f"(pop {len(pop)}, cache {len(cache)})", flush=True)
        # next generation: elitism + tournament crossover + mutation
        survivors = [s for s, _ in scored[:max(2, pop_size // 4)]]
        nxt = list(survivors)
        while len(nxt) < pop_size:
            a = min(rng.sample(scored, min(3, len(scored))), key=lambda t: t[1])[0]
            b = min(rng.sample(scored, min(3, len(scored))), key=lambda t: t[1])[0]
            nxt.append(mutate(crossover(a, b, rng), rng))
        pop = nxt
    # top unique candidates by synth area
    uniq = sorted({tuple(s): a for s, a in
                   [(k, v) for k, v in cache.items() if v is not None]}.items(),
                  key=lambda kv: kv[1])
    return best, history, uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", nargs="+", required=True)
    ap.add_argument("--pop", type=int, default=16)
    ap.add_argument("--gens", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--verify-k", type=int, default=3, help="top-K candidates to route")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--num-cores", type=int, default=4)
    ap.add_argument("--orfs", default=DEFAULT_ORFS)
    args = ap.parse_args()

    apply_patch(args.orfs)
    clocks = load_clocks()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(RESULTS_DIR, f"flagship_{stamp}.json")
    report = {}

    for d in args.designs:
        print(f"=== GA search on {d} (pop {args.pop} x {args.gens} gens) ===", flush=True)
        t0 = time.time()
        best, history, uniq = ga_search(d, clocks, args.orfs, args.pop, args.gens,
                                        args.workers, args.seed, args.num_cores)
        search_s = time.time() - t0
        # route-verify the top-K distinct candidates
        print(f"  route-verifying top {args.verify_k} candidates ...", flush=True)
        clk = clocks[d]
        sdc = write_sdc(args.orfs, d, clk["calibrated_period"],
                        scale_all=clk.get("mode") == "scale_all")
        extra = {"SDC_FILE": sdc, **CLASSIC}
        verified = []
        for steps, synthA in uniq[:args.verify_k]:
            recipe = rc.Recipe(steps=tuple(steps), label="gaver")
            res = run_recipe(recipe, design=d, orfs=args.orfs, num_cores=args.num_cores,
                             extra_vars=extra, timeout_s=7200)
            verified.append({"steps": list(steps), "synth_area": synthA,
                             "ok": res.ok, "area": res.area, "wns": res.wns,
                             "meets_timing": bool(res.ok and res.wns is not None and res.wns >= 0)})
            print(f"    routed: synthA={synthA:.1f} -> area={res.area} wns={res.wns} "
                  f"meets={verified[-1]['meets_timing']}", flush=True)
        report[d] = {"search_seconds": round(search_s, 1), "evals": len(uniq),
                     "history": history, "verified": verified}
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)

    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()

"""Evaluate a trained policy against resyn2 and random search.

Two tiers:
  - proxy (fast, all designs): node count after the recipe.
  - real ASAP7 (Arizona State University 7nm predictive Process Design Kit) QoR
    (Quality of Results): full ORFS run, only for the designs listed in --real
    (kept few and low-thread so we do not crowd a shared machine).

The RL (Reinforcement Learning) policy is rolled out greedily to produce one
recipe per design. Random search reports the best of N random recipes on the proxy.
"""

from __future__ import annotations

import argparse
import json
import os
import random

from stable_baselines3 import PPO

import aig
import recipes as rc
from harness import run_recipe
from rl_env import AbcRecipeEnv

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def rollout_policy(model, design: str, horizon: int) -> tuple[str, ...]:
    env = AbcRecipeEnv([design], horizon=horizon)
    obs, _ = env.reset()
    info = {}
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, term, trunc, info = env.step(int(action))
        done = term or trunc
    return info.get("recipe", ())


def best_random_proxy(blif: str, n: int, seed: int) -> tuple[tuple[str, ...], int]:
    rng = random.Random(seed)
    best_steps, best_nodes = None, 10**9
    for _ in range(n):
        r = rc.random_recipe(rng)
        res = aig.proxy_eval(blif, list(r.steps))
        if res and res[0] < best_nodes:
            best_nodes, best_steps = res[0], r.steps
    return best_steps or rc.RESYN2, best_nodes


def eval_design(model, design: str, horizon: int, n_random: int, real: bool):
    blif = aig.make_start_aig(design)
    start_nodes = aig.proxy_eval(blif, [])[0]
    resyn2_nodes = aig.proxy_eval(blif, list(rc.RESYN2))[0]
    rl_steps = rollout_policy(model, design, horizon)
    rl_nodes = aig.proxy_eval(blif, list(rl_steps))[0]
    rand_steps, rand_nodes = best_random_proxy(blif, n_random, seed=1)

    row = {
        "design": design,
        "start_nodes": start_nodes,
        "proxy": {
            "resyn2": resyn2_nodes,
            "rl": rl_nodes,
            "random_best": rand_nodes,
            "rl_vs_resyn2_pct": 100.0 * (rl_nodes - resyn2_nodes) / resyn2_nodes,
        },
        "rl_recipe": list(rl_steps),
    }

    if real:
        row["real"] = {}
        for name, steps in [("resyn2", rc.RESYN2), ("rl", rl_steps),
                            ("random_best", rand_steps)]:
            recipe = rc.Recipe(steps=tuple(steps), label=f"eval_{design}_{name}")
            res = run_recipe(recipe, design=design, num_cores=4)
            row["real"][name] = {"ok": res.ok, "fom": res.fom, "area": res.area,
                                 "wns": res.wns, "power": res.power}
        r2 = row["real"]["resyn2"].get("fom")
        rl = row["real"]["rl"].get("fom")
        if r2 and rl:
            row["real"]["rl_vs_resyn2_pct"] = 100.0 * (rl - r2) / r2
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(os.path.dirname(__file__),
                    "..", "models", "ppo_abc.zip"))
    ap.add_argument("--designs", nargs="+", default=["gcd", "uart", "aes"])
    ap.add_argument("--real", nargs="+", default=["gcd", "uart"],
                    help="designs to also evaluate at real ASAP7 QoR")
    ap.add_argument("--horizon", type=int, default=12)
    ap.add_argument("--n-random", type=int, default=40)
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "rl_eval.json"))
    args = ap.parse_args()

    model = PPO.load(args.model, device="cpu")
    rows = []
    for d in args.designs:
        print(f"evaluating {d} ...", flush=True)
        rows.append(eval_design(model, d, args.horizon, args.n_random, d in args.real))
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"wrote {args.out}")
    for r in rows:
        line = f"{r['design']:8s} proxy: resyn2={r['proxy']['resyn2']} rl={r['proxy']['rl']} ({r['proxy']['rl_vs_resyn2_pct']:+.1f}%)"
        if "real" in r and "rl_vs_resyn2_pct" in r["real"]:
            line += f" | real fom rl vs resyn2 {r['real']['rl_vs_resyn2_pct']:+.1f}%"
        print(line)

"""Train a PPO policy over the classic ABC (And-Inverter Graph optimizer) command
space, rewarded by the fast node-count proxy. Saves the policy and a training log.

Reward is the proxy (fast, so training finishes overnight without competing for the
shared machine). Learned recipes are validated at real ASAP7 (Arizona State
University 7nm predictive Process Design Kit) QoR (Quality of Results) by
eval_policy.py.
"""

from __future__ import annotations

import argparse
import csv
import os

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_env import AbcRecipeEnv

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


class EpisodeLogger(BaseCallback):
    """Record mean episode reward over time to a CSV."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.rows = []

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            ep = info.get("episode")
            if ep is not None:
                self.rows.append((self.num_timesteps, ep["r"], ep["l"]))
        return True

    def _on_training_end(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timesteps", "ep_reward", "ep_len"])
            w.writerows(self.rows)


def make_env(designs, horizon, seed):
    def _thunk():
        from gymnasium.wrappers import RecordEpisodeStatistics
        return RecordEpisodeStatistics(AbcRecipeEnv(designs, horizon=horizon, seed=seed))
    return _thunk


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs="+", default=["gcd", "uart"])
    ap.add_argument("--timesteps", type=int, default=50000)
    ap.add_argument("--horizon", type=int, default=12)
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(MODEL_DIR, "ppo_abc.zip"))
    args = ap.parse_args()

    print(f"training PPO on {args.train} for {args.timesteps} timesteps")
    venv = DummyVecEnv([make_env(args.train, args.horizon, args.seed + i)
                        for i in range(args.n_envs)])
    logger = EpisodeLogger(os.path.join(MODEL_DIR, "training_log.csv"))
    model = PPO("MlpPolicy", venv, verbose=1, seed=args.seed,
                n_steps=256, batch_size=256, gamma=0.99, device="cpu")
    model.learn(total_timesteps=args.timesteps, callback=logger)
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save(args.out)
    print(f"saved policy -> {args.out}")

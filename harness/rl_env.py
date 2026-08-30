"""Gymnasium RL (Reinforcement Learning) environment over the classic ABC
(And-Inverter Graph optimizer) command space.

- Action: append one classic command (the ALPHABET) to the recipe.
- Reward: per-step reduction in AIG (And-Inverter Graph) node count (the area
  proxy) from the fast proxy evaluator, normalized by the starting node count.
- Episode: fixed horizon of steps, then done.
- State: static design descriptors + dynamic progress + last action.

The reward is the fast ABC proxy so training is feasible overnight (DRiLLS
approach). Learned recipes are validated at real ASAP7 (Arizona State University
7nm predictive Process Design Kit) post-route QoR (Quality of Results) separately
by eval_policy.py.
"""

from __future__ import annotations

import math

import gymnasium as gym
import numpy as np
from gymnasium import spaces

import aig
import recipes as rc

_PROXY_CACHE: dict[tuple[str, tuple[str, ...]], tuple[int, int] | None] = {}


def cached_proxy(blif: str, steps: tuple[str, ...]) -> tuple[int, int] | None:
    key = (blif, steps)
    if key not in _PROXY_CACHE:
        _PROXY_CACHE[key] = aig.proxy_eval(blif, list(steps))
    return _PROXY_CACHE[key]


class DesignInfo:
    def __init__(self, design: str):
        self.design = design
        self.blif = aig.make_start_aig(design)
        feats = aig.start_features(self.blif)
        if feats is None:
            raise RuntimeError(f"could not get start features for {design}")
        self.pi, self.po, self.lat, self.nodes0, self.lev0 = feats

    def static_vec(self) -> np.ndarray:
        return np.array([
            math.log10(max(self.nodes0, 1)),
            self.lev0 / 100.0,
            self.pi / 100.0,
            self.po / 100.0,
            self.lat / 100.0,
        ], dtype=np.float32)


class AbcRecipeEnv(gym.Env):
    """One episode builds one recipe for one (sampled) design."""

    metadata = {"render_modes": []}

    def __init__(self, designs: list[str], horizon: int = 12, seed: int = 0):
        super().__init__()
        self.infos = [DesignInfo(d) for d in designs]
        self.horizon = horizon
        self.alphabet = rc.ALPHABET
        self._rng = np.random.default_rng(seed)

        n_static = 5
        n_dynamic = 3  # cur_nodes/nodes0, cur_lev/lev0, step/horizon
        obs_dim = n_static + n_dynamic + len(self.alphabet)
        self.observation_space = spaces.Box(-10.0, 10.0, (obs_dim,), np.float32)
        self.action_space = spaces.Discrete(len(self.alphabet))
        self._reset_state()

    def _reset_state(self):
        self.info = self.infos[self._rng.integers(len(self.infos))]
        self.steps: list[str] = []
        self.cur_nodes = self.info.nodes0
        self.cur_lev = self.info.lev0
        self.last_action = -1
        self.t = 0

    def _obs(self) -> np.ndarray:
        onehot = np.zeros(len(self.alphabet), dtype=np.float32)
        if self.last_action >= 0:
            onehot[self.last_action] = 1.0
        dyn = np.array([
            self.cur_nodes / max(self.info.nodes0, 1),
            self.cur_lev / max(self.info.lev0, 1),
            self.t / self.horizon,
        ], dtype=np.float32)
        return np.concatenate([self.info.static_vec(), dyn, onehot])

    def reset(self, *, seed=None, options=None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: int):
        cmd = self.alphabet[int(action)]
        self.steps.append(cmd)
        self.last_action = int(action)
        self.t += 1

        res = cached_proxy(self.info.blif, tuple(self.steps))
        if res is None:
            # proxy failed on this recipe; end with a penalty
            return self._obs(), -1.0, True, False, {"failed": True}
        new_nodes, new_lev = res
        reward = (self.cur_nodes - new_nodes) / max(self.info.nodes0, 1)
        self.cur_nodes, self.cur_lev = new_nodes, new_lev

        terminated = self.t >= self.horizon
        info = {
            "design": self.info.design,
            "nodes": self.cur_nodes,
            "lev": self.cur_lev,
            "recipe": tuple(self.steps),
        }
        return self._obs(), float(reward), terminated, False, info


if __name__ == "__main__":
    env = AbcRecipeEnv(["gcd"], horizon=12)
    obs, _ = env.reset()
    print("obs dim:", obs.shape, "n actions:", env.action_space.n)
    total = 0.0
    for _ in range(12):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        total += r
        if term:
            break
    print(f"random episode total reward: {total:.4f}, final nodes={info.get('nodes')}")
    print("recipe:", info.get("recipe"))

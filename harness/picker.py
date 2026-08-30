"""One-step lookahead recipe picker driven by the GNN (Graph Neural Network)
value surrogate.

At each step: apply every classic transform, score each resulting AIG (And-Inverter
Graph) state with the GNN value model (lower predicted reachable node count = better
state), commit to the best, repeat. The value target means a zero-cost `-z` setup
move can score well because it *leads to* a lower state, which greedy-by-immediate
cannot see.

Compares three pickers on final proxy node count:
  - resyn2 (fixed baseline)
  - greedy-immediate (pick the transform with the lowest node count right now)
  - GNN-value lookahead
"""

from __future__ import annotations

import argparse
import json
import math
import os

import torch
from torch_geometric.data import Batch

import aig
import aig_graph
import recipes as rc
from gnn_train import GNNSurrogate, N_TYPES, to_data


def load_model(path: str) -> GNNSurrogate:
    model = GNNSurrogate(in_dim=N_TYPES + 2)
    model.load_state_dict(torch.load(path, map_location="cpu"))
    model.eval()
    return model


def gnn_value(model, blif, steps):
    """Predicted final node count reachable from the state after `steps`.

    The GNN predicts the size-invariant reachable REDUCTION fraction (the part it
    predicts well). We combine it with the exactly-measured current node count:
        predicted_final = current_nodes * (1 - predicted_reduction)
    Lower is better. This leverages the GNN's structural strength without fighting
    the size-dominated absolute-value regression.
    """
    g = aig_graph.extract_graph(blif, steps)
    if g is None:
        return None
    cur = g["counts"][4]
    s = {"node_type": g["node_type"], "edge_index": g["edge_index"],
         "cur_and": cur, "log_cur": math.log10(max(cur, 1)), "y": 0.0, "design": ""}
    with torch.no_grad():
        red = float(model(Batch.from_data_list([to_data(s, "after")])).item())
    return cur * (1.0 - red)


def lookahead_pick(model, blif, horizon):
    steps = []
    for _ in range(horizon):
        best = None
        for cmd in rc.ALPHABET:
            v = gnn_value(model, blif, steps + [cmd])
            if v is None:
                continue
            if best is None or v < best[0]:
                best = (v, cmd)
        if best is None:
            break
        steps.append(best[1])
    return steps


def greedy_immediate(blif, horizon):
    steps = []
    for _ in range(horizon):
        best = None
        for cmd in rc.ALPHABET:
            r = aig.proxy_eval(blif, steps + [cmd])
            if r is None:
                continue
            if best is None or r[0] < best[0]:
                best = (r[0], cmd)
        if best is None:
            break
        steps.append(best[1])
    return steps


def final_nodes(blif, steps):
    r = aig.proxy_eval(blif, list(steps))
    return r[0] if r else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(os.path.dirname(__file__),
                    "..", "models", "gnn_value_reduction.pt"))
    ap.add_argument("--designs", nargs="+",
                    default=["mult_18", "addchain_24", "decoder_9", "cmptree_24",
                             "lfsr_64", "muxtree_7"])
    ap.add_argument("--horizon", type=int, default=10)
    args = ap.parse_args()

    model = load_model(args.model)
    rows = []
    for spec in args.designs:
        name, _, sz = spec.partition("_")
        size = int(sz) if sz else None
        blif = aig.make_micro_aig(name, preopt="min", size=size)
        start = final_nodes(blif, [])
        r2 = final_nodes(blif, rc.RESYN2)
        gi = greedy_immediate(blif, args.horizon)
        gi_n = final_nodes(blif, gi)
        la = lookahead_pick(model, blif, args.horizon)
        la_n = final_nodes(blif, la)
        row = {"design": spec, "start": start, "resyn2": r2,
               "greedy_immediate": gi_n, "gnn_lookahead": la_n,
               "gnn_vs_resyn2_pct": 100.0 * (la_n - r2) / r2,
               "gnn_recipe": la}
        rows.append(row)
        print(f"{spec:14s} start={start:6d} resyn2={r2:6d} greedy={gi_n:6d} "
              f"gnn={la_n:6d}  (gnn vs resyn2 {row['gnn_vs_resyn2_pct']:+.1f}%)",
              flush=True)

    wins = sum(r["gnn_lookahead"] <= r["resyn2"] for r in rows)
    print(f"\nGNN-lookahead <= resyn2 on {wins}/{len(rows)} designs")
    out = os.path.join(os.path.dirname(__file__), "..", "results", "picker_results.json")
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"wrote {out}")

"""Train a GNN (Graph Neural Network) QoR (Quality of Results) surrogate.

Predicts an AIG (And-Inverter Graph) state's optimization outcome (log10 of the
node count after resyn2) from its graph structure. Two tests:
  - in-distribution: held-out states of the training designs.
  - generalization: an entirely held-out design.

Baseline is a size-only linear fit (log10 nodes after ~ log10 nodes now). The GNN
earns its keep only if it beats that by reading structure, not just size.
"""

from __future__ import annotations

import argparse
import os
import pickle

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader
from torch_geometric.nn import SAGEConv, global_mean_pool

N_TYPES = 4  # const, PI, latch, AND


def target_value(s, kind: str) -> float:
    """after = log10(nodes after resyn2). reduction = size-invariant fraction of
    nodes resyn2 removes from this state (structure-driven, size cannot predict)."""
    if kind == "reduction":
        after = 10 ** s["y"]
        return (s["cur_and"] - after) / max(s["cur_and"], 1)
    return s["y"]


def to_data(s, target: str = "after") -> Data:
    ntype = torch.tensor(s["node_type"])
    x_type = torch.nn.functional.one_hot(ntype, N_TYPES).float()
    ei = torch.tensor(s["edge_index"], dtype=torch.long)
    n = x_type.size(0)
    indeg = torch.zeros(n)
    outdeg = torch.zeros(n)
    indeg.index_add_(0, ei[1], torch.ones(ei.size(1)))
    outdeg.index_add_(0, ei[0], torch.ones(ei.size(1)))
    x = torch.cat([x_type, torch.log1p(indeg).unsqueeze(1),
                   torch.log1p(outdeg).unsqueeze(1)], dim=1)
    d = Data(x=x, edge_index=ei)
    d.y = torch.tensor([target_value(s, target)], dtype=torch.float)
    d.log_cur = torch.tensor([s["log_cur"]], dtype=torch.float)
    d.design = s["design"]
    return d


class GNNSurrogate(nn.Module):
    def __init__(self, in_dim: int, hidden: int = 64):
        super().__init__()
        self.c1 = SAGEConv(in_dim, hidden)
        self.c2 = SAGEConv(hidden, hidden)
        self.c3 = SAGEConv(hidden, hidden)
        self.head = nn.Sequential(nn.Linear(hidden + 1, hidden), nn.ReLU(),
                                  nn.Linear(hidden, 1))

    def forward(self, data):
        x, ei = data.x, data.edge_index
        x = torch.relu(self.c1(x, ei))
        x = torch.relu(self.c2(x, ei))
        x = torch.relu(self.c3(x, ei))
        g = global_mean_pool(x, data.batch)
        g = torch.cat([g, data.log_cur.view(-1, 1)], dim=1)
        return self.head(g).squeeze(-1)


def mae(pred, y):
    return float(np.mean(np.abs(np.array(pred) - np.array(y))))


def baseline_fit(train):
    x = np.array([s["log_cur"] for s in train])
    y = np.array([s["y"] for s in train])
    a, b = np.polyfit(x, y, 1)
    return lambda lc: a * lc + b


def evaluate(model, loader, device):
    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for batch in loader:
            batch = batch.to(device)
            preds += model(batch).cpu().tolist()
            ys += batch.y.cpu().tolist()
    return preds, ys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__),
                    "..", "models", "gnn_dataset.pkl"))
    ap.add_argument("--holdout", nargs="+", default=["jpeg"],
                    help="design id(s) held out entirely")
    ap.add_argument("--target", choices=["after", "reduction"], default="after")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    samples = pickle.load(open(args.data, "rb"))

    hset = set(args.holdout)
    heldout = [s for s in samples if s["design"] in hset]
    pool = [s for s in samples if s["design"] not in hset]
    rng.shuffle(pool)
    n_val = max(1, len(pool) // 5)
    val, train = pool[:n_val], pool[n_val:]
    holdout_label = ",".join(args.holdout) if len(args.holdout) <= 3 else \
        f"{len(args.holdout)} designs"
    print(f"train={len(train)} val={len(val)} heldout({holdout_label})={len(heldout)}")

    device = "cpu"
    tgt = args.target
    tr_loader = DataLoader([to_data(s, tgt) for s in train], batch_size=16, shuffle=True)
    va_loader = DataLoader([to_data(s, tgt) for s in val], batch_size=32)
    ho_loader = DataLoader([to_data(s, tgt) for s in heldout], batch_size=32)

    model = GNNSurrogate(in_dim=N_TYPES + 2).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    lossf = nn.MSELoss()
    for ep in range(args.epochs):
        model.train()
        for batch in tr_loader:
            batch = batch.to(device)
            opt.zero_grad()
            loss = lossf(model(batch), batch.y)
            loss.backward()
            opt.step()

    # GNN metrics
    vp, vy = evaluate(model, va_loader, device)
    hp, hy = evaluate(model, ho_loader, device)
    gnn_val, gnn_ho = mae(vp, vy), mae(hp, hy)

    # baseline: for 'after' a size-only linear fit; for 'reduction' the train mean
    # (size is uninformative for a size-invariant target, so mean is the bar).
    ytr = [target_value(s, tgt) for s in train]
    if tgt == "reduction":
        mean_y = float(np.mean(ytr))
        b_val = mae([mean_y] * len(val), [target_value(s, tgt) for s in val])
        b_ho = mae([mean_y] * len(heldout), [target_value(s, tgt) for s in heldout])
        base_name, unit = "mean-baseline", "reduction-fraction"
    else:
        base = baseline_fit(train)
        b_val = mae([base(s["log_cur"]) for s in val], ytr[:0] + [target_value(s, tgt) for s in val])
        b_ho = mae([base(s["log_cur"]) for s in heldout], [target_value(s, tgt) for s in heldout])
        base_name, unit = "size-baseline", "log10(nodes)"

    print(f"\ntarget={tgt}  MAE in {unit} (lower is better):")
    print(f"  in-distribution val: GNN={gnn_val:.4f}  {base_name}={b_val:.4f}")
    print(f"  held-out ({holdout_label}): GNN={gnn_ho:.4f}  {base_name}={b_ho:.4f}")

    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "models"), exist_ok=True)
    torch.save(model.state_dict(), os.path.join(os.path.dirname(__file__), "..",
               "models", "gnn_surrogate.pt"))
    results = {"gnn_val": gnn_val, "gnn_holdout": gnn_ho,
               "baseline_val": b_val, "baseline_holdout": b_ho,
               "holdout": holdout_label, "n_train": len(train),
               "target": tgt, "unit": unit, "baseline_name": base_name}
    import json
    with open(os.path.join(os.path.dirname(__file__), "..", "results",
              "gnn_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("saved model and results/gnn_results.json")


if __name__ == "__main__":
    main()

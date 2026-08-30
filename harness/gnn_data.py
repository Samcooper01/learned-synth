"""Generate a GNN (Graph Neural Network) dataset of AIG (And-Inverter Graph) states.

For each design we harvest many AIG states (the graph after a random recipe prefix)
and label each with its optimization outcome: the node count after applying resyn2
from that state. The GNN learns to predict that outcome from graph structure.

Random prefixes give thousands of structurally distinct graphs from only a handful
of base designs, which is what lets a GNN show value here.
"""

from __future__ import annotations

import argparse
import math
import os
import pickle
import random

import aig
import aig_graph
import recipes as rc

OUT = os.path.join(os.path.dirname(__file__), "..", "models", "gnn_dataset.pkl")


# size sweep per microbenchmark type (same structure, different scale)
MICRO_SIZES = {"mult": [10, 14, 18], "addchain": [12, 18, 24],
               "muxtree": [5, 6, 7], "decoder": [7, 8, 9],
               "xortree": [24, 36, 48], "cmptree": [12, 18, 24],
               "crossbar": [8, 12, 16], "lfsr": [32, 48, 64]}


def gen_for_design(design: str, n: int, rng: random.Random,
                   source: str = "orfs", preopt: str = "synth",
                   size: int | None = None):
    if source == "micro":
        blif = aig.make_micro_aig(design, preopt=preopt, size=size)
        design_id = design if size is None else f"{design}_{size}"
    else:
        blif = aig.make_start_aig(design, preopt=preopt)
        design_id = design
    samples = []
    for _ in range(n):
        plen = rng.randint(0, 10)
        prefix = tuple(rng.choice(rc.ALPHABET) for _ in range(plen))
        g = aig_graph.extract_graph(blif, prefix)
        if g is None:
            continue
        cur_and = g["counts"][4]
        # label: node count after resyn2 continues from this state
        after = aig.proxy_eval(blif, list(prefix) + list(rc.RESYN2))
        if after is None or cur_and <= 0:
            continue
        samples.append({
            "design": design_id,
            "type": design,
            "node_type": g["node_type"],
            "edge_index": g["edge_index"],
            "cur_and": cur_and,
            "log_cur": math.log10(cur_and),
            "y": math.log10(max(after[0], 1)),   # target: log10 nodes after resyn2
        })
    return samples


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs", nargs="+",
                    default=["gcd", "uart", "aes", "ethmac", "jpeg"])
    ap.add_argument("--source", choices=["orfs", "micro"], default="orfs")
    ap.add_argument("--preopt", choices=["synth", "min"], default="synth")
    ap.add_argument("--sized", action="store_true",
                    help="micro: sweep each type over MICRO_SIZES (size variants)")
    ap.add_argument("--per-design", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    all_samples = []
    for d in args.designs:
        sizes = MICRO_SIZES[d] if (args.sized and args.source == "micro") else [None]
        for sz in sizes:
            s = gen_for_design(d, args.per_design, rng, args.source, args.preopt, sz)
            tag = d if sz is None else f"{d}_{sz}"
            print(f"{tag}: {len(s)} samples", flush=True)
            all_samples += s
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(all_samples, f)
    print(f"wrote {len(all_samples)} samples -> {args.out}")

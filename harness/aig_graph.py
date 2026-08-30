"""Extract an AIG (And-Inverter Graph) state as a graph for a GNN (Graph Neural
Network).

Runs a classic recipe in ABC (And-Inverter Graph optimizer), writes the resulting
AIG as binary AIGER, and parses it into node features + an edge index. This lets a
GNN read the actual graph structure, not hand-crafted summaries.

Node types: constant, primary input, latch, AND gate. Each AND gate has two
incoming edges (its fanins); an edge attribute marks input inversion.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import numpy as np

from aig import YOSYS_ABC

# node-type ids
CONST, PI, LATCH, AND = 0, 1, 2, 3


def _decode_leb(data: bytes, pos: int) -> tuple[int, int]:
    x = shift = 0
    while True:
        ch = data[pos]
        pos += 1
        x |= (ch & 0x7F) << shift
        if not (ch & 0x80):
            return x, pos
        shift += 7


def _write_aiger(blif: str, steps, out: str) -> bool:
    cmds = "; ".join(["strash", *steps, f"write_aiger -s {out}"])
    proc = subprocess.run([YOSYS_ABC, "-c", f"read_blif {blif}; {cmds}"],
                          capture_output=True, text=True, timeout=120)
    return os.path.exists(out) and os.path.getsize(out) > 0


def parse_aiger(path: str):
    """Return (node_type[N], edge_index[2,E], edge_inv[E], counts) for a binary AIGER."""
    with open(path, "rb") as f:
        data = f.read()
    nl = data.index(b"\n")
    header = data[:nl].split()
    assert header[0] == b"aig", "not a binary AIGER file"
    nums = [int(x) for x in header[1:]]
    M, I, L, O, A = nums[:5]
    # AIGER 1.9 optional counts: B (bad), C (constraint), J (justice), F (fairness).
    B = nums[5] if len(nums) > 5 else 0
    C = nums[6] if len(nums) > 6 else 0
    pos = nl + 1

    # ASCII lines before the binary AND section: latches, outputs, bad, constraint.
    for _ in range(L + O + B + C):
        pos = data.index(b"\n", pos) + 1

    n_nodes = 1 + I + L + A            # const 0, inputs, latches, ANDs
    node_type = np.zeros(n_nodes, dtype=np.int64)
    node_type[0] = CONST
    node_type[1:1 + I] = PI
    node_type[1 + I:1 + I + L] = LATCH
    node_type[1 + I + L:] = AND

    def var_to_idx(v: int) -> int:
        return v  # variable v maps to node v (0..M); ANDs occupy I+L+1..M

    src, dst, inv = [], [], []
    for i in range(A):
        g_var = I + L + 1 + i
        lhs = 2 * g_var
        d0, pos = _decode_leb(data, pos)
        rhs0 = lhs - d0
        d1, pos = _decode_leb(data, pos)
        rhs1 = rhs0 - d1
        for rhs in (rhs0, rhs1):
            src.append(var_to_idx(rhs >> 1))
            dst.append(g_var)
            inv.append(rhs & 1)

    edge_index = np.array([src, dst], dtype=np.int64)
    edge_inv = np.array(inv, dtype=np.float32)
    return node_type, edge_index, edge_inv, (M, I, L, O, A)


def extract_graph(blif: str, steps):
    """AIG-state graph after running `steps` on `blif`. Returns dict of arrays."""
    with tempfile.NamedTemporaryFile(suffix=".aig", delete=False) as tf:
        out = tf.name
    try:
        if not _write_aiger(blif, list(steps), out):
            return None
        node_type, edge_index, edge_inv, counts = parse_aiger(out)
    finally:
        if os.path.exists(out):
            os.remove(out)
    return {"node_type": node_type, "edge_index": edge_index,
            "edge_inv": edge_inv, "counts": counts}


if __name__ == "__main__":
    import aig
    blif = aig.make_start_aig("gcd")
    g = extract_graph(blif, ["balance", "rewrite"])
    print("nodes:", len(g["node_type"]), "edges:", g["edge_index"].shape[1],
          "counts (M,I,L,O,A):", g["counts"])
    import collections
    print("node type histogram:", collections.Counter(g["node_type"].tolist()))

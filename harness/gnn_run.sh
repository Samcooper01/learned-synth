#!/bin/bash
set -u
cd "$(dirname "$0")"
LOG=../results/gnn_run.log
echo "[$(date +%H:%M:%S)] generating GNN dataset (5 designs x 150 states)" | tee "$LOG"
python3 gnn_data.py --designs gcd uart aes ethmac jpeg --per-design 150 >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] training GNN surrogate (holdout=jpeg)" | tee -a "$LOG"
python3 gnn_train.py --holdout jpeg --epochs 80 >> "$LOG" 2>&1
echo "[$(date +%H:%M:%S)] GNN done" | tee -a "$LOG"
tail -6 "$LOG"

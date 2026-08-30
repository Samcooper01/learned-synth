#!/bin/bash
# Overnight orchestrator: train RL, evaluate vs resyn2/random (proxy + real QoR),
# write the report. Robust: continues to the report even if eval partially fails.
# Low-thread and modest-parallelism throughout to not crowd the shared machine.
set -u
cd "$(dirname "$0")"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG=../results/overnight_${STAMP}.log
STATUS=../results/overnight_status.txt
mkdir -p ../results ../models

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; echo "$*" > "$STATUS"; }

say "STAGE 1/3: training PPO (gcd, uart), 50000 timesteps"
python3 train_rl.py --train gcd uart --timesteps 50000 --n-envs 4 \
    >> "$LOG" 2>&1
say "training done (exit $?)"

say "STAGE 2/3: evaluating (proxy: gcd uart aes; real QoR: gcd uart)"
python3 eval_policy.py --designs gcd uart aes --real gcd uart --n-random 60 \
    >> "$LOG" 2>&1
say "eval done (exit $?)"

say "STAGE 3/3: writing report"
python3 make_report.py >> "$LOG" 2>&1
say "ALL DONE ($STAMP). See results/RESULTS.md"

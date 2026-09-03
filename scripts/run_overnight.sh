#!/usr/bin/env bash
# Overnight generation protocol (spec section 5). The run is resumable; this script
# is idempotent and is what tmux invokes. Logs tee to logs/fullrun.log.
set -euo pipefail
cd "$(dirname "$0")/.."

SESSION=run
LOG=logs/fullrun.log

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session '$SESSION' already active; attach with: tmux attach -t $SESSION" >&2
  exit 0
fi

mkdir -p logs data/raw
tmux new-session -d -s "$SESSION" \
  "cd $PWD && .venv/bin/python -u -m src.runner 2>&1 | tee -a $LOG"
echo "launched $SESSION; tail -f $LOG to watch"

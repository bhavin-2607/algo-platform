#!/bin/bash
tmux new-session -d -s algo 'cd ~/Algo/algo-platform/backend && uvicorn app.main:app --reload' \; \
  split-window -v 'cd ~/Algo/algo-platform/backend && celery -A app.worker.celery_app worker --loglevel=info' \; \
  split-window -v 'cd ~/Algo/algo-platform/frontend && npm run dev' \; \
  select-layout even-vertical \; \
  attach

#!/usr/bin/env bash
set -euo pipefail
if [ "$(/usr/bin/nvidia-smi -i 0 --query-gpu=mig.mode.current --format=csv,noheader | tr -d "[:space:]")" != Enabled ]; then
  /usr/bin/nvidia-smi -i 0 -mig 1
fi
listing=$(/usr/bin/nvidia-smi -L)
count=$(printf '%s\n' "$listing" | grep -c 'MIG ' || true)
matching=$(printf '%s\n' "$listing" | grep -c 'MIG 1g.16gb' || true)
if [ "$count" -eq 0 ]; then
  /usr/bin/nvidia-smi mig -i 0 -cgi 5,5 -C
elif [ "$count" -ne 2 ] || [ "$matching" -ne 2 ]; then
  echo 'Unexpected MIG configuration; refusing to alter it' >&2
  exit 1
fi

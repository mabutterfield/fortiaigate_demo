#!/usr/bin/env bash
# Experimental: exactly one 1g.16gb MIG instance on each of two GPUs.
# Review the target GPU model and profile ID before running as root.
set -euo pipefail

NVSMI=${FAIG_NVIDIA_SMI:-/usr/bin/nvidia-smi}
profile_id=5
profile_name='MIG 1g.16gb'

# `nvidia-smi -L` does not accept -i on the tested 595 driver. Restrict the
# full listing to the indented MIG entries belonging to the requested card.
gpu_mig_listing() {
  "$NVSMI" -L | awk -v gpu="$1" '
    $0 ~ "^GPU " gpu ": " { selected=1; next }
    /^GPU [0-9]+:/ { selected=0 }
    selected { print }
  '
}

physical_ids=()
while IFS= read -r gpu; do
  physical_ids+=("$gpu")
done < <("$NVSMI" --query-gpu=index --format=csv,noheader | tr -d '[:blank:]')
if [ "${#physical_ids[@]}" -ne 2 ]; then
  echo 'Expected exactly two physical GPUs; refusing to change MIG configuration.' >&2
  exit 1
fi

# Preflight both GPUs before changing either. Never replace an existing layout.
for gpu in "${physical_ids[@]}"; do
  mode=$("$NVSMI" -i "$gpu" --query-gpu=mig.mode.current --format=csv,noheader | tr -d '[:space:]')
  if [ "$mode" != Enabled ] && [ "$mode" != Disabled ]; then
    echo "GPU $gpu does not report a configurable MIG mode; refusing." >&2
    exit 1
  fi
  listing=$(gpu_mig_listing "$gpu")
  count=$(printf '%s\n' "$listing" | grep -c 'MIG ' || true)
  matching=$(printf '%s\n' "$listing" | grep -Fc "$profile_name" || true)
  gi_count=0
  if [ "$mode" = Enabled ]; then
    gi_listing=$("$NVSMI" mig -i "$gpu" -lgi)
    gi_count=$(printf '%s\n' "$gi_listing" | grep -Ec '\|[[:space:]]+[0-9]+[[:space:]]+MIG[[:space:]]' || true)
  fi
  if [ "$count" -gt 1 ] || [ "$count" -ne "$matching" ] || [ "$count" -ne "$gi_count" ]; then
    echo "GPU $gpu has an unexpected MIG layout; refusing to modify it." >&2
    exit 1
  fi
  profiles=$("$NVSMI" mig -i "$gpu" -lgip)
  if ! grep -Eq 'MIG 1g[.]16gb[[:space:]]+5[[:space:]]' <<<"$profiles"; then
    echo "GPU $gpu does not advertise the expected 1g.16gb profile ID 5; refusing." >&2
    exit 1
  fi
done

for gpu in "${physical_ids[@]}"; do
  mode=$("$NVSMI" -i "$gpu" --query-gpu=mig.mode.current --format=csv,noheader | tr -d '[:space:]')
  if [ "$mode" != Enabled ]; then
    "$NVSMI" -i "$gpu" -mig 1
  fi
  listing=$(gpu_mig_listing "$gpu")
  count=$(printf '%s\n' "$listing" | grep -c 'MIG ' || true)
  if [ "$count" -eq 0 ]; then
    "$NVSMI" mig -i "$gpu" -cgi "$profile_id" -C
  fi
done

"$NVSMI" -L

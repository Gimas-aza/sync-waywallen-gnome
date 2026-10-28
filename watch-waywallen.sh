#!/usr/bin/env bash
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
base="${WAYWALLEN_BASE:-$HOME/.var/app/org.waywallen.waywallen}"
config="$base/config/waywallen/config.toml"
database="$base/data/waywallen/waywallen-v2.db"
script="$(dirname "${BASH_SOURCE[0]}")/sync-waywallen-colors"
previous=""
while :; do
    current="$(stat -c '%n:%y:%s' "$config" "$database" "$database-wal" 2>/dev/null || true)"
    if [ -n "$current" ] && [ "$current" != "$previous" ]; then
        if "$script"; then previous="$current"; fi
    fi
    sleep 3
done

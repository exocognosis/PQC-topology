#!/usr/bin/env bash
# One measurement run on the local Docker version (Option A).
# Usage: scripts/local-run.sh <run-name> <seconds>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="${1:-local}"
SECONDS_WINDOW="${2:-120}"
export RUN
COMPOSE=(docker compose -f "$ROOT/local/compose.yaml")

"${COMPOSE[@]}" --profile probe down --remove-orphans >/dev/null 2>&1 || true
rm -rf "$ROOT/results/$RUN"
mkdir -p "$ROOT/results/$RUN"
# throwaway SSH key for the backup pulls of the SSH plane
[ -s "$ROOT/pki/out/ssh-backup" ] || ssh-keygen -q -t ed25519 -N '' -C testbed-backup -f "$ROOT/pki/out/ssh-backup"

echo "== starting estate and clients (window: ${SECONDS_WINDOW}s)"
"${COMPOSE[@]}" up -d
sleep "$SECONDS_WINDOW"
"${COMPOSE[@]}" stop client-modern client-legacy ops

echo "== probing"
"${COMPOSE[@]}" --profile probe run --rm probe

echo "== stopping (flushes captures)"
"${COMPOSE[@]}" --profile probe down

echo "== extracting handshakes and scoring"
sh "$ROOT/tools/extract_handshakes.sh" "$ROOT/results/$RUN"
sh "$ROOT/tools/extract_ssh.sh" "$ROOT/results/$RUN"
(cd "$ROOT" && python3 tools/score.py "results/$RUN")

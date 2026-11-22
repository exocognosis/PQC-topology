#!/usr/bin/env bash
# One measurement run on Hetzner: traffic window, probe, collect, score.
# Usage: scripts/run.sh <run-name> <minutes>
# shellcheck source=scripts/common.sh
source "$(dirname "$0")/common.sh"
RUN="${1:?run name}"
MINUTES="${2:-15}"
OUT="$ROOT/results/$RUN"
mkdir -p "$OUT"

echo "== starting clients (traffic window: $MINUTES min)"
on client "rm -rf /opt/testbed/run/client /opt/testbed/run/probe && mkdir -p /opt/testbed/run/client /opt/testbed/run/probe"
compose client client up -d
sleep $((MINUTES * 60))
compose client client stop

echo "== probing from the client server's private address"
compose client probe run --rm probe

echo "== stopping services (flushes captures)"
for role in "${ROLES_ESTATE[@]}"; do compose "$role" "$role" stop; done

echo "== collecting"
for role in "${ROLES_ESTATE[@]}"; do
  mkdir -p "$OUT/$role"
  rsync -az "root@$(public_ip "$role"):/opt/testbed/run/$role/" "$OUT/$role/"
done
mkdir -p "$OUT/client" "$OUT/probe"
rsync -az "root@$(public_ip client):/opt/testbed/run/client/" "$OUT/client/"
rsync -az "root@$(public_ip client):/opt/testbed/run/probe/" "$OUT/probe/"
hosts_json >"$OUT/inventory.json"

echo "== extracting handshakes and scoring"
sh "$ROOT/tools/extract_handshakes.sh" "$OUT"
(cd "$ROOT" && python3 tools/score.py "$OUT")

echo "== restarting services for further runs (use 'make cloud-destroy' when done)"
for role in "${ROLES_ESTATE[@]}"; do
  on "$role" "rm -rf /opt/testbed/run/$role && mkdir -p /opt/testbed/run/$role"
  compose "$role" "$role" up -d
done
echo "Report: $OUT/report.md"

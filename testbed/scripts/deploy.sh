#!/usr/bin/env bash
# Waits for cloud-init, copies files, builds images and starts the estate
# services on the Hetzner servers created by terraform/.
# shellcheck source=scripts/common.sh
source "$(dirname "$0")/common.sh"

[ -s "$ROOT/pki/out/root-rsa.pem" ] || { echo "Run 'make pki' first." >&2; exit 1; }

for role in "${ROLES_ALL[@]}"; do
  echo "== $role: waiting for cloud-init"
  until on "$role" true 2>/dev/null; do sleep 5; done
  # cloud-init can exit with an error (seen with IPv6 disabled); docker is all we need from it.
  on "$role" "cloud-init status --wait >/dev/null; docker --version"
  # The private NIC is sometimes left down when it is hot-plugged after first boot.
  echo "== $role: checking private address"
  priv=$(hosts_json | jq -r --arg r "$role" '.[$r].private')
  on "$role" "ip -4 -o addr | grep -q ' $priv/' || {
    nic=\$(ip -o link | awk -F': ' '\$2 ~ /^en/ {print \$2; exit}')
    printf 'network:\n  version: 2\n  ethernets:\n    %s:\n      dhcp4: true\n' \"\$nic\" > /etc/netplan/60-testbed-private.yaml
    chmod 600 /etc/netplan/60-testbed-private.yaml && netplan apply && sleep 3
  }; ip -4 -o addr | grep -q ' $priv/' || { echo 'private address $priv missing' >&2; exit 1; }"
  echo "== $role: copying files"
  push "$role"
  echo "== $role: building images"
  on "$role" "cd /opt/testbed && docker build -q -t pqc-nginx images/pqc-nginx"
  if [ "$role" = client ]; then
    on "$role" "cd /opt/testbed && docker build -q -t pqc-legacy-client images/legacy-client"
  fi
done

for role in "${ROLES_ESTATE[@]}"; do
  echo "== $role: starting service"
  on "$role" "rm -rf /opt/testbed/run/$role && mkdir -p /opt/testbed/run/$role"
  compose "$role" "$role" up -d
done
echo "Estate is up. Gateway public address: $(public_ip gw)"

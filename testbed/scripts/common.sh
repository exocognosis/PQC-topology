#!/usr/bin/env bash
# Shared helpers for the Hetzner scripts. Sourced, not executed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/terraform"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
KNOWN_HOSTS="$ROOT/.ssh_known_hosts"
ROLES_ESTATE=(gw lb appa appb data)
ROLES_ALL=(gw lb appa appb data client)

ssh_opts=(-i "$SSH_KEY" -o "UserKnownHostsFile=\"$KNOWN_HOSTS\"" -o StrictHostKeyChecking=accept-new
          -o ConnectTimeout=10 -o BatchMode=yes)
# rsync's remote shell, quoted so paths with spaces survive rsync's own splitting.
# rsync (and macOS openrsync) parse single quotes in this string themselves.
RSYNC_RSH="ssh"
# shellcheck disable=SC2089
for _a in "${ssh_opts[@]}"; do RSYNC_RSH+=" '$_a'"; done
# shellcheck disable=SC2090
export RSYNC_RSH
export ROLES_ESTATE ROLES_ALL

hosts_json() { terraform -chdir="$TF_DIR" output -json hosts; }
public_ip() { hosts_json | jq -r --arg r "$1" '.[$r].public'; }

on() {  # on <role> <command...>
  local role=$1; shift
  # shellcheck disable=SC2029  # commands are composed locally on purpose
  ssh "${ssh_opts[@]}" "root@$(public_ip "$role")" "$@"
}

push() {  # push <role>: copy the testbed files the server needs
  local role=$1
  rsync -az --delete \
    --exclude results --exclude terraform --exclude .ssh_known_hosts --exclude local \
    --exclude 'pki/out/*.key' \
    "$ROOT/" "root@$(public_ip "$role"):/opt/testbed/"
  # Each server receives only its own private keys.
  local keys=()
  case "$role" in
    gw)     keys=(gw.key) ;;
    lb)     keys=(lb.key lb-client.key) ;;
    appa)   keys=(appa.key) ;;
    appb)   keys=(appb.key) ;;
    data)   keys=(data.key) ;;
    client) keys=() ;;
  esac
  for k in ${keys[@]+"${keys[@]}"}; do
    rsync -az "$ROOT/pki/out/$k" "root@$(public_ip "$role"):/opt/testbed/pki/out/$k"
  done
}

compose() {  # compose <role> <profile> <args...>
  local role=$1 profile=$2; shift 2
  on "$role" "cd /opt/testbed && GW_PUBLIC_IP='$(public_ip gw)' docker compose -f hetzner/compose.yaml --profile $profile $*"
}

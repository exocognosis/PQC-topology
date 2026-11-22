#!/bin/sh
# Pulls a backup of the records data class from data over SSH, using the client's
# default key-exchange preferences (OpenSSH 10 in pqc-nginx, OpenSSH 8.x in the legacy image).
INTERVAL="${SSH_INTERVAL:-5}"
OUT="${OUT:-/run-out}"
CLASS="${CLIENT_CLASS:-ssh}"
mkdir -p "$OUT"
LOG="$OUT/ssh-$CLASS.log"
install -m 600 /pki/ssh-backup /tmp/ssh-backup
echo "start $(date -u +%FT%TZ) class=$CLASS $(ssh -V 2>&1)" >>"$LOG"
while :; do
  if ssh -i /tmp/ssh-backup -o BatchMode=yes -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5 \
      root@data cat /srv/records/records.json >/dev/null 2>>"$LOG"; then
    echo "$(date -u +%FT%TZ) ok" >>"$LOG"
  else
    echo "$(date -u +%FT%TZ) fail" >>"$LOG"
  fi
  sleep "$INTERVAL"
done

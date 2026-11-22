#!/bin/sh
# Roles: gw | lb | appa | appb | data  -> nginx (+ optional packet capture)
#        client                        -> traffic generator
#        probe                         -> run the command given
set -eu
ROLE="${ROLE:-}"
OUT="${OUT:-/run-out}"
mkdir -p "$OUT"

if [ "${CAPTURE:-0}" = "1" ] && [ "$ROLE" != "client" ] && [ "$ROLE" != "probe" ]; then
  tcpdump -i any -U -s 0 -w "$OUT/capture.pcap" \
    'tcp and (port 443 or port 8443 or port 9443 or port 9444 or port 7443 or port 22)' \
    >"$OUT/tcpdump.log" 2>&1 &
fi

case "$ROLE" in
  client)
    exec /bin/sh /clients/traffic.sh
    ;;
  probe)
    exec "$@"
    ;;
  data)
    (cd /srv/records && python3 -m http.server 8000 --bind 127.0.0.1 >"$OUT/records.log" 2>&1 &)
    if [ "${SSHD:-0}" = "1" ]; then
      # SSH plane: backups of the records data class are pulled over SSH (port 22).
      ssh-keygen -A >/dev/null
      install -m 600 /pki/ssh-backup.pub /etc/ssh/backup_authorized_keys
      /usr/sbin/sshd -D -e -o LogLevel=DEBUG1 -o PasswordAuthentication=no \
        -o PermitRootLogin=prohibit-password -o AuthorizedKeysFile=/etc/ssh/backup_authorized_keys \
        -o "KexAlgorithms=${SSH_KEX}" >"$OUT/sshd.log" 2>&1 &
    fi
    exec nginx -g 'daemon off;'
    ;;
  gw|lb|appa|appb)
    if [ "${SSH_PULL:-0}" = "1" ]; then
      /bin/sh /clients/ssh-pull.sh &
    fi
    exec nginx -g 'daemon off;'
    ;;
  *)
    echo "unknown ROLE '$ROLE'" >&2
    exit 2
    ;;
esac

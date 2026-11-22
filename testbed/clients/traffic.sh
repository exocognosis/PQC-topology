#!/bin/sh
# Generates read traffic through the edge gateway.
#   /records  data -> appa -> lb -> gw -> client   (records data class)
#   /enrich   appb -> appa -> lb -> gw -> client   (profile data class)
#   /cycle    appa -> appb -> appa ...             (mutual-TLS call cycle)
INTERVAL="${INTERVAL:-2}"
OUT="${OUT:-/run-out}"
CLASS="${CLIENT_CLASS:-client}"
mkdir -p "$OUT"
LOG="$OUT/$CLASS.log"
echo "start $(date -u +%FT%TZ) class=$CLASS $(openssl version)" >>"$LOG"
while :; do
  for path in records enrich cycle; do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
      --cacert /pki/root-rsa.pem "https://gw/$path" || echo 000)
    echo "$(date -u +%FT%TZ) $path $code" >>"$LOG"
  done
  sleep "$INTERVAL"
done

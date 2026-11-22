#!/bin/sh
# Extracts negotiated parameters from captured ServerHello / ServerKeyExchange messages.
# Usage: tools/extract_handshakes.sh results/<run>
# Output: results/<run>/<host>/handshakes.tsv, columns:
#   src_ip src_port dst_ip supported_version cipher_suite key_share_group server_named_curve
set -eu
RUN_DIR="$1"
for pcap in "$RUN_DIR"/*/capture.pcap; do
  [ -s "$pcap" ] || continue
  dir=$(cd "$(dirname "$pcap")" && pwd)
  docker run --rm -v "$dir:/d" pqc-analysis \
    tshark -r /d/capture.pcap -n -Y 'tls.handshake.type == 2 || tls.handshake.type == 12' \
      -T fields -E separator=/t -E occurrence=f \
      -e ip.src -e tcp.srcport -e ip.dst \
      -e tls.handshake.extensions.supported_version -e tls.handshake.ciphersuite \
      -e tls.handshake.extensions_key_share_group -e tls.handshake.server_named_curve \
    >"$dir/handshakes.tsv" 2>"$dir/tshark.err" || true
  echo "$dir/handshakes.tsv: $(wc -l <"$dir/handshakes.tsv" | tr -d ' ') records"
done

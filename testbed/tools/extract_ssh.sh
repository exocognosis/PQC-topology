#!/bin/sh
# Extracts SSH KEXINIT algorithm lists (sent in clear) from the captured pcaps.
# Usage: tools/extract_ssh.sh results/<run>
# Output: results/<run>/<host>/ssh_kexinit.tsv, columns:
#   src_ip src_port dst_ip dst_port kex_algorithms
set -eu
RUN_DIR="$1"
for pcap in "$RUN_DIR"/*/capture.pcap; do
  [ -s "$pcap" ] || continue
  dir=$(cd "$(dirname "$pcap")" && pwd)
  docker run --rm -v "$dir:/d" pqc-analysis \
    tshark -r /d/capture.pcap -n -Y 'ssh.message_code == 20' \
      -T fields -E separator=/t -E occurrence=f \
      -e ip.src -e tcp.srcport -e ip.dst -e tcp.dstport -e ssh.kex_algorithms \
    >"$dir/ssh_kexinit.tsv" 2>"$dir/tshark-ssh.err" || true
  n=$(wc -l <"$dir/ssh_kexinit.tsv" | tr -d ' ')
  [ "$n" -gt 0 ] && echo "$dir/ssh_kexinit.tsv: $n records"
done
exit 0

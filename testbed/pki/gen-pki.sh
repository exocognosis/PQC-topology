#!/bin/sh
# Generates the testbed PKI with OpenSSL 3.5. Run inside the pqc-nginx image:
#   docker run --rm -v "$PWD/pki:/pki" --entrypoint sh pqc-nginx /pki/gen-pki.sh /pki/out
#
# Trust graph (ground truth, see groundtruth.json):
#   root-rsa   RSA-4096, 20 years, "never rotated" legacy root
#     int-ecdsa  ECDSA P-256 issuing CA
#       gw (ECDSA), lb (RSA-2048 for RSA key transport), appa, appb (ECDSA, mTLS),
#       lb-client (mTLS client), fw-signer (code signing -> firmware.bin.p7s)
#   root-mldsa ML-DSA-65 root
#       data (ML-DSA-65 leaf)
set -eu
OUT="${1:-/pki/out}"
mkdir -p "$OUT"
cd "$OUT"
rm -f ./*.pem ./*.key ./*.csr ./*.srl ./*.p7s ./*.bin

openssl req -x509 -newkey rsa:4096 -nodes -keyout root-rsa.key -out root-rsa.pem -days 7300 \
  -subj "/O=PQC Testbed/CN=Legacy Root (RSA-4096)" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

openssl req -x509 -newkey ML-DSA-65 -nodes -keyout root-mldsa.key -out root-mldsa.pem -days 3650 \
  -subj "/O=PQC Testbed/CN=PQ Root (ML-DSA-65)" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -keyout int-ecdsa.key -out int-ecdsa.csr \
  -subj "/O=PQC Testbed/CN=Issuing CA (ECDSA P-256)" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl x509 -req -in int-ecdsa.csr -CA root-rsa.pem -CAkey root-rsa.key -CAcreateserial \
  -days 1825 -copy_extensions copyall -out int-ecdsa.pem

# leaf NAME KEYSPEC CA CAKEY DAYS EXTKEYUSAGE [SAN]
leaf() {
  name=$1; keyspec=$2; ca=$3; cakey=$4; days=$5; eku=$6; san=${7:-}
  case "$keyspec" in
    ec)     set -- -newkey ec -pkeyopt ec_paramgen_curve:P-256 ;;
    rsa)    set -- -newkey rsa:2048 ;;
    mldsa)  set -- -newkey ML-DSA-65 ;;
  esac
  if [ -n "$san" ]; then
    openssl req "$@" -nodes -keyout "$name.key" -out "$name.csr" -subj "/O=PQC Testbed/CN=$name" \
      -addext "basicConstraints=CA:FALSE" -addext "extendedKeyUsage=$eku" -addext "subjectAltName=$san"
  else
    openssl req "$@" -nodes -keyout "$name.key" -out "$name.csr" -subj "/O=PQC Testbed/CN=$name" \
      -addext "basicConstraints=CA:FALSE" -addext "extendedKeyUsage=$eku"
  fi
  openssl x509 -req -in "$name.csr" -CA "$ca" -CAkey "$cakey" -CAcreateserial -days "$days" \
    -copy_extensions copyall -out "$name.pem"
}

leaf gw        ec    int-ecdsa.pem  int-ecdsa.key  398  serverAuth            DNS:gw
leaf lb        rsa   int-ecdsa.pem  int-ecdsa.key  398  serverAuth            DNS:lb
leaf appa      ec    int-ecdsa.pem  int-ecdsa.key  398  serverAuth,clientAuth DNS:appa
leaf appb      ec    int-ecdsa.pem  int-ecdsa.key  398  serverAuth,clientAuth DNS:appb
leaf lb-client ec    int-ecdsa.pem  int-ecdsa.key  398  clientAuth
leaf fw-signer ec    int-ecdsa.pem  int-ecdsa.key  1095 codeSigning
leaf data      mldsa root-mldsa.pem root-mldsa.key 398  serverAuth            DNS:data

for n in gw lb appa appb lb-client fw-signer; do cat "$n.pem" int-ecdsa.pem >"$n.chain.pem"; done
cp data.pem data.chain.pem
cat int-ecdsa.pem root-rsa.pem >clientca.pem

# Signed firmware artifact (detached CMS signature) for the static scan.
head -c 65536 /dev/urandom >firmware.bin
openssl cms -sign -binary -in firmware.bin -signer fw-signer.pem -inkey fw-signer.key \
  -certfile int-ecdsa.pem -outform DER -out firmware.bin.p7s

rm -f ./*.csr ./*.srl
chmod 0644 ./*.pem ./*.p7s ./*.bin
chmod 0644 ./*.key   # test keys only; containers run nginx as an unprivileged worker
echo "PKI written to $OUT"
ls -1 "$OUT"

# nginx, curl and probe tooling linked against OpenSSL 3.5 (ML-KEM, ML-DSA).
FROM alpine:3.22
RUN apk add --no-cache nginx openssl curl python3 tcpdump nmap nmap-scripts \
      openssh-server openssh-client \
 && openssl version && ssh -V \
 && openssl list -kem-algorithms | grep -qi mlkem \
 && openssl list -signature-algorithms | grep -qi mldsa
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Legacy client: curl on OpenSSL 1.1.1 (no ML-KEM) and an OpenSSH 8.x client.
# Negotiates classical X25519 for TLS and, by default, classical curve25519 for SSH.
FROM alpine:3.14
RUN apk add --no-cache curl openssl openssh-client && openssl version && ssh -V
ENV ROLE=client
ENTRYPOINT ["/bin/sh", "/clients/traffic.sh"]

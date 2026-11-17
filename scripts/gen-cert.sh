#!/bin/sh
# Genera un certificado TLS autofirmado para el laboratorio (solo si no existe).
# HOST_IP define la IP de la red interna; por defecto 127.0.0.1.
set -e
if [ -f /certs/server.crt ] && [ -f /certs/server.key ]; then
  echo "Certificado existente: no se regenera."
  exit 0
fi
apk add --no-cache openssl >/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout /certs/server.key -out /certs/server.crt \
  -subj "/O=Nexo Unificado/CN=nexo.local" \
  -addext "subjectAltName=DNS:localhost,DNS:nexo.local,IP:127.0.0.1,IP:${HOST_IP:-127.0.0.1}"
echo "Certificado generado en ./certs (SAN incluye ${HOST_IP:-127.0.0.1})"
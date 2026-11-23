#!/bin/sh
# Genera un certificado TLS autofirmado para el laboratorio. Lo regenera si
# cambia HOST_IP, porque los navegadores validan la IP mediante el campo SAN.
set -e
HOST_IP=${HOST_IP:-127.0.0.1}
apk add --no-cache openssl >/dev/null

# Compose antiguo puede haber creado un directorio vacío para un bind de archivo.
if [ -d /certs/server.crt ]; then
  rmdir /certs/server.crt
fi

publish_public_certificate() {
  mkdir -p /certs/public
  cp /certs/server.crt /certs/public/server.crt.tmp
  mv /certs/public/server.crt.tmp /certs/public/server.crt
}

if [ -f /certs/server.crt ] && [ -f /certs/server.key ] \
  && openssl x509 -in /certs/server.crt -noout -ext subjectAltName \
    | grep -F "IP Address:${HOST_IP}" >/dev/null 2>&1; then
  echo "Certificado existente: ya incluye ${HOST_IP}; no se regenera."
  publish_public_certificate
  exit 0
fi

echo "Generando certificado con SAN para ${HOST_IP}..."
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout /certs/server.key -out /certs/server.crt \
  -subj "/O=Nexo Unificado/CN=nexo.local" \
  -addext "subjectAltName=DNS:localhost,DNS:nexo.local,IP:127.0.0.1,IP:${HOST_IP}"
publish_public_certificate
echo "Certificado actualizado en ./certs (SAN incluye ${HOST_IP})."

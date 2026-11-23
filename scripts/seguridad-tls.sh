#!/usr/bin/env bash
# testssl.sh en contenedor temporal; el objetivo es el proxy local publicado.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
OUT="$PWD/evidencias/seguridad-infra"
mkdir -p "$OUT"
# El adaptador local invoca docker.exe: necesita una ruta Windows para el bind.
OUT_DOCKER="$OUT"
if command -v wslpath >/dev/null 2>&1 && grep -qi microsoft /proc/version; then
  OUT_DOCKER="$(wslpath -w "$OUT")"
fi
# testssl devuelve no cero cuando encuentra advertencias; el reporte igual es valido.
docker run --rm --user root -v "$OUT_DOCKER:/out" drwetter/testssl.sh:latest \
  --fast --jsonfile /out/testssl.json --htmlfile /out/testssl.html \
  --logfile /out/testssl.txt host.docker.internal:8443 || true
test -s "$OUT/testssl.txt"

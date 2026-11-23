#!/usr/bin/env bash
# H15 · Escaneo de imagenes con Trivy en contenedor temporal (nada se instala en el host).
# Uso: scripts/h15-trivy.sh antes|despues
set -u
FASE="${1:?uso: $0 antes|despues}"
OUT="evidencias/h15/$FASE"
mkdir -p "$OUT" .trivy-cache
export MSYS_NO_PATHCONV=1
docker compose config --images | sort -u > evidencias/h15/imagenes.txt
while read -r img; do
  [ -z "$img" ] && continue
  n=$(echo "$img" | tr '/:' '__')
  echo ">> $img"
  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$PWD/.trivy-cache:/root/.cache" -v "$PWD/$OUT:/out" \
    aquasec/trivy:latest image --severity HIGH,CRITICAL --scanners vuln \
    --format json --output "/out/$n.json" "$img" > "$OUT/$n.log" 2>&1 \
    && docker run --rm -v "$PWD/$OUT:/out" aquasec/trivy:latest convert --format table \
       --output "/out/$n.txt" "/out/$n.json" >/dev/null 2>&1 \
    || echo "   (no escaneada: ver $OUT/$n.log)"
done < evidencias/h15/imagenes.txt

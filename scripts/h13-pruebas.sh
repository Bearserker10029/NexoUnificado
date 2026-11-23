#!/usr/bin/env bash
# H13 · Pruebas permitidas/denegadas. Ejecutar desde un host de la VLAN a probar.
# Uso: scripts/h13-pruebas.sh <vlan10|vlan20|vlan99|wireguard>
set -u
SRV=192.168.30.10
V="${1:?uso: $0 vlan10|vlan20|vlan99|wireguard}"
OUT="evidencias/h13/pruebas-$V.txt"; mkdir -p evidencias/h13
tcp() { if timeout 4 bash -c "</dev/tcp/$SRV/$2" 2>/dev/null; then echo "$1 tcp/$2: ABIERTO"; else echo "$1 tcp/$2: BLOQUEADO"; fi; }
{
  echo "# $(date -Is) origen=$V host=$(hostname) ip=$(hostname -I)"
  tcp HTTPS 8443; tcp SSH 22; tcp SIP-TLS 5061
  echo "healthz:"; curl -sk --max-time 4 "https://$SRV:8443/element/" -o /dev/null -w "  https 8443 -> HTTP %{http_code}\n" || echo "  https 8443 -> fallo"
  [ "$V" = wireguard ] && sudo wg show
} | tee "$OUT"

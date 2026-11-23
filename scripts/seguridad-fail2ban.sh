#!/usr/bin/env bash
# Prueba local con identidad falsa; conserva el bloqueo y lo retira al final.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
OUT=evidencias/seguridad-infra
mkdir -p "$OUT"
docker exec nexo-fail2ban fail2ban-client status | tee "$OUT/fail2ban-jails.txt"
for jail in nexo-keycloak asterisk; do
  docker exec nexo-fail2ban fail2ban-client status "$jail" | tee "$OUT/fail2ban-$jail-antes.txt"
done
: > "$OUT/intentos-keycloak.txt"
for n in 1 2 3 4 5 6; do
  code=$(curl -sk --max-time 5 -o /dev/null -w '%{http_code}' \
    -X POST 'https://127.0.0.1:8443/keycloak/realms/nexo/protocol/openid-connect/token' \
    --data 'grant_type=password&client_id=prueba-bloqueo&username=usuario-inexistente&password=clave-falsa' || true)
  printf 'Intento %s: HTTP %s (credenciales falsas)\n' "$n" "$code" | tee -a "$OUT/intentos-keycloak.txt"
  sleep 1
done
docker exec nexo-fail2ban fail2ban-client status nexo-keycloak | tee "$OUT/fail2ban-keycloak-bloqueo.txt"
banned=$(docker exec nexo-fail2ban fail2ban-client status nexo-keycloak | sed -n 's/.*Banned IP list:[[:space:]]*//p')
if [ -z "$banned" ]; then
  echo 'ERROR: no se registro una IP bloqueada; la prueba no es valida.' >&2
  exit 1
fi
for ip in $banned; do
  docker exec nexo-fail2ban fail2ban-client set nexo-keycloak unbanip "$ip" >/dev/null
done
docker exec nexo-fail2ban fail2ban-client status nexo-keycloak | tee "$OUT/fail2ban-keycloak-despues.txt"

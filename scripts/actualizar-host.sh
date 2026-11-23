#!/bin/sh
# Actualiza el estado persistido al cambiar NEXO_HOST. Compose ejecuta este
# script automaticamente mediante el servicio host-update.
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
if [ "${NEXO_HOST_UPDATE_CONTAINER:-}" != 1 ]; then
  [ -f .env ] || { echo "No existe .env." >&2; exit 1; }
  ENV_NORMALIZED="/tmp/nexo-host-update.env"
  sed 's/\r$//' .env > "$ENV_NORMALIZED"
  . "$ENV_NORMALIZED"
  rm -f "$ENV_NORMALIZED"
fi
: "${NEXO_HOST:?Define NEXO_HOST en .env}"
: "${KC_ADMIN_USER:?Define KC_ADMIN_USER en .env}"
: "${KC_ADMIN_PASSWORD:?Define KC_ADMIN_PASSWORD en .env}"
: "${KC_VOIP_CLIENT_SECRET:?Define KC_VOIP_CLIENT_SECRET en .env}"
NEXO_URL="https://${NEXO_HOST}:8443"

echo "Actualizando OIDC para ${NEXO_URL}..."
kcadm() {
  docker exec nexo-keycloak /opt/keycloak/bin/kcadm.sh "$@"
}

READY=0
attempt=0
while [ "$attempt" -lt 30 ]; do
  attempt=$((attempt + 1))
  if kcadm config credentials \
    --server http://localhost:8080 --realm master \
    --user "$KC_ADMIN_USER" --password "$KC_ADMIN_PASSWORD" >/dev/null 2>&1; then
    READY=1
    break
  fi
  echo "Esperando a Keycloak (intento ${attempt}/30)..."
  sleep 5
done
[ "$READY" = "1" ] || { echo "Keycloak no estuvo listo a tiempo." >&2; exit 1; }

NC_ID=$(kcadm get clients -r nexo -q clientId=nextcloud --fields id --format csv --noquotes)
[ -n "$NC_ID" ] || { echo "No existe el cliente nextcloud." >&2; exit 1; }
kcadm update "clients/${NC_ID}" -r nexo \
  -s "redirectUris=[\"${NEXO_URL}/docs/apps/user_oidc/code*\"]" \
  -s "webOrigins=[\"${NEXO_URL}\"]" \
  -s "rootUrl=${NEXO_URL}" \
  -s "baseUrl=/docs/" \
  -s "attributes={\"post.logout.redirect.uris\":\"${NEXO_URL}/docs/*\"}"
echo "Cliente nextcloud actualizado."

SYN_ID=$(kcadm get clients -r nexo -q clientId=synapse --fields id --format csv --noquotes)
[ -n "$SYN_ID" ] || { echo "No existe el cliente synapse." >&2; exit 1; }
kcadm update "clients/${SYN_ID}" -r nexo \
  -s "redirectUris=[\"${NEXO_URL}/_synapse/client/oidc/callback\"]" \
  -s "webOrigins=[\"${NEXO_URL}\"]" \
  -s 'attributes."post.logout.redirect.uris"=+'
echo "Cliente synapse actualizado para el mismo origen HTTPS."

# Los realm existentes no importan clientes nuevos: crea voip si hace falta.
VOIP_ID=$(kcadm get clients -r nexo -q clientId=voip --fields id --format csv --noquotes)
if [ -z "$VOIP_ID" ]; then
  kcadm create clients -r nexo \
    -s clientId=voip \
    -s name="Telefonia WebRTC" \
    -s enabled=true \
    -s protocol=openid-connect \
    -s publicClient=false \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=false \
    -s "secret=${KC_VOIP_CLIENT_SECRET}" >/dev/null
  VOIP_ID=$(kcadm get clients -r nexo -q clientId=voip --fields id --format csv --noquotes)
fi
kcadm update "clients/${VOIP_ID}" -r nexo \
  -s "secret=${KC_VOIP_CLIENT_SECRET}" \
  -s "redirectUris=[\"${NEXO_URL}/voip-sso/callback\"]" \
  -s "webOrigins=[\"${NEXO_URL}\"]" \
  -s "rootUrl=${NEXO_URL}/voip/" \
  -s "baseUrl=/voip/" \
  -s "attributes={\"post.logout.redirect.uris\":\"${NEXO_URL}/voip/*\",\"pkce.code.challenge.method\":\"S256\"}"
echo "Cliente voip creado/actualizado."

# El cliente público usa PKCE S256. Crea o actualiza en realms ya persistidos.
. ./scripts/configurar-asistente-oidc.sh

# Synapse comparte esquema, IP y puerto con Nextcloud/Element.
echo "Actualizando homeserver.yaml de Synapse..."
docker exec nexo-synapse sh -c "
  set -eu
  sed -i -E \
    -e \"s#issuer: \\\"https://[^/\\\"]+/keycloak/realms/nexo\\\"#issuer: \\\"${NEXO_URL}/keycloak/realms/nexo\\\"#\" \
    -e \"s#authorization_endpoint: \\\"https://[^/\\\"]+/keycloak/realms/nexo/protocol/openid-connect/auth\\\"#authorization_endpoint: \\\"${NEXO_URL}/keycloak/realms/nexo/protocol/openid-connect/auth\\\"#\" \
    -e \"s#token_endpoint: \\\"[^\\\"]+\\\"#token_endpoint: \\\"${NEXO_URL}/keycloak/realms/nexo/protocol/openid-connect/token\\\"#\" \
    -e \"s#userinfo_endpoint: \\\"[^\\\"]+\\\"#userinfo_endpoint: \\\"${NEXO_URL}/keycloak/realms/nexo/protocol/openid-connect/userinfo\\\"#\" \
    -e \"s#jwks_uri: \\\"[^\\\"]+\\\"#jwks_uri: \\\"${NEXO_URL}/keycloak/realms/nexo/protocol/openid-connect/certs\\\"#\" \
    -e \"s#x_forwarded: false#x_forwarded: true#g\" \
    /data/homeserver.yaml
  if grep -q '^public_baseurl:' /data/homeserver.yaml; then
    sed -i -E \"s#^public_baseurl:.*#public_baseurl: '${NEXO_URL}/'#\" /data/homeserver.yaml
  else
    sed -i \"/^server_name:/a public_baseurl: '${NEXO_URL}/'\" /data/homeserver.yaml
  fi
  if ! grep -q '^sso:' /data/homeserver.yaml; then
    printf '\nsso:\n  client_whitelist:\n    - \"%s/element/\"\n' '${NEXO_URL}' >> /data/homeserver.yaml
  else
    sed -i -E \"s#- \\\"https://[^\\\"]+/element/\\\"#- \\\"${NEXO_URL}/element/\\\"#\" /data/homeserver.yaml
  fi
"
docker restart nexo-synapse >/dev/null
echo "Synapse actualizado y reiniciado."

# NEXTCLOUD_TRUSTED_DOMAINS solo se aplica en la instalacion inicial.
echo "Comprobando trusted_domains de Nextcloud..."
occ() { docker exec --user www-data nexo-nextcloud php occ "$@"; }
ALREADY=$(occ config:system:get trusted_domains --output=json 2>/dev/null | grep -c "\"${NEXO_HOST}\"" || true)
if [ "$ALREADY" = "0" ]; then
  NEXT_IDX=$(occ config:system:get trusted_domains --output=json 2>/dev/null | docker exec -i nexo-nextcloud php -r '
    $d = json_decode(stream_get_contents(STDIN), true);
    echo is_array($d) ? count($d) : 0;
  ')
  occ config:system:set trusted_domains "$NEXT_IDX" --value="$NEXO_HOST" >/dev/null
  echo "${NEXO_HOST} agregado a trusted_domains."
else
  echo "${NEXO_HOST} ya estaba en trusted_domains."
fi

echo "Actualizacion de host completada."

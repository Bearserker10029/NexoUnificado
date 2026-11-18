#!/bin/sh
# Corrige el estado que "docker compose up -d" NO actualiza solo al cambiar
# NEXO_HOST en .env: Keycloak importa su realm una sola vez (estrategia
# IGNORE_EXISTING), Synapse escribe sus oidc_providers en homeserver.yaml una
# sola vez (ver synapse-oidc-patch en docker-compose.yml) y Nextcloud solo
# lee NEXTCLOUD_TRUSTED_DOMAINS en su instalacion inicial (no en cada
# arranque), asi que los tres conservan el NEXO_HOST anterior en datos ya
# persistidos hasta que este script los corrige con kcadm/sed/occ dentro de
# los contenedores. Todo lo demas (Element, OVERWRITEHOST de Nextcloud,
# Asterisk, Jitsi) ya se adapta solo al recrear los contenedores porque lee
# NEXO_HOST en cada arranque.
#
# Uso, desde la raiz del repo, despues de editar NEXO_HOST en .env y de
# "docker compose up -d":
#   ./scripts/actualizar-host.sh
set -eu
# Evita que Git Bash en Windows reescriba las rutas /opt/..., /data/...
# como rutas de Windows al pasarlas a "docker exec" (no afecta a Linux/macOS).
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "No existe .env. Copia .env.example primero." >&2; exit 1; }
# shellcheck disable=SC1091
. ./.env

: "${NEXO_HOST:?Define NEXO_HOST en el archivo .env}"
: "${KC_ADMIN_USER:?Define KC_ADMIN_USER en el archivo .env}"
: "${KC_ADMIN_PASSWORD:?Define KC_ADMIN_PASSWORD en el archivo .env}"

NEXO_URL="https://${NEXO_HOST}:8443"
echo "Actualizando clientes de Keycloak y endpoints OIDC de Synapse para NEXO_HOST=${NEXO_HOST} ($NEXO_URL)..."

kcadm() {
  docker exec nexo-keycloak /opt/keycloak/bin/kcadm.sh "$@"
}

kcadm config credentials \
  --server http://localhost:8080 --realm master \
  --user "$KC_ADMIN_USER" --password "$KC_ADMIN_PASSWORD" >/dev/null

NC_ID=$(kcadm get clients -r nexo -q clientId=nextcloud --fields id --format csv --noquotes)
if [ -z "$NC_ID" ]; then
  echo "No se encontro el cliente 'nextcloud' en el realm 'nexo'." >&2
  exit 1
fi
# rootUrl SIN "/docs/" + baseUrl "/docs/" (no al reves): Keycloak las
# concatena para el enlace "Back to Application" de sus propias pantallas de
# error, y con las dos conteniendo "/docs/" quedaba duplicado
# (".../docs/docs/", pagina no encontrada). post.logout.redirect.uris es un
# campo aparte de redirectUris: sin el, Keycloak devuelve "Invalid redirect
# uri" al cerrar sesion (single logout) y la sesion de Keycloak nunca
# termina, asi que el redirect directo de la raiz vuelve a autenticar sola.
kcadm update "clients/${NC_ID}" -r nexo \
  -s "redirectUris=[\"${NEXO_URL}/docs/apps/user_oidc/code*\"]" \
  -s "webOrigins=[\"${NEXO_URL}\"]" \
  -s "rootUrl=${NEXO_URL}" \
  -s "baseUrl=/docs/" \
  -s "attributes={\"post.logout.redirect.uris\":\"${NEXO_URL}/docs/*\"}"
echo "Cliente 'nextcloud' actualizado."

SYN_ID=$(kcadm get clients -r nexo -q clientId=synapse --fields id --format csv --noquotes)
if [ -z "$SYN_ID" ]; then
  echo "No se encontro el cliente 'synapse' en el realm 'nexo'." >&2
  exit 1
fi
kcadm update "clients/${SYN_ID}" -r nexo \
  -s "redirectUris=[\"http://${NEXO_HOST}:8008/_synapse/client/oidc/callback\"]" \
  -s "webOrigins=[\"http://${NEXO_HOST}:8008\",\"${NEXO_URL}\"]" \
  -s 'attributes."post.logout.redirect.uris"=+'
echo "Cliente 'synapse' actualizado."

# issuer/authorization_endpoint del proveedor OIDC de Synapse: el navegador
# necesita la URL externa (ver matrix/oidc-providers.yaml.template); token,
# userinfo y jwks ya usan el nombre interno "keycloak" y no cambian.
echo "Actualizando issuer/authorization_endpoint en homeserver.yaml de Synapse..."
docker exec nexo-synapse sh -c "
  sed -i -E \
    -e \"s#issuer: \\\"https://[^/\\\"]+/keycloak/realms/nexo\\\"#issuer: \\\"${NEXO_URL}/keycloak/realms/nexo\\\"#\" \
    -e \"s#authorization_endpoint: \\\"https://[^/\\\"]+/keycloak/realms/nexo/protocol/openid-connect/auth\\\"#authorization_endpoint: \\\"${NEXO_URL}/keycloak/realms/nexo/protocol/openid-connect/auth\\\"#\" \
    /data/homeserver.yaml
"
docker restart nexo-synapse >/dev/null
echo "homeserver.yaml corregido y nexo-synapse reiniciado."

# NEXTCLOUD_TRUSTED_DOMAINS solo se aplica en la instalacion inicial del
# contenedor (ver docker-entrypoint.sh de la imagen "nextcloud"); si el
# volumen de datos ya existia, un NEXO_HOST nuevo nunca llega a
# trusted_domains y Nextcloud puede rechazar el acceso por ese nombre.
echo "Agregando NEXO_HOST a trusted_domains de Nextcloud (si falta)..."
occ() { docker exec --user www-data nexo-nextcloud php occ "$@"; }
ALREADY=$(occ config:system:get trusted_domains --output=json 2>/dev/null | grep -c "\"${NEXO_HOST}\"" || true)
if [ "$ALREADY" = "0" ]; then
  NEXT_IDX=$(occ config:system:get trusted_domains --output=json 2>/dev/null | docker exec -i nexo-nextcloud php -r '
    $d = json_decode(stream_get_contents(STDIN), true);
    echo is_array($d) ? count($d) : 0;
  ')
  occ config:system:set trusted_domains "$NEXT_IDX" --value="$NEXO_HOST" >/dev/null
  echo "'${NEXO_HOST}' agregado a trusted_domains."
else
  echo "'${NEXO_HOST}' ya estaba en trusted_domains."
fi

echo "Listo. Element/Nextcloud (OVERWRITEHOST)/Asterisk/Jitsi ya deberian"
echo "reflejar NEXO_HOST tras el 'docker compose up -d' que recreo sus"
echo "contenedores; si alguno quedo con el valor anterior, confirma que su"
echo "contenedor se recreo (docker compose ps)."

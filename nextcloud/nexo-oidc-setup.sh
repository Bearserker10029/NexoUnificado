#!/bin/sh
# Configura el proveedor OIDC "keycloak" en Nextcloud (app user_oidc) para que
# la pantalla de login visible sea la de Keycloak. Se ejecuta una sola vez.
# Si tu version de la app user_oidc cambio los parametros del comando
# "occ user_oidc:provider", revisa "occ user_oidc:provider --help" dentro del
# contenedor nexo-nextcloud y ajusta este script o ejecuta el comando a mano.
set -eu
: "${KC_NEXTCLOUD_CLIENT_SECRET:?}" "${NEXO_URL:?}"
cd /var/www/html

occ() {
  su -s /bin/sh www-data -c "php occ $*"
}

echo "Esperando a que Nextcloud termine la instalacion inicial..."
i=0
until occ status --output=json 2>/dev/null | grep -q '"installed":true'; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "Nextcloud no reporto 'installed:true' a tiempo. Revisa 'docker logs nexo-nextcloud'." >&2
    exit 1
  fi
  sleep 5
done

occ app:install user_oidc 2>/dev/null || occ app:enable user_oidc
occ app:enable external 2>/dev/null || true

EXISTING_ID=$(occ user_oidc:provider:list --output=json 2>/dev/null | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*' || true)
if [ -n "${EXISTING_ID:-}" ]; then
  occ "user_oidc:provider:delete ${EXISTING_ID}" || true
fi

occ "user_oidc:provider keycloak \
  --clientid='nextcloud' \
  --clientsecret='${KC_NEXTCLOUD_CLIENT_SECRET}' \
  --discoveryuri='http://keycloak:8080/keycloak/realms/nexo/.well-known/openid-configuration' \
  --unique-uid=0 \
  --mapping-display-name='name' \
  --mapping-email='email'"

echo "Proveedor OIDC 'keycloak' configurado en Nextcloud."
echo "Si no aparece el boton de 'Nexo Unificado (Keycloak)' en el login,"
echo "revisa en Nextcloud: Ajustes > Administracion > Autenticacion con OpenID Connect."

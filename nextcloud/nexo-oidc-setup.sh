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

# Pone un valor booleano de config.php y verifica que haya quedado escrito.
# "status.php" puede reportar "installed:true" mientras el entrypoint propio
# de la imagen "nextcloud" (el que crea config.php la primera vez) todavia
# esta terminando sus propios ajustes en segundo plano: si este script
# escribe config.php en ese momento, su cambio puede perderse cuando el
# entrypoint reescribe el archivo completo justo despues. Reintentar hasta
# que la lectura confirme el valor evita quedar con una config a medias.
occ_set_bool_verified() {
  _key="$1"; _value="$2"
  _j=0
  while [ "$_j" -lt 12 ]; do
    occ "config:system:set $_key --value=$_value --type=boolean" >/dev/null
    if occ "config:system:get $_key" 2>/dev/null | grep -qx "$_value"; then
      return 0
    fi
    _j=$((_j + 1))
    sleep 2
  done
  echo "No se pudo confirmar que '$_key' quedara en '$_value' en config.php." >&2
  return 1
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
# Margen extra: "installed:true" puede llegar mientras el entrypoint de la
# imagen "nextcloud" todavia esta reescribiendo config.php por su cuenta.
sleep 10

occ app:install user_oidc 2>/dev/null || occ app:enable user_oidc
occ app:enable external 2>/dev/null || true

# Sin esto, el cliente HTTP de Nextcloud rechaza la llamada al discovery
# endpoint de Keycloak por ser un host "local" de la red interna srv.
occ_set_bool_verified allow_local_remote_servers true

# "occ user_oidc:provider keycloak" es un upsert (crea o actualiza el
# proveedor "keycloak" si ya existe), asi que conserva su ID numerico entre
# reinicios: la raiz en nginx/conf.d/default.conf redirige directo a
# /docs/apps/user_oidc/login/<ID> y ese ID no puede cambiar en cada arranque.
occ "user_oidc:provider keycloak \
  --clientid='nextcloud' \
  --clientsecret='${KC_NEXTCLOUD_CLIENT_SECRET}' \
  --discoveryuri='http://keycloak:8080/realms/nexo/.well-known/openid-configuration' \
  --unique-uid=0 \
  --mapping-display-name='name' \
  --mapping-email='email'"

PROVIDER_ID=$(occ user_oidc:provider --output=json 2>/dev/null | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
echo "Proveedor 'keycloak' con id interno ${PROVIDER_ID:-?}."
echo "Si cambio respecto al desplegado antes, actualiza la ruta"
echo "/docs/apps/user_oidc/login/\${PROVIDER_ID} en nginx/conf.d/default.conf"
echo "y recarga nginx (\"docker exec nexo-proxy nginx -s reload\")."

# hide_login_form queda en false: para las personas usuarias no importa (la
# raiz y /docs/login saltan directo a Keycloak por Nginx, nunca ven esta
# pantalla), pero nexo_admin la necesita en false para poder entrar con
# usuario/clave local por la puerta trasera /docs/admin-login (ver
# nginx/conf.d/default.conf). En true, el formulario queda oculto ahi
# tambien y no hay forma de entrar como nexo_admin desde el navegador.
occ_set_bool_verified hide_login_form false

echo "Proveedor OIDC 'keycloak' configurado en Nextcloud."
echo "Entrada normal: raiz o /docs/login, directo a Keycloak (sin boton de por medio)."
echo "Entrada de nexo_admin (cuenta local, fuera de Keycloak): /docs/admin-login."

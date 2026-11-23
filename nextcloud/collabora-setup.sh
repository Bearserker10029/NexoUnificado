#!/bin/sh
# Integra Collabora Online (CODE) con Nextcloud Office (app richdocuments).
# Tarea unica: se ejecuta despues de nextcloud-menu-init para no pisar config.php.
set -eu
: "${NEXO_URL:?}"
cd /var/www/html

occ() {
  su -s /bin/sh www-data -c "php occ $*"
}

echo "Esperando a Nextcloud..."
i=0
until occ status --output=json 2>/dev/null | grep -q '"installed":true'; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo "Nextcloud no estuvo listo a tiempo." >&2; exit 1; }
  sleep 5
done

occ app:install richdocuments 2>/dev/null || occ app:enable richdocuments

# El navegador llega a Collabora por Nginx (mismo origen HTTPS); Nextcloud lo
# consulta por la red interna; Collabora vuelve a llamar a Nextcloud (WOPI)
# por el listener interno de Nginx en el puerto 8082, sin pasar por TLS.
occ "config:app:set richdocuments wopi_url --value='http://collabora:9980'"
occ "config:app:set richdocuments public_wopi_url --value='${NEXO_URL}'"
occ "config:app:set richdocuments disable_certificate_verification --value='yes'"
occ "config:system:set allow_local_remote_servers --value=true --type=boolean"
occ "richdocuments:activate-config" || echo "activate-config devolvio error: revisa 'docker logs nexo-collabora'." >&2

# activate-config restablece la URL de callback a "autodetectar"; se fija
# despues para que Collabora llame a Nextcloud por el listener interno.
occ "config:app:set richdocuments wopi_callback_url --value='http://proxy:8082'"
# activate-config tambien reescribe public_wopi_url con la URL que anuncia
# Collabora hacia dentro (https://collabora:9980), que el navegador no
# resuelve y el CSP bloquea; se vuelve a fijar a la URL publica.
occ "config:app:set richdocuments public_wopi_url --value='${NEXO_URL}'"
occ "config:app:get richdocuments public_wopi_url"
occ "config:app:get richdocuments wopi_callback_url"

echo "Collabora configurado: wopi_url=http://collabora:9980 publico=${NEXO_URL} callback=http://proxy:8082"

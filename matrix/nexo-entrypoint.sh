#!/bin/sh
# Renderiza config.json desde la plantilla con la variable unica NEXO_HOST
# (no hay IP quemada en el repo) y arranca el comando original de la imagen.
set -eu
: "${NEXO_HOST:?Define NEXO_HOST en el archivo .env}"
sed "s#\${NEXO_HOST}#${NEXO_HOST}#g" /nexo/element-config.json.template > /app/config.json
# Delega en el entrypoint original de la imagen: renderiza el nginx.conf de
# /etc/nginx/templates (ELEMENT_WEB_PORT, etc.) antes de arrancar nginx; si
# se omite este paso, nginx queda escuchando en el puerto de fabrica (8080)
# en vez de 80.
exec /docker-entrypoint.sh nginx -g "daemon off;"

#!/bin/sh
set -eu
: "${NEXO_URL:?}"
export NEXO_URL
envsubst '${NEXO_URL}' < /template/config.json > /app/config.json
exec /docker-entrypoint.sh nginx -g "daemon off;"

#!/bin/sh
# Version "contenedor" de nextcloud/poblar-menu.sh: mismas 4 entradas y misma
# logica, pero pensada para correr DENTRO de un contenedor con el volumen de
# datos de Nextcloud montado (occ local, sin "docker exec" desde el host),
# para que "docker compose up -d" deje el menu poblado solo, sin pasos
# manuales. Si cambias las entradas, edita las DOS copias (este archivo y
# nextcloud/poblar-menu.sh, que sigue sirviendo para reasignar grupos a mano
# sin tener que reiniciar nada).
set -eu
cd /var/www/html

occ() {
  # "-- occ $@" preserva cada argumento como unidad (el JSON de --value
  # trae saltos de linea: con "php occ $*" se re-interpretan como comandos
  # nuevos dentro del "-c" de su, rompiendo el valor a la mitad). El primer
  # valor tras "--" se vuelve $0 dentro del "-c" (no $1), por eso el "occ"
  # de relleno: sin el, el primer argumento real se pierde.
  su -s /bin/sh www-data -c 'exec php occ "$@"' -- occ "$@"
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

echo "Habilitando la app External Sites..."
occ app:install external >/dev/null 2>&1 || occ app:enable external

# Nextcloud crea el iframe exterior; sin este allow, Chromium bloquea el
# microfono aunque /voip/embed.html lo habilite en su propio iframe interior.
EXTERNAL_FRAME="/var/www/html/custom_apps/external/templates/frame.php"
if [ -f "$EXTERNAL_FRAME" ] && ! grep -q 'allow="microphone; camera"' "$EXTERNAL_FRAME"; then
  sed -i 's/allowfullscreen><\/iframe>/allow="microphone; camera" allowfullscreen><\/iframe>/' "$EXTERNAL_FRAME"
  echo "Permisos de microfono/camara habilitados en el iframe de External Sites."
fi

SITES_JSON=$(cat <<'JSON'
{
  "1": {"id": 1, "name": "Telefonía", "url": "/voip/embed.html", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "2": {"id": 2, "name": "Videoconferencia", "url": "/jitsi/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "3": {"id": 3, "name": "Chat", "url": "/element/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "4": {"id": 4, "name": "Monitoreo", "url": "/grafana/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": ["admin"], "redirect": false}
}
JSON
)

echo "Escribiendo las 4 entradas en la appconfig de External Sites..."
occ config:app:set external sites --value="$SITES_JSON"
occ config:app:set external max_site --value=4

echo "Menu unificado poblado (Telefonía, Videoconferencia, Chat, Monitoreo)."
echo "Monitoreo queda restringido al grupo 'admin'. Para reasignar grupos sin"
echo "reiniciar nada, usa ./nextcloud/poblar-menu.sh desde el host."

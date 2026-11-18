#!/bin/sh
# Pobla el menu unificado de Nextcloud (app External Sites) con las cuatro
# rutas reales detras del proxy Nginx (Documentos no va aqui: usa la app
# nativa de Archivos de Nextcloud). Se ejecuta desde el host, una vez
# desplegado el contenedor nexo-nextcloud (se puede volver a correr para
# agregar/actualizar entradas; es idempotente, siempre reescribe la lista
# completa de "sites").
#
# Uso:
#   ./nextcloud/poblar-menu.sh
#   docker exec nexo-nextcloud ... (lo hace el propio script via docker exec)
#
# Estructura verificada contra la version instalada (external 10.0.0, ver
# /var/www/html/custom_apps/external/lib/SitesManager.php dentro del
# contenedor): la app guarda sus entradas en la appconfig "external"/"sites"
# como un objeto JSON indexado por id, con los campos id, name, url, lang,
# type, device, icon, groups y redirect. No existe un comando "occ" propio
# para altas/bajas, asi que se escribe ese JSON directamente con
# "occ config:app:set external sites".
#
# Las URLs son relativas al mismo origen (sin esquema/host) para que el
# navegador las resuelva contra "https://<NEXO_HOST>:8443" sin importar el
# valor de NEXO_HOST, y para que la sesion de Nextcloud/Keycloak no se pierda
# al saltar de servicio (ver README > "Cambio de IP o de nombre de host").
set -eu

CONTENEDOR="${1:-nexo-nextcloud}"

occ() {
  docker exec --user www-data "$CONTENEDOR" php occ "$@"
}

echo "Habilitando la app External Sites en $CONTENEDOR..."
occ app:install external >/dev/null 2>&1 || occ app:enable external

# JSON que espera SitesManager::getSites(): objeto indexado por id (como
# string), con name/url relativa/tipo "link"/icon/device "" (todos)/groups
# vacio (visible para todos) y redirect=false (abre en iframe dentro de
# Nextcloud). No hay entrada de "Documentos": la app nativa de Archivos de
# Nextcloud ya cumple esa funcion (icono de apps, arriba a la izquierda), y
# agregarla aqui solo duplicaba Nextcloud embebido dentro de si mismo.
SITES_JSON=$(cat <<'JSON'
{
  "1": {"id": 1, "name": "Telefonía", "url": "/voip/embed.html", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "2": {"id": 2, "name": "Videoconferencia", "url": "/jitsi/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "3": {"id": 3, "name": "Chat", "url": "/element/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": [], "redirect": false},
  "4": {"id": 4, "name": "Monitoreo", "url": "/grafana/", "lang": "", "type": "link", "device": "", "icon": "external.svg", "groups": ["admin"], "redirect": false}
}
JSON
)

# --- "Monitoreo" queda restringido al grupo integrado "admin" (solo
# nexo_admin y quien mas se agregue con "occ group:adduser admin <usuario>"
# lo ve en el menu); el resto de entradas no tiene "groups" y es visible
# para todas las personas usuarias.
#
# Para restringir cualquier otra entrada a un grupo propio (asignar
# servicios por cliente), agrega el/los nombres de grupo en "groups", por
# ejemplo para que solo lo vea el grupo "clienteA" creado con
# "occ group:add clienteA":
#   "groups": ["clienteA"]
# Si "groups" queda vacio, la entrada es visible para todas las personas
# usuarias.

echo "Escribiendo las 4 entradas en la appconfig de External Sites..."
occ config:app:set external sites --value="$SITES_JSON"
occ config:app:set external max_site --value=4

echo "Verificando que lo guardado sea JSON valido con la forma esperada..."
occ config:app:get external sites | docker exec -i "$CONTENEDOR" php -r '
  $sites = json_decode(stream_get_contents(STDIN), true);
  if (!is_array($sites) || count($sites) < 1) { fwrite(STDERR, "JSON invalido o vacio\n"); exit(1); }
  foreach ($sites as $id => $s) {
    foreach (["id","name","url","lang","type","device","icon","groups","redirect"] as $campo) {
      if (!array_key_exists($campo, $s)) { fwrite(STDERR, "Falta el campo $campo en el sitio $id\n"); exit(1); }
    }
  }
  echo "OK: " . count($sites) . " entradas con la estructura esperada.\n";
' 2>&1 || {
  echo "ADVERTENCIA: no se pudo verificar automaticamente. Revisa a mano con:" >&2
  echo "  docker exec --user www-data $CONTENEDOR php occ config:app:get external sites" >&2
}

echo "Listo. Entra a Nextcloud y revisa el menu (icono de apps, arriba a la izquierda)."
echo "Si una version mas nueva de la app 'external' cambio esta estructura, ajusta"
echo "este script: dentro del contenedor, revisa"
echo "  docker exec $CONTENEDOR cat /var/www/html/custom_apps/external/lib/SitesManager.php"

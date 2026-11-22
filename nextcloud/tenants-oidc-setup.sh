#!/bin/sh
set -eu
cd /var/www/html
: "${KC_NEXTCLOUD_CLIENT_SECRET:?}" "${NEXO_URL:?}"

occ() {
  su -s /bin/sh www-data -c 'exec php occ "$@"' -- occ "$@"
}

i=0
until occ status --output=json 2>/dev/null | grep -q '"installed":true'; do
  i=$((i + 1)); [ "$i" -le 60 ] || exit 1
  sleep 5
done

python3 - <<'PY' > /tmp/nexo-tenants.txt
import json
with open('/tenants/registry.json', encoding='utf-8') as f:
    for tenant in json.load(f)['tenants']:
        print(tenant['name'])
PY

while IFS= read -r tenant; do
  [ -n "$tenant" ] || continue
  echo "Configurando proveedor Nextcloud keycloak-${tenant}..."
  occ user_oidc:provider "keycloak-${tenant}" \
    --clientid='nextcloud' \
    --clientsecret="${KC_NEXTCLOUD_CLIENT_SECRET}" \
    --discoveryuri="http://keycloak:8080/realms/nexo-${tenant}/.well-known/openid-configuration" \
    --unique-uid=0 \
    --mapping-display-name='name' \
    --mapping-email='email' \
    --mapping-groups='groups'
done < /tmp/nexo-tenants.txt

occ user_oidc:provider --output=json

# Cada empresa recibe entradas propias, visibles solo para sus grupos sincronizados.
python3 - <<'PY' > /tmp/nexo-tenant-sites.json
import json
with open('/tenants/registry.json', encoding='utf-8') as f:
    tenants = json.load(f)['tenants']
sites = {}
index = 1
for tenant in tenants:
    name = tenant['name']
    for service, label, path in [
        ('telefonia', 'Telefonía', f'/{name}/voip/embed.html'),
        ('videoconferencia', 'Videoconferencia', f'/{name}/jitsi/'),
        ('chat', 'Chat', f'/{name}/element/'),
    ]:
        if service not in tenant.get('services', []):
            continue
        sites[str(index)] = {"id": index, "name": f"{label} · {name.upper()}", "url": path,
            "lang": "", "type": "link", "device": "", "icon": "external.svg",
            "groups": [f"{name}-servicio-{service}"], "redirect": False}
        index += 1
print(json.dumps(sites, ensure_ascii=False))
PY
occ config:app:set external sites --value="$(cat /tmp/nexo-tenant-sites.json)"
occ config:app:set external max_site --value="$(python3 -c 'import json; print(len(json.load(open("/tmp/nexo-tenant-sites.json"))))')"

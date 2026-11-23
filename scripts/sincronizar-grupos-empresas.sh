#!/bin/sh
# Ejecutar con: docker exec -i nexo-keycloak sh -s < scripts/sincronizar-grupos-empresas.sh
set -eu
config=$(mktemp)
trap 'rm -f "$config"' EXIT
kcadm() { /opt/keycloak/bin/kcadm.sh "$@" --config "$config"; }
kcadm config credentials --server http://localhost:8080 --realm master \
  --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"

for template in /opt/keycloak/nexo/tenants/*/keycloak/realm.json.template; do
  [ -f "$template" ] || continue
  tenant=$(basename "$(dirname "$(dirname "$template")")")
  realm="nexo-$tenant"
  groups=$(sed -n "s/^[[:space:]]*\"name\": \"\($tenant-\(administradores\|servicio-[a-z0-9-]*\)\)\".*$/\1/p" "$template")
  for group in $groups; do
    existing=$(kcadm get groups -r "$realm" -q "search=$group" -q exact=true --fields name --format csv --noquotes)
    if [ "$existing" != "$group" ]; then
      kcadm create groups -r "$realm" -s "name=$group"
    fi
  done
  kcadm add-roles -r "$realm" --gname "$tenant-administradores" \
    --cclientid realm-management --rolename manage-users
  portal_id=$(kcadm get clients -r "$realm" -q clientId=nexo-portal --fields id --format csv --noquotes)
  admin_scope_id=$(kcadm get client-scopes -r "$realm" --fields id,name --format csv --noquotes |
    sed -n -e 's/^\([^,]*\),kc-admin-api$/\1/p' -e 's/^kc-admin-api,\([^,]*\)$/\1/p')
  test -n "$portal_id" && test -n "$admin_scope_id"
  kcadm update "clients/$portal_id/optional-client-scopes/$admin_scope_id" -r "$realm" -n
done

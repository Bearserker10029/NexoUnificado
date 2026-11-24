#!/bin/sh
# Alta del administrador de una empresa (lo ejecuta el administrador del proveedor).
#
#   docker exec -i -e TENANT=acme -e ADMIN_USER=admin.acme \
#     -e ADMIN_EMAIL=admin@acme.test -e ADMIN_PASSWORD='Temporal#2026' \
#     nexo-keycloak sh -s < scripts/crear-admin-empresa.sh
#
# Crea la cuenta en el realm nexo-<TENANT> con clave temporal y la agrega a
# <TENANT>-administradores y a los servicios contratados. Es idempotente.
set -eu
: "${TENANT:?}" "${ADMIN_USER:?}" "${ADMIN_EMAIL:?}" "${ADMIN_PASSWORD:?}"
realm="nexo-$TENANT"
config=$(mktemp)
trap 'rm -f "$config"' EXIT
kcadm() { /opt/keycloak/bin/kcadm.sh "$@" --config "$config"; }
kcadm config credentials --server http://localhost:8080 --realm master \
  --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"

uid=$(kcadm get users -r "$realm" -q username="$ADMIN_USER" -q exact=true --fields id --format csv --noquotes)
if [ -z "$uid" ]; then
  kcadm create users -r "$realm" -s username="$ADMIN_USER" -s enabled=true -s emailVerified=true \
    -s email="$ADMIN_EMAIL" -s firstName="Administrador" -s lastName="$TENANT"
  uid=$(kcadm get users -r "$realm" -q username="$ADMIN_USER" -q exact=true --fields id --format csv --noquotes)
  kcadm set-password -r "$realm" --username "$ADMIN_USER" --new-password "$ADMIN_PASSWORD" --temporary
fi
for group in "$TENANT-administradores" "$TENANT-servicio-chat" "$TENANT-servicio-telefonia" "$TENANT-servicio-videoconferencia"; do
  gid=$(kcadm get groups -r "$realm" -q search="$group" -q exact=true --fields id,name --format csv --noquotes |
    sed -n "s/^\([^,]*\),$group\$/\1/p;s/^$group,\(.*\)\$/\1/p" | head -1)
  [ -n "$gid" ] && kcadm update "users/$uid/groups/$gid" -r "$realm" -s realm="$realm" -s userId="$uid" -s groupId="$gid" -n || true
done
echo "Administrador $ADMIN_USER listo en $realm."

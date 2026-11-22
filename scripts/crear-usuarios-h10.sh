#!/bin/sh
# Usuarios exclusivos de laboratorio H10. Requiere claves en variables de entorno.
set -eu
: "${KC_ADMIN_USER:?}" "${KC_ADMIN_PASSWORD:?}"
: "${ACME1_PASSWORD:?}" "${ACME2_PASSWORD:?}" "${BETA1_PASSWORD:?}"
kcadm() { docker exec nexo-keycloak /opt/keycloak/bin/kcadm.sh "$@"; }
kcadm config credentials --server http://localhost:8080 --realm master \
  --user "$KC_ADMIN_USER" --password "$KC_ADMIN_PASSWORD"

create_user() {
  realm=$1; username=$2; password=$3
  kcadm create users -r "$realm" -s username="$username" -s enabled=true \
    -s emailVerified=true -s firstName="$username" -s lastName=H10 || true
  uid=$(kcadm get users -r "$realm" -q username="$username" --fields id --format csv --noquotes)
  kcadm set-password -r "$realm" --userid "$uid" --new-password "$password"
  for group in chat telefonia videoconferencia; do
    tenant=${realm#nexo-}
    gid=$(kcadm get groups -r "$realm" -q search="${tenant}-servicio-${group}" --fields id --format csv --noquotes | head -1)
    kcadm update "users/${uid}/groups/${gid}" -r "$realm" -n
  done
}
create_user nexo-acme acme1 "$ACME1_PASSWORD"
create_user nexo-acme acme2 "$ACME2_PASSWORD"
create_user nexo-beta beta1 "$BETA1_PASSWORD"
echo "Usuarios H10 creados. ACME1 y BETA1 usan las extensiones TLS 1001/2001 de prueba."

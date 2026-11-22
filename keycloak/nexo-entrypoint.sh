#!/bin/sh
set -eu
: "${NEXO_URL:?}"
: "${KC_NEXTCLOUD_CLIENT_SECRET:?}" "${KC_SYNAPSE_CLIENT_SECRET:?}" "${KC_VOIP_CLIENT_SECRET:?}"
mkdir -p /opt/keycloak/data/import
sed \
  -e "s#\${NEXO_URL}#${NEXO_URL}#g" \
  -e "s#\${KC_NEXTCLOUD_CLIENT_SECRET}#${KC_NEXTCLOUD_CLIENT_SECRET}#g" \
  -e "s#\${KC_SYNAPSE_CLIENT_SECRET}#${KC_SYNAPSE_CLIENT_SECRET}#g" \
  -e "s#\${KC_VOIP_CLIENT_SECRET}#${KC_VOIP_CLIENT_SECRET}#g" \
  /opt/keycloak/nexo/realm-nexo.json.template > /opt/keycloak/data/import/realm-nexo.json
for template in /opt/keycloak/nexo/tenants/*/keycloak/realm.json.template; do
  [ -f "$template" ] || continue
  tenant=$(printf '%s' "$template" | cut -d/ -f6)
  sed \
    -e "s#\${NEXO_URL}#${NEXO_URL}#g" \
    -e "s#\${KC_NEXTCLOUD_CLIENT_SECRET}#${KC_NEXTCLOUD_CLIENT_SECRET}#g" \
    -e "s#\${KC_SYNAPSE_CLIENT_SECRET}#${KC_SYNAPSE_CLIENT_SECRET}#g" \
    -e "s#\${KC_VOIP_CLIENT_SECRET}#${KC_VOIP_CLIENT_SECRET}#g" \
    "$template" > "/opt/keycloak/data/import/realm-${tenant}.json"
done
exec /opt/keycloak/bin/kc.sh "$@"

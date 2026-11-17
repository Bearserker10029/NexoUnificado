#!/bin/sh
set -eu
: "${NEXO_URL:?}" "${HOST_IP:?}"
: "${KC_NEXTCLOUD_CLIENT_SECRET:?}" "${KC_SYNAPSE_CLIENT_SECRET:?}"
: "${KC_TEST_USER1_USERNAME:?}" "${KC_TEST_USER1_PASSWORD:?}"
: "${KC_TEST_USER2_USERNAME:?}" "${KC_TEST_USER2_PASSWORD:?}"
mkdir -p /opt/keycloak/data/import
sed \
  -e "s#\${NEXO_URL}#${NEXO_URL}#g" \
  -e "s#\${HOST_IP}#${HOST_IP}#g" \
  -e "s#\${KC_NEXTCLOUD_CLIENT_SECRET}#${KC_NEXTCLOUD_CLIENT_SECRET}#g" \
  -e "s#\${KC_SYNAPSE_CLIENT_SECRET}#${KC_SYNAPSE_CLIENT_SECRET}#g" \
  -e "s#\${KC_TEST_USER1_USERNAME}#${KC_TEST_USER1_USERNAME}#g" \
  -e "s#\${KC_TEST_USER1_PASSWORD}#${KC_TEST_USER1_PASSWORD}#g" \
  -e "s#\${KC_TEST_USER2_USERNAME}#${KC_TEST_USER2_USERNAME}#g" \
  -e "s#\${KC_TEST_USER2_PASSWORD}#${KC_TEST_USER2_PASSWORD}#g" \
  /opt/keycloak/nexo/realm-nexo.json.template > /opt/keycloak/data/import/realm-nexo.json
exec /opt/keycloak/bin/kc.sh "$@"

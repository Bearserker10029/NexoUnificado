# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0

configure_assistant_client() {
  realm="$1"
  client_id=$(kcadm get clients -r "$realm" -q clientId=nexo-assistant --fields id --format csv --noquotes)
  set -- -r "$realm" -s clientId=nexo-assistant -s name="Asistente IA Nexo" \
    -s enabled=true -s protocol=openid-connect -s publicClient=true \
    -s standardFlowEnabled=true -s implicitFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s "redirectUris=[\"${NEXO_URL}/airi/callback\"]" \
    -s 'attributes={"pkce.code.challenge.method":"S256"}'
  if [ -n "$client_id" ]; then
    kcadm update "clients/$client_id" "$@"
  else
    kcadm create clients "$@" >/dev/null
  fi
}

assistant_realms=$(kcadm get realms --fields realm --format csv --noquotes)
for assistant_realm in $assistant_realms; do
  case "$assistant_realm" in
    nexo|nexo-*) configure_assistant_client "$assistant_realm" ;;
  esac
done

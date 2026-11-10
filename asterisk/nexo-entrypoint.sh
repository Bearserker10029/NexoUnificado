#!/bin/sh
set -eu
: "${SIP_PASSWORD_100:?}" "${SIP_PASSWORD_101:?}"
: "${WEBRTC_PASSWORD_100:?}" "${WEBRTC_PASSWORD_101:?}"
# La llave TLS del volumen /certs solo la lee root; se copia con dueño asterisk y permisos 0600.
mkdir -p /etc/asterisk/keys
cp /certs/server.crt /etc/asterisk/keys/server.crt
cp /certs/server.key /etc/asterisk/keys/server.key
chown -R asterisk:asterisk /etc/asterisk/keys
chmod 0700 /etc/asterisk/keys
chmod 0600 /etc/asterisk/keys/server.key
chmod 0644 /etc/asterisk/keys/server.crt
envsubst < /etc/asterisk/pjsip.conf.template > /etc/asterisk/pjsip.conf
chown asterisk:asterisk /etc/asterisk/pjsip.conf
chmod 0640 /etc/asterisk/pjsip.conf
exec /usr/local/bin/entrypoint.sh "$@"

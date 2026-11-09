#!/bin/sh
set -eu
: "${SIP_PASSWORD_100:?}" "${SIP_PASSWORD_101:?}"
: "${WEBRTC_PASSWORD_100:?}" "${WEBRTC_PASSWORD_101:?}"
envsubst < /etc/asterisk/pjsip.conf.template > /etc/asterisk/pjsip.conf
chown asterisk:asterisk /etc/asterisk/pjsip.conf
chmod 0640 /etc/asterisk/pjsip.conf
exec /usr/local/bin/entrypoint.sh "$@"

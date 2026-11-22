#!/bin/sh
set -eu
: "${VOIP_AMI_USER:?}" "${VOIP_AMI_SECRET:?}"
# La llave TLS del volumen /certs solo la lee root; se copia con dueño asterisk.
mkdir -p /etc/asterisk/keys /etc/asterisk/dynamic
cp /certs/server.crt /etc/asterisk/keys/server.crt
cp /certs/server.key /etc/asterisk/keys/server.key
chown -R asterisk:asterisk /etc/asterisk/keys
chmod 0700 /etc/asterisk/keys
chmod 0600 /etc/asterisk/keys/server.key
chmod 0644 /etc/asterisk/keys/server.crt
touch /etc/asterisk/dynamic/pjsip-users.conf
# El gateway corre como UID 10001 y publica archivos mediante rename atomico.
chown 10001:10001 /etc/asterisk/dynamic /etc/asterisk/dynamic/pjsip-users.conf
chmod 0755 /etc/asterisk/dynamic
chmod 0644 /etc/asterisk/dynamic/pjsip-users.conf
mkdir -p /var/log/asterisk/cdr-csv /var/log/asterisk/cdr-custom
chown -R asterisk:asterisk /var/log/asterisk
envsubst < /etc/asterisk/pjsip.conf.template > /etc/asterisk/pjsip.conf
envsubst < /etc/asterisk/manager.conf.template > /etc/asterisk/manager.conf
: > /etc/asterisk/dynamic/tenants-pjsip.conf
for template in /etc/asterisk/tenants/*/asterisk/pjsip.conf.template; do
  [ -f "$template" ] || continue
  envsubst < "$template" >> /etc/asterisk/dynamic/tenants-pjsip.conf
done
: > /etc/asterisk/dynamic/tenants-extensions.conf
for dialplan in /etc/asterisk/tenants/*/asterisk/extensions.conf; do
  [ -f "$dialplan" ] || continue
  cat "$dialplan" >> /etc/asterisk/dynamic/tenants-extensions.conf
done
chown asterisk:asterisk /etc/asterisk/dynamic/tenants-*.conf
chmod 0644 /etc/asterisk/dynamic/tenants-*.conf
chown asterisk:asterisk /etc/asterisk/pjsip.conf /etc/asterisk/manager.conf
chmod 0640 /etc/asterisk/pjsip.conf /etc/asterisk/manager.conf
exec /usr/local/bin/entrypoint.sh "$@"

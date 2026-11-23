#!/bin/sh
# H7: exige TOTP en el realm "nexo" y crea usuarios de prueba (H5/H7).
# Uso (desde la raiz del repo, con el stack arriba):
#   TEST_USER_PASSWORD='<clave-de-prueba>' sh scripts/h7-configurar-totp.sh
# Credenciales de admin: KC_ADMIN_USER / KC_ADMIN_PASSWORD (de .env).
set -eu
: "${KC_ADMIN_USER:?}" "${KC_ADMIN_PASSWORD:?}" "${TEST_USER_PASSWORD:?}"
REALM=${REALM:-nexo}
KC=${KC_CONTAINER:-nexo-keycloak}
kcadm() { docker exec "$KC" /opt/keycloak/bin/kcadm.sh "$@"; }

kcadm config credentials --server http://localhost:8080 --realm master \
  --user "$KC_ADMIN_USER" --password "$KC_ADMIN_PASSWORD" >/dev/null

# Politica OTP: TOTP, 6 digitos, 30 s (ya viene del realm; se fija por si acaso).
kcadm update "realms/$REALM" -s otpPolicyType=totp -s otpPolicyDigits=6 -s otpPolicyPeriod=30 -s otpPolicyAlgorithm=HmacSHA1

# Toda cuenta nueva debera enrolar TOTP en su primer login.
kcadm update authentication/required-actions/CONFIGURE_TOTP -r "$REALM" -s enabled=true -s defaultAction=true

for u in ana.prueba beto.prueba; do
  if [ -z "$(kcadm get users -r "$REALM" -q "username=$u" --fields id --format csv --noquotes)" ]; then
    kcadm create users -r "$REALM" -s "username=$u" -s enabled=true -s emailVerified=true \
      -s "email=$u@nexo.local" -s "firstName=${u%%.*}" -s lastName=Prueba \
      -s 'requiredActions=["CONFIGURE_TOTP"]'
  fi
  kcadm set-password -r "$REALM" --username "$u" --new-password "$TEST_USER_PASSWORD"
  echo "Usuario $u listo (TOTP obligatorio en el primer login)."
done

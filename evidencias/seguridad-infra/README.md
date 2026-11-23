# Evidencias de seguridad de infraestructura

## TLS

`testssl.txt`, `testssl.json` y `testssl.html` contienen el análisis de testssl.sh 3.2.5
contra `host.docker.internal:8443`. Se comprobaron TLS 1.2 y TLS 1.3; SSLv2, SSLv3,
TLS 1.0 y TLS 1.1 no se ofrecen. La calificación global experimental fue **T**, limitada
por el certificado autofirmado y por el nombre del objetivo Docker, que no coincide con
el certificado local. Este resultado corresponde al entorno de prueba, no a producción.

## fail2ban

- `fail2ban-jails.txt`: jails activos `asterisk` y `nexo-keycloak`.
- `fail2ban-*-antes.txt`: reglas y logs activos antes de la prueba.
- `intentos-keycloak.txt`: cinco rechazos HTTP 401 con una identidad falsa; el sexto
  intento no pudo conectar (`HTTP 000`) porque la IP del gateway ya estaba bloqueada.
- `fail2ban-keycloak-bloqueo.txt`: un bloqueo activo sobre la IP local `172.20.0.1`.
- `fail2ban-keycloak-despues.txt`: bloqueo retirado tras capturar la evidencia.

El jail SSH queda desactivado en Docker Desktop porque el host Windows no proporciona
`/var/log/auth.log`; su activación para Linux está documentada en `docs/seguridad-infra.md`.

**Nmap no fue ejecutado y permanece pendiente por indicación expresa del usuario.**

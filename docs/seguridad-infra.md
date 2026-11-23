# Seguridad de infraestructura

## Carga de la configuración

Ansible carga automáticamente, en este orden:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml \
  -f security/docker-compose.security.yml up -d
```

El tercer archivo solo añade el volumen de accesos del proxy y el servicio fail2ban.
No elimina ni sustituye rutas o servicios multiempresa. `nginx/conf.d/logging.conf`
guarda los accesos en `nexo-access.log`: el enlace a `/dev/stdout` de la imagen oficial
no permite que fail2ban lea los eventos desde otro contenedor.

## Límites de tasa en Nginx

- `nexo_web`: 20 solicitudes/s por IP para recursos web que ya lo referencian.
- `nexo_auth`: 10 solicitudes/min por IP, con ráfaga de 5, para el token OIDC de
  cualquier realm y los formularios administrativos de Nextcloud.
- El exceso responde HTTP 429; no se cambian los flujos OIDC ni las rutas por empresa.

## fail2ban

El contenedor comparte el namespace de red del proxy, por lo que `iptables-allports`
bloquea en ese punto las conexiones HTTPS/WSS de una IP sancionada. Configuración:

- `nexo-keycloak`: cinco respuestas 400/401 al endpoint de token en 10 minutos.
- `asterisk`: eventos `InvalidPassword`, `FailedACL`, `ChallengeResponseFailed` o
  `InvalidAccountID` del log `security`.
- `sshd`: filtro incluido, desactivado en Docker Desktop porque Windows no expone
  `/var/log/auth.log`. En un servidor Linux ejecuta Ansible con `-e security_sshd=true`;
  esto añade `security/docker-compose.sshd.yml`, monta el log real y activa el jail.

El tiempo de bloqueo es 15 minutos. Revisión y desbloqueo manual:

```bash
docker exec nexo-fail2ban fail2ban-client status
docker exec nexo-fail2ban fail2ban-client status nexo-keycloak
docker exec nexo-fail2ban fail2ban-client set nexo-keycloak unbanip IP_A_RETIRAR
```

## Evidencias reproducibles

Con la pila desplegada:

```bash
scripts/seguridad-fail2ban.sh
scripts/seguridad-tls.sh
```

El primer script guarda reglas activas, realiza intentos con una identidad falsa,
captura el bloqueo y lo retira. El segundo ejecuta testssl.sh en un contenedor contra
`host.docker.internal:8443`; el certificado autofirmado debe producir una advertencia
de cadena de confianza y no presentarse como apto para producción.

Las salidas se guardan en `evidencias/seguridad-infra`. No contienen secretos ni IPs
del laboratorio. El escaneo Nmap se ejecutará y documentará por separado cuando sea
solicitado.

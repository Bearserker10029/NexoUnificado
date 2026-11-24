# Nexo Unificado

Plataforma de comunicaciones con un único acceso HTTPS y autenticación centralizada
mediante Keycloak. Nextcloud sirve como menú unificado; Element/Matrix y la
telefonía WebRTC delegan su autenticación en Keycloak, y Jitsi se abre dentro de
la misma plataforma sin una cuenta adicional.

## Requisitos

- Docker Desktop con WSL2.
- Puertos libres: `8081` y `8443` TCP, `10000–10002` y `20000–20199` UDP.
- Los servicios web no publican puertos independientes: todo pasa por Nginx.

## Configuración y arranque

Para una instalación completa en equipos nuevos, incluidos el certificado, el
firewall y la configuración inicial de Element, sigue [Guia.md](Guia.md).

En PowerShell, dentro del repositorio:

```powershell
# Solo si todavia no existe .env:
Copy-Item .env.example .env

# Genera los secretos tecnicos ausentes y conserva los existentes:
.\scripts\new-secrets.ps1

docker compose up -d --build
docker compose ps --all
```

`.env` contiene únicamente las credenciales de los administradores técnicos y
secretos internos de servicios. No contiene cuentas ni claves de usuarios finales.

## Automatización y seguridad de infraestructura

El hito H12 aprovisiona y verifica toda la pila con Ansible, conserva las credenciales
existentes y puede ejecutarse dos veces para comprobar su idempotencia. La guía está en
[docs/h12-ansible.md](docs/h12-ansible.md).

La configuración de límites de tasa, fail2ban y la auditoría TLS local se documenta en
[docs/seguridad-infra.md](docs/seguridad-infra.md).

## Acceso

Sustituye `192.168.1.39` por el `NEXO_HOST` configurado. Todas las rutas usan el
mismo esquema, IP y puerto:

| Ruta | Servicio | Autenticación |
|---|---|---|
| `/` y `/docs/` | Nextcloud, menú unificado | Keycloak |
| `/element/` | Chat Element/Matrix | Keycloak |
| `/jitsi/` | Videoconferencia Jitsi | Sin cuenta adicional |
| `/voip/` | Telefonía WebRTC | Keycloak; extensión SIP automática |
| `/airi/` | [Asistente IA con chat y voz en español](evidencias/asistente-ia/README.md) | Keycloak; habilitación por empresa |
| `/grafana/` | Monitoreo | Administrador de Grafana |
| `/keycloak/admin/` | Consola de identidad | Administrador de Keycloak |

El certificado es autofirmado y exclusivo del laboratorio. Para confiarlo solo
en el usuario actual de Windows:

```powershell
Import-Certificate -FilePath ".\certs\server.crt" -CertStoreLocation Cert:\CurrentUser\Root
```

## Administración de usuarios

Los usuarios, incluidos `usuario1` y `usuario2`, se crean desde la consola de
**Keycloak**, no desde `.env`, Nextcloud ni Matrix:

1. Abre `/keycloak/admin/` e inicia sesión con `KC_ADMIN_USER` y
   `KC_ADMIN_PASSWORD`.
2. Selecciona el realm **nexo**.
3. Entra en **Users → Add user**, completa el nombre y habilita la cuenta.
4. En **Credentials**, asigna una clave temporal o definitiva.

Al primer acceso:

- Nextcloud crea su cuenta mediante `user_oidc`.
- Synapse crea su identidad Matrix mediante OIDC.
- `voip-gateway` le asigna una extensión del rango `2000–2999` y genera una clave
  SIP aleatoria interna. El softphone recibe esa configuración tras completar
  OIDC; la persona no introduce ninguna clave SIP.

Los usuarios que ya existían en el volumen de Keycloak se conservan. Eliminar
sus variables antiguas de `.env` no borra sus cuentas.

La cuenta local de Nextcloud definida por `NC_ADMIN_USER` queda como acceso de
administración en `/docs/admin-login`. No es una cuenta para usuarios finales.

## Flujo de sesión única

1. La persona entra a la raíz y Nextcloud la deriva a Keycloak.
2. Al abrir **Chat**, Element utiliza la API de Matrix en `/_matrix/` y el
   callback OIDC en `/_synapse/client/oidc/callback`, ambos bajo el mismo HTTPS.
3. **Videoconferencia** abre Jitsi en `/jitsi/`; no pide una cuenta propia.
4. **Telefonía** ejecuta Authorization Code Flow con PKCE contra Keycloak. Si ya
   hay sesión, Keycloak no vuelve a pedir credenciales. El gateway valida el
   token, provisiona PJSIP mediante AMI y devuelve la configuración al softphone.

Las claves SIP no se comparten entre usuarios, no están en `.env` y solo se
transmiten por HTTPS/WSS. El volumen `asterisk_dynamic` conserva la asignación
de extensiones para que cada identidad mantenga la suya.

## Cambio de IP o de nombre de host

Edita únicamente `NEXO_HOST` en `.env`, sin `https://` ni puerto, y ejecuta:

```powershell
docker compose up -d --build
```

Compose recrea los servicios afectados y realiza automáticamente estas tareas:

- Regenera el certificado si su SAN no incluye la nueva IP.
- Actualiza las URLs de los clientes `nextcloud`, `synapse` y `voip` en Keycloak.
- Actualiza `public_baseurl`, el callback OIDC y `trusted_domains`.
- Recrea Nginx para resolver las nuevas IP internas de los upstreams.

Diagnóstico:

```powershell
docker compose ps --all
docker compose logs host-update
docker compose logs voip-gateway
docker compose logs asterisk
```

## Telefonía WebRTC

El plan de marcado solo permite llamadas entre extensiones dinámicas `2000–2999`.
No existe troncal PSTN ni salida internacional. Asterisk publica únicamente el
rango UDP de medios; WSS termina en Nginx en el mismo puerto 8443.

Comprobaciones técnicas:

```powershell
docker exec nexo-asterisk asterisk -rx "core show version"
docker exec nexo-asterisk asterisk -rx "pjsip show endpoints"
docker exec nexo-asterisk asterisk -rx "pjsip show contacts"
docker exec nexo-asterisk asterisk -rx "dialplan show internal"
```

## Apagado

```powershell
docker compose down
```

Conserva usuarios, datos y extensiones. No uses `down -v` salvo que quieras borrar
todos los volúmenes persistentes.

## Licencias

Asterisk es GPLv2+; Keycloak usa Apache-2.0; Nextcloud Server y `user_oidc` usan
AGPLv3+; MariaDB usa GPLv2; ClamAV usa GPLv2. Tryit-JsSIP y JsSIP conservan su
licencia MIT en `voip/LICENSE` y `voip/ATTRIBUTION.txt`. Flask, Requests, PyJWT y
Gunicorn mantienen sus licencias permisivas en la imagen `voip-gateway`.

| Componente del asistente | Licencia |
| --- | --- |
| [AIRI Stage Web](https://github.com/moeru-ai/airi/blob/v0.15.4/LICENSE) | MIT |
| [Pocket TTS](https://github.com/kyutai-labs/pocket-tts/blob/v3.3.0/LICENSE) | MIT |
| [Pesos de Pocket TTS](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning) | CC BY 4.0 |
| Gemini API | Servicio propietario opcional |

## Modo multiempresa (H10)

`docker-compose.override.yml` incorpora automáticamente ACME (`1xxx`) y BETA
(`2xxx`) sin eliminar el modo tradicional. El archivo
`docker-compose.multiempresa.yml` conserva una copia equivalente por
compatibilidad; no es necesario indicarlo con `-f`. Element/Matrix gestiona las
llamadas 1:1 dentro de cada empresa; Asterisk solo interconecta empresas mediante
`9 + extensión`; Jitsi mantiene las videoconferencias grupales aisladas.

Para consultar la arquitectura, el alta de empresas con un solo comando, el
despliegue y el estado real de las evidencias, consulta
[el avance del hito H10](evidencias/h10/avance-hito.md).

```powershell
python scripts/nexo-tenant.py render
python -m unittest tests.test_multiempresa -v
docker compose config --quiet
docker compose up -d --build
```

`scripts/new-secrets.ps1` genera los secretos SIP de ACME y BETA que faltan en
`.env`. El CDR interempresas queda en Asterisk bajo
`/var/log/asterisk/cdr-custom/interempresas.csv`.

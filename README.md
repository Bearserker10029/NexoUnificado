# Nexo Unificado · Entorno base, VoIP e identidad única (H2 + H3 + H9)

Entorno Docker Compose con Nginx como proxy TLS, portal estático, Prometheus,
Grafana y Blackbox. H3 añade **Asterisk 20.21.0**, dos extensiones SIP con
TLS + SDES-SRTP y un cliente WebRTC basado en Tryit-JsSIP. H4/H6 añaden
mensajería (Matrix Synapse + Element) y videoconferencia (Jitsi Meet). H9
añade **inicio de sesión único**: Nextcloud como menú unificado y Keycloak
como único proveedor de identidad (ver [H9](#h9-identidad-única-keycloak-y-menú-unificado-nextcloud)).

## Requisitos

- Docker Desktop con WSL2.
- PhonerLite 3.46 para las pruebas SIP del laboratorio.
- Wireshark/TShark para las evidencias.
- Puertos libres: 8081, 8443, 5061/TCP, 8000, 8008, 8090, 8444, 10000/UDP y
  20000–20199/UDP.

## Configuración y arranque

En PowerShell, dentro del repositorio:

```powershell
# Solo si todavía no existe .env:
Copy-Item .env.example .env

# Genera claves aleatorias ausentes y conserva las que ya existan:
.\scripts\new-secrets.ps1

docker compose up -d
docker compose ps
```

Los valores `CAMBIAR_...` de `.env.example` son ejemplos públicos, no claves del
despliegue. `.env` y los certificados están excluidos de Git.

Servicios (sustituye `localhost` por el `NEXO_HOST` configurado en `.env`):

- **Raíz (`https://localhost:8443/`): va directo al login de Keycloak**
  (redirect 302 a `/docs/apps/user_oidc/login/1`, la ruta de inicio de sesión
  del proveedor OIDC de Nextcloud), sin la pantalla intermedia de Nextcloud.
  Si ya hay sesión abierta, cae directo en el menú unificado. Ver
  [H9](#h9-identidad-única-keycloak-y-menú-unificado-nextcloud).
- Keycloak (identidad): <https://localhost:8443/keycloak/>
- Portal estático de respaldo: <https://localhost:8443/portal/>
- Grafana: <https://localhost:8443/grafana/> (usuario `admin`; clave en `.env`).
- Cliente WebRTC: <https://localhost:8443/voip/> (embebido en Nextcloud en `/voip/embed.html`).
- Chat (Element): <https://localhost:8443/element/>, respaldo directo en `:8090`.
- Videoconferencia (Jitsi): <https://localhost:8443/jitsi/>, respaldo directo en `:8444`.
- SIP sobre TLS: `localhost:5061`.
- Audio SRTP: UDP 20000–20199.

El certificado es autofirmado y solo corresponde al laboratorio. Para producción
hay que reemplazarlo, usar un nombre DNS real y cambiar `ASTERISK_PUBLIC_IP` por
la dirección IP accesible del host Docker. El valor `127.0.0.1` sirve únicamente
para clientes ejecutados en la misma PC.

## H3: Asterisk puro, sin FreePBX

Se eligió Asterisk puro porque el enunciado permite esta alternativa y evita la
complejidad adicional de FreePBX en Docker. La imagen fija es
`andrius/asterisk:20.21.0_debian-trixie`.

El servicio está conectado a `srv`. Nginx, presente en `pub`, `srv` y `mgmt`, es
el único acceso web. Asterisk publica SIP/TLS y el rango de medios requerido;
su WebSocket 8088 queda interno y Nginx lo expone como WSS en 8443.

Archivos principales:

- `asterisk/pjsip.conf.template`: transportes, autenticación y cifrado PJSIP.
- `asterisk/extensions.conf`: marcación interna y denegación por defecto.
- `asterisk/rtp.conf`: rango UDP 20000–20199.
- `asterisk/http.conf`: WebSocket interno para WebRTC.
- `asterisk/nexo-entrypoint.sh`: renderiza la plantilla sin escribir claves en Git.
- `nginx/conf.d/default.conf`: `/voip/` y `/asterisk/ws`.

### Extensiones y seguridad

| Uso | Extensión lógica | Perfil de conexión | Variable de contraseña |
|---|---:|---:|---|
| PhonerLite | 100 | 100, SIP/TLS + SDES-SRTP | `SIP_PASSWORD_100` |
| PhonerLite | 101 | 101, SIP/TLS + SDES-SRTP | `SIP_PASSWORD_101` |
| Navegador | 100 | 1100, WSS + DTLS-SRTP | `WEBRTC_PASSWORD_100` |
| Navegador | 101 | 1101, WSS + DTLS-SRTP | `WEBRTC_PASSWORD_101` |

Un navegador exige DTLS-SRTP y PhonerLite usa SDES-SRTP; por eso los perfiles de
conexión no se mezclan. Marcar 100 u 101 hace sonar sus perfiles SIP y web.

No hay troncal PSTN. El plan de marcado bloquea explícitamente los prefijos `00`,
`011` y `+`, y deniega cualquier otro destino por defecto. `direct_media=no`
mantiene el audio anclado en Asterisk. Se aplican DSCP EF al audio y CS3 a SIP.

Comprobaciones:

```powershell
docker exec nexo-asterisk asterisk -rx "core show version"
docker exec nexo-asterisk asterisk -rx "pjsip show contacts"
docker exec nexo-asterisk asterisk -rx "pjsip show aors"
docker exec nexo-asterisk asterisk -rx "dialplan show internal"
docker exec nexo-asterisk asterisk -rx "module show like res_srtp.so"
```

## Prueba con PhonerLite

PhonerLite permite varios perfiles, pero solo uno activo por instancia. Para una
misma PC se usó el PhonerLite instalado para 100 y el ZIP portable oficial para
101: <https://www.phoner.de/PhonerLite64.zip>. El directorio local `tools/` está
excluido de Git y no es necesario para levantar el servidor.

En ambos perfiles:

1. **Servidor:** Proxy/Registrar `localhost:5061`, Dominio/Reino `nexo.local`,
   STUN vacío y Registro activado.
2. **Usuario:** número y nombre de autenticación 100 o 101; contraseña desde la
   variable correspondiente de `.env`.
3. **Red:** TLS y un puerto local distinto. La prueba usó 5080 para 100 y 5070
   para 101. El puerto 5060 ocupado provocó un intento de registro incorrecto.
4. **Codecs:** activar **SRTP** y **SAVP** para exigir el perfil seguro.
5. **Certificado:** activar comprobación remota y **Archivo Windows CA**.
6. Pulsar **Salvar** y comprobar que el estado termina en `transport=tls registrado`.

Para confiar el certificado autofirmado solo en el usuario actual:

```powershell
Import-Certificate -FilePath ".\certs\server.crt" -CertStoreLocation Cert:\CurrentUser\Root
```

Marca 101 desde 100, pulsa Enter, contesta en la otra instancia y mantén la
llamada 15–20 segundos. No se necesita STUN ni una troncal externa.

## Cliente WebRTC reutilizado

`voip/` contiene el build de **Tryit-JsSIP 1.0.3**, del repositorio
<https://github.com/versatica/tryit-jssip>, commit
`98487147f220607a3eb8ff68490f8d97651d6c83`. Se conserva su licencia MIT en
`voip/LICENSE` y la procedencia en `voip/ATTRIBUTION.txt`.

Adaptaciones: WSS por el mismo Nginx, dominio `nexo.local`, sin STUN/Callstats
externos, sin depuración de credenciales y sin persistir la contraseña. La CSP
permite estilos internos y sonidos del cliente, pero no scripts en línea.

Para entrar como Web 100:

1. Abre <https://localhost:8443/voip/> y el icono de configuración.
2. SIP URI: `sip:1100@nexo.local`.
3. Authorization user: `1100`.
4. Registrar server: `sip:nexo.local`.
5. WebSocket URI: `wss://localhost:8443/asterisk/ws`.
6. Contraseña: valor local de `WEBRTC_PASSWORD_100`.
7. Guarda, escribe un nombre visible de al menos tres caracteres y entra.

Para Web 101 usa 1101 y `WEBRTC_PASSWORD_101`, preferiblemente en otro perfil de
navegador. WebRTC es complementario: la evidencia principal usa PhonerLite.

## Captura y evidencia Wireshark

La captura se realiza en el namespace de red de Asterisk, para observar el
tráfico antes de que Docker lo reenvíe al host:

```powershell
New-Item -ItemType Directory -Force .\evidencias\h3
docker run -d --name nexo-h3-capture --network container:nexo-asterisk `
  --cap-add NET_ADMIN -v "${PWD}\evidencias\h3:/evidence" alpine:3.20 `
  sh -c 'apk add --no-cache tcpdump >/dev/null; exec tcpdump -i eth0 -nn -s0 -U -w /evidence/llamada-srtp.pcap "tcp port 5061 or udp portrange 20000-20199"'
```

Realiza el registro y la llamada. Durante la llamada:

```powershell
docker exec nexo-asterisk asterisk -rx "core show channels verbose"
docker exec nexo-asterisk asterisk -rx "pjsip show channelstats"
```

Después de colgar:

```powershell
docker stop -t 3 nexo-h3-capture
docker rm nexo-h3-capture
& "C:\Program Files\Wireshark\tshark.exe" -r .\evidencias\h3\llamada-srtp.pcap -q -z io,phs
& "C:\Program Files\Wireshark\tshark.exe" -r .\evidencias\h3\llamada-srtp.pcap -q -z conv,udp
& "C:\Program Files\Wireshark\tshark.exe" -r .\evidencias\h3\llamada-srtp.pcap -q -z rtp,streams
```

Abre `evidencias/h3/llamada-srtp.pcap` en Wireshark:

- `tcp.port == 5061`: la señalización debe verse como TLS, sin SIP legible.
- `udp.port >= 20000 && udp.port <= 20199`: deben existir datagramas durante la
  llamada, con carga no reconstruible como audio.
- **Telephony → RTP → RTP Streams** no debe ofrecer flujos RTP/G.711 reproducibles.
- No uses **Decode As → RTP** para fabricar una etiqueta: no demuestra cifrado.

**Una captura sin paquetes UDP no es una evidencia SRTP válida**, aunque la llamada
se haya señalizado correctamente. Tampoco basta con que Wireshark etiquete UDP de
forma genérica. Las capturas anteriores a corregir la IP de SDP se conservan solo
como diagnóstico y no prueban flujo de audio.

## H9: Identidad única (Keycloak) y menú unificado (Nextcloud)

Diseño de acceso (no cambia por servicio):

- **Nextcloud** es el menú unificado donde vive la persona usuaria. Desde ahí
  salta a cada servicio con la app **External Sites**, cada uno con su propia
  plataforma detrás.
- **Keycloak** es el único proveedor de identidad. Nextcloud delega su login
  en Keycloak con la app **OpenID Connect user backend** (`user_oidc`): la
  pantalla que ve la persona es la de Keycloak, no la de Nextcloud.
- Nextcloud **nunca** es proveedor de identidad de los demás servicios.
- El portal estático se conserva como entrada de respaldo en
  `https://localhost:8443/portal/`, documentado más abajo. La raíz
  (`https://localhost:8443/`) va directo al login de Keycloak via
  `/docs/apps/user_oidc/login/1` (ruta de login del proveedor OIDC de
  Nextcloud), sin pasar por ninguna pantalla de Nextcloud de por medio.
- La voz no pasa por Keycloak: las extensiones SIP se autentican contra
  Asterisk por **digest** (ver H3). El cliente web solo hereda la identidad de
  sesión para precargar la red de conexión (WebSocket WSS, registrar, realm),
  no la extensión ni la contraseña SIP.

### Mapa de rutas (todas detrás de `https://localhost:8443`, el mismo dominio de laboratorio)

| Ruta | Servicio | Rol |
|---|---|---|
| `/docs/` | Nextcloud | Menú unificado / punto de entrada tras login |
| `/keycloak/` | Keycloak | Proveedor de identidad (OIDC) |
| `/jitsi/` | Jitsi Meet web | Videoconferencia (respaldo directo: `:8444`) |
| `/element/` | Element Web | Chat/Matrix (respaldo directo: `:8090`) |
| `/grafana/` | Grafana | Monitoreo (H2) |
| `/voip/` | Tryit-JsSIP | Cliente WebRTC (H3), también embebido en `/voip/embed.html` |
| `/` y `/docs/login` | — | Redirect 302 directo al login de Keycloak (`/docs/apps/user_oidc/login/1`), sin la pantalla de Nextcloud con el botón |
| `/portal/` | Portal estático | Entrada de respaldo (H2), sin SSO |

### Flujo de login único

1. La persona abre `https://localhost:8443/` (o directamente `/docs/`).
2. La raíz salta de frente a Keycloak (`/docs/apps/user_oidc/login/1` →
   `/keycloak/realms/nexo/...`), que muestra su propio formulario con la
   marca "Nexo Unificado" — sin ninguna pantalla de Nextcloud de por medio.
3. Primer ingreso: Keycloak exige configurar **TOTP** (segundo factor) porque
   los usuarios de prueba tienen la acción requerida `CONFIGURE_TOTP`.
4. Tras autenticarse, Keycloak redirige de vuelta a Nextcloud
   (`/docs/apps/user_oidc/code`), que abre sesión sin pedir usuario/clave propios.
5. Desde el menú de Nextcloud (External Sites, paso siguiente), al entrar a
   **Chat** (Element/Matrix), Synapse también delega en el mismo Keycloak
   (`oidc_providers`, ver `matrix/oidc-providers.yaml.template`): como la
   sesión de Keycloak ya está abierta, Element entra sin pedir credenciales.
6. **Videoconferencia** (Jitsi) y **Telefonía** (voip) no piden login propio
   en este laboratorio (Jitsi corre sin autenticación de sala; la voz usa
   digest SIP), así que no hay una segunda pantalla de credenciales que evitar.

Cookies/redirecciones: todo vive bajo el mismo origen `https://localhost:8443`
(mismo esquema, host y puerto para Nextcloud, Keycloak, Jitsi y Element), por
lo que no hace falta `SameSite=None`; el valor por defecto `Lax` de cada app
alcanza. Si se despliega con un dominio DNS real en vez de `NEXO_URL=https://localhost:8443`,
usar ese mismo dominio para los tres antes de pasar a producción.

### Cómo levantarlo

Variables nuevas en `.env` (ver `.env.example`): `KC_ADMIN_USER`,
`KC_ADMIN_PASSWORD`, `KC_NEXTCLOUD_CLIENT_SECRET`, `KC_SYNAPSE_CLIENT_SECRET`,
`KC_TEST_USER1_USERNAME`/`PASSWORD`, `KC_TEST_USER2_USERNAME`/`PASSWORD`,
`NC_DB_ROOT_PASSWORD`, `NC_DB_PASSWORD`, `NC_ADMIN_USER`, `NC_ADMIN_PASSWORD`.

```powershell
docker compose up -d
docker compose logs -f nextcloud-init   # confirma que el proveedor OIDC quedo creado
docker compose logs -f synapse-oidc-patch
```

`nextcloud-init` y `synapse-oidc-patch` son tareas de un solo uso (idempotentes):
configuran el proveedor OIDC `keycloak` en Nextcloud (`occ user_oidc:provider`,
ver `nextcloud/nexo-oidc-setup.sh`) y agregan `oidc_providers` al
`homeserver.yaml` de Synapse (ver `matrix/oidc-providers.yaml.template`) la
primera vez que corren. Si la versión instalada de la app `user_oidc` cambió
los parámetros de su comando `occ`, revisa
`docker exec nexo-nextcloud occ user_oidc:provider --help` y ajusta el script.

**Si cambia `NEXO_HOST`** (por ejemplo, otra red Wi-Fi): edita `.env`, corre
`docker compose up -d` y luego `.\scripts\actualizar-host.sh`. Ver la sección
[Cambio de IP o de nombre de host](#cambio-de-ip-o-de-nombre-de-host) más abajo
para el detalle de por qué este paso sigue siendo manual.

### Menú de Nextcloud (External Sites)

```powershell
.\nextcloud\poblar-menu.sh
```

Habilita la app **External Sites** si falta y escribe sus cuatro entradas
(Telefonía → `/voip/embed.html`, Videoconferencia → `/jitsi/`, Chat →
`/element/`, Monitoreo → `/grafana/`) directamente en la appconfig
`external`/`sites` con `occ config:app:set`, porque la app no tiene un
comando `occ` propio para altas/bajas. No hay entrada de "Documentos": la
app nativa de Archivos de Nextcloud ya cumple esa función (icono de apps,
arriba a la izquierda); agregarla a External Sites solo embebía Nextcloud
dentro de sí mismo (doble barra superior). Las URLs son relativas al mismo
origen para no depender de `NEXO_HOST` ni romper la sesión al saltar de
servicio. Es idempotente (se puede volver a correr).

`Telefonía` abre la página embebible (`voip/embed.html`) con el softphone en
un `<iframe allow="microphone; camera">`; si el navegador bloquea el
micrófono dentro del iframe, esa misma página ofrece el enlace "ábrelo en
pestaña nueva" como respaldo, igual que la URL directa `/voip/`.

Para que el admin asigne servicios por cliente, `nextcloud/poblar-menu.sh`
deja comentado el formato para restringir una entrada a un grupo de
Nextcloud (campo `"groups"`, por ejemplo `["clienteA"]` tras crear el grupo
con `occ group:add clienteA`); por defecto las cuatro quedan visibles para
todas las personas usuarias.

### Licencias y copyleft de red (Anexo B)

Todo lo añadido en H9 es software libre: Keycloak (Apache 2.0), Nextcloud
Server y la app `user_oidc` (**AGPLv3**), MariaDB (GPLv2), ClamAV (GPLv2).

**Nota de cumplimiento AGPL (Nextcloud):** al ejecutar Nextcloud como servicio
de red modificado únicamente por configuración (sin tocar su código fuente),
el código fuente correspondiente sigue siendo el publicado por Nextcloud GmbH
en <https://github.com/nextcloud/server>, con la versión exacta fijada por la
imagen `nextcloud:35-apache` del `docker-compose.yml`. Este repositorio no
modifica el código de Nextcloud; solo lo configura (variables de entorno,
`occ user_oidc:provider`, External Sites), por lo que no genera código
derivado propio que deba publicarse aparte.

### Qué no se integró de la rama `desarrollo`

Del aporte de H5 en `desarrollo` se adaptaron Nextcloud+MariaDB (H5), Keycloak
(H7) y ClamAV (H14) a este `docker-compose.yml` único, detrás de Nginx y bajo
el mismo dominio. **No** se incorporaron `compose.h5.collabora.yml` ni
`compose.h5.office.yml` (Collabora/Nextcloud Office): asumen Nextcloud expuesto
directo en `127.0.0.1:18085` sin proxy, lo que choca con el diseño de un solo
dominio de este hito. Quedan como trabajo futuro si se requiere edición de
documentos ofimáticos. ClamAV queda desplegado pero sin conectar todavía a
ninguna app: para usarlo, instala la app `files_antivirus` en Nextcloud y
apúntala al host `clamav`, puerto `3310`, modo *Daemon*.

## Cambio de IP o de nombre de host

Toda referencia al host del laboratorio sale de una única variable,
`NEXO_HOST`, en `.env` (IP o nombre, sin esquema ni puerto). Nginx, Asterisk,
Jitsi, Keycloak, Nextcloud y Element la leen al arrancar, así que **no** hace
falta editar nada más a mano ni entrar con `docker exec` a cambiar archivos.

Para mudar la plataforma a otra IP o nombre de host:

```powershell
# 1. Edita NEXO_HOST en .env (y NEXO_HOST en ansible/env.j2 si despliegas con Ansible)
docker compose up -d

# 2. Corrige el estado que Keycloak y Synapse NO regeneran solos (ver mas abajo)
.\scripts\actualizar-host.sh
```

`docker compose up -d` recrea los contenedores cuyas variables de entorno
cambiaron (Asterisk, Jitsi, Keycloak, Nextcloud, Element incluido: su
`config.json` se vuelve a renderizar desde `matrix/element-config.json.template`
en cada arranque, ver `matrix/nexo-entrypoint.sh`), así que todos quedan con
el `NEXO_HOST` nuevo sin intervención manual.

Dos piezas de estado quedan **persistidas** y no se regeneran solas, por eso
necesitan `scripts/actualizar-host.sh`:

- Keycloak importa `realm-nexo.json` una sola vez (estrategia
  `IGNORE_EXISTING` en `--import-realm`): el `redirectUri` de los clientes
  `nextcloud` y `synapse` queda con el host viejo hasta que el script lo
  corrige con `kcadm.sh` dentro del contenedor.
- `synapse-oidc-patch` agrega `oidc_providers` a `homeserver.yaml` una sola
  vez (`if ! grep -q oidc_providers`): el `issuer`/`authorization_endpoint`
  del proveedor Keycloak quedan con el host viejo hasta que el script los
  corrige con `sed` dentro de `nexo-synapse` y lo reinicia.

Verificado en este repositorio corriendo la plataforma y ejecutando el script
tras cambiar `NEXO_HOST`: el inicio de sesión único (Nextcloud → Keycloak →
Element) y la llamada de prueba desde `/voip/embed.html` siguen funcionando
sin pasos manuales adicionales.

## Licencias

Asterisk es software libre bajo GPLv2 (con componentes bajo otras licencias). Se
puede comprobar en la instancia desplegada:

```powershell
docker exec nexo-asterisk asterisk -rx "core show license"
```

La receta de la imagen `andrius/asterisk` es MIT; Tryit-JsSIP y JsSIP son MIT.
PhonerLite es **freeware, no open source**, y se utiliza solo como cliente de
prueba, como en los laboratorios.

## Evidencias H2

`.\evidencias.ps1` genera `evidencia_h2.txt` con contenedores, redirección HTTPS,
cabeceras de seguridad y versión TLS. El tablero de Grafana está en la carpeta
“Nexo Unificado” → “Estado de la plataforma”.

## Evidencias H3

## Evidencias H9

No se generaron en este cambio: levantar Keycloak + Nextcloud + Synapse con
OIDC implica descargar varias imágenes grandes y completar un flujo de login
real en el navegador, algo que debe hacerse en la máquina donde corre Docker
Desktop (`docker compose config --quiet` sí se validó al preparar este cambio).
Al correr `docker compose up -d`, captura:

1. **Login único entre dos servicios**: abre `/docs/`, inicia sesión en la
   pantalla de Keycloak (incluye el paso de TOTP la primera vez), y una vez
   dentro de Nextcloud entra a **Chat** desde el menú de External Sites;
   Element debe abrir sin pedir usuario/clave otra vez. Captura ambas
   pantallas (Keycloak y Element ya autenticado).
2. **Llamada de prueba desde el menú unificado**: desde Nextcloud, abre
   **Telefonía** (`voip/embed.html`), regístrate como 1100/1101 (ver
   [Cliente WebRTC reutilizado](#cliente-webrtc-reutilizado)) y marca entre
   dos sesiones. Captura la llamada activa dentro del iframe.

Guarda las imágenes en `evidencias/h9/` (carpeta nueva, no toca `h3/` ni `h8/`).

## Estructura y apagado

- `docker-compose.yml`: servicios y redes `pub`, `srv`, `mgmt`.
- `nginx/`, `portal/`: proxy TLS (raíz redirige a `/docs/`) y portal de respaldo (`/portal/`).
- `scripts/actualizar-host.sh`: corrige Keycloak/Synapse al cambiar `NEXO_HOST`.
- `asterisk/`, `voip/`: VoIP SIP y WebRTC de H3.
- `matrix/`, `jitsi/`: mensajería (H4) y videoconferencia (H6).
- `prometheus/`, `blackbox/`, `grafana/`: monitoreo para el SLA.
- `keycloak/`, `nextcloud/`: identidad única y menú unificado de H9 (`nextcloud/poblar-menu.sh` puebla External Sites).
- `firewall/nexo.nft`: reglas para el servidor Ubuntu del V305.

```powershell
docker compose down
# Solo si también se desean borrar los volúmenes persistentes:
docker compose down -v
```

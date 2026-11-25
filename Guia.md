# Guía para ejecutar Nexo Unificado

Esta guía permite levantar toda la plataforma desde cero en Windows. Ejecuta los
comandos en **PowerShell**, desde la raíz del repositorio, donde se encuentra
`docker-compose.yml`.

## 1. Requisitos

- Docker Desktop para Windows con WSL2, instalado y en ejecución.
- Git para obtener el repositorio.
- Puertos libres: `8081` y `8443` TCP; `10000–10002` y `20000–20199` UDP.
- No detener Docker Desktop mientras se estén levantando los servicios.

Comprueba que Docker responde antes de continuar:

```powershell
docker version
docker compose version
```

## 2. Configurar `.env`

Si todavía no existe `.env`, crea una copia de la plantilla:

```powershell
Copy-Item .env.example .env
```

Edita el archivo:

```powershell
notepad .env
```

Define `NEXO_HOST` con la IPv4 del equipo que alojará la plataforma. Puedes
consultarla con `ipconfig`. Escribe únicamente la IP o el nombre de host, sin
`https://`, sin barra final y sin puerto:

```dotenv
NEXO_HOST=192.168.1.39
```

Genera los secretos técnicos que falten. El script conserva los valores que ya
existan; no vuelvas a copiar `.env.example` sobre un `.env` ya configurado:

```powershell
.\scripts\new-secrets.ps1
```

Para el asistente de IA, el proveedor define en `.env` `GEMINI_API_KEY` y
`GROQ_API_KEY` (con `GEMINI_MODEL` y `GROQ_MODEL`; el modelo gratuito de Groq por
defecto es `openai/gpt-oss-20b`). Es el modelo que usan todas las empresas salvo
que una configure el suyo (ver la sección 7).

`.env` no debe compartirse ni subirse a Git. Las contraseñas de los usuarios
finales tampoco van ahí: sus cuentas se crean posteriormente en Keycloak. Las
variables `H10_*_PASSWORD` que genera el script son **solo credenciales de
laboratorio para las pruebas automatizadas**; no deben reutilizarse en un entorno
real ni tratarse como cuentas de usuarios finales.

## 3. Levantar todos los servicios

El repositorio incluye `docker-compose.override.yml`. Docker Compose carga este
archivo automáticamente junto con `docker-compose.yml`, por lo que el despliegue
tradicional y las empresas ACME/BETA se levantan juntos **sin opciones `-f`
adicionales**. Con Docker Desktop en ejecución:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps --all
```

El primer arranque puede tardar porque descarga imágenes, construye los servicios
y ejecuta las tareas de inicialización. Espera a que finalicen antes de probar
el acceso.

Las tareas `certs`, `synapse-init`, `synapse-oidc-patch`, `nextcloud-init`,
`nextcloud-menu-init`, `nextcloud-tenants-init` y `host-update` deben terminar
con `Exited (0)`: es su estado normal. Los servicios persistentes deben quedar
activos y, cuando tienen comprobación de salud, `healthy`.

Si alguna inicialización falla, revisa su salida antes de repetir el arranque:

```powershell
docker compose logs certs
docker compose logs synapse-oidc-patch
docker compose logs nextcloud-init
docker compose logs nextcloud-menu-init
docker compose logs nextcloud-tenants-init
docker compose logs host-update
```

## 4. Instalar el certificado en cada equipo Windows

El laboratorio utiliza un certificado autofirmado. Debe instalarse en **cada
equipo cliente** que vaya a usar la plataforma, no solamente en el servidor.
Esto elimina la advertencia de confianza y permite que Element registre su
service worker para cargar imágenes y archivos autenticados.

En el equipo que contiene el repositorio:

```powershell
Import-Certificate -FilePath ".\certs\server.crt" -CertStoreLocation Cert:\CurrentUser\Root
```

En otro equipo, copia únicamente `certs/server.crt` por un medio seguro, abre
PowerShell en la carpeta donde lo guardaste y ejecuta:

```powershell
Import-Certificate -FilePath ".\server.crt" -CertStoreLocation Cert:\CurrentUser\Root
```

La instalación afecta solo al usuario actual de Windows. Cada persona que use
otra cuenta de Windows debe repetirla. **Nunca compartas `server.key`**, ya que
esa es la clave privada del servidor.

Cierra y vuelve a abrir el navegador si el aviso de certificado o el error del
service worker persisten.

## 5. Permitir acceso desde otros equipos

Este paso solo es necesario en el equipo que aloja los contenedores. En
PowerShell **como administrador**:

```powershell
netsh advfirewall firewall add rule name="Nexo HTTPS" dir=in action=allow protocol=TCP localport=8443 profile=any
netsh advfirewall firewall add rule name="Nexo JVB" dir=in action=allow protocol=UDP localport=10000-10002 profile=any
netsh advfirewall firewall add rule name="Nexo WebRTC" dir=in action=allow protocol=UDP localport=20000-20199 profile=any
```

Los demás equipos deben usar la IP configurada en `NEXO_HOST`; no uses
`127.0.0.1` ni `localhost` desde un cliente remoto.

Comprueba desde el otro equipo que el puerto responde:

```powershell
Test-NetConnection IP-DEL-SERVIDOR -Port 8443
```

`TcpTestSucceeded : True` indica que la web y el login llegan, pero no prueba el
audio y el video, que viajan por UDP. Si una llamada conecta y queda muda, también
puede estar bloqueando el firewall del **equipo cliente**: permite el navegador que
usa para el softphone (PowerShell como administrador):

```powershell
New-NetFirewallRule -DisplayName "Chrome UDP" -Direction Inbound -Program "C:\Program Files\Google\Chrome\Application\chrome.exe" -Protocol UDP -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Edge UDP" -Direction Inbound -Program "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -Protocol UDP -Action Allow -Profile Any
```

Asterisk anuncia `NEXO_HOST` como dirección de audio (ICE): al arrancar, su
entrypoint genera `rtp.conf` con `ice_host_candidates` para sustituir la IP interna
del contenedor por la del servidor. Evita apagar el firewall de Windows, salvo en
una prueba de un minuto, y vuelve a encenderlo.

Algunas redes, como la Wi-Fi de una universidad, aíslan los equipos o filtran el UDP
entre subredes. Si con las reglas anteriores no hay audio, conecta ambos equipos al
punto de acceso de un celular y repite la prueba.

## 6. Administrar empresas, usuarios y sectores

Hay un solo acceso para todos: `https://TU_IP:8443/` (o `/docs/`). Nginx dirige al
portal de acceso de Nexo, que busca el identificador o correo en Keycloak y abre
automáticamente el realm de la empresa correspondiente. La persona no elige
empresa. Sustituye `TU_IP` por el valor de `NEXO_HOST`. La ruta de acceso directo
es `https://TU_IP:8443/voip-sso/entrar`.

Hay tres niveles, cada uno con su propio alcance:

| Quién | Qué hace | Dónde |
|---|---|---|
| Proveedor | Da de alta empresas y su administrador | Archivos del repositorio y Keycloak (`/administracion/`) |
| Administrador de empresa | Crea sectores y usuarios de su empresa | Nextcloud: **Sectores y usuarios** y **Cuentas** |
| Usuario | Usa Nextcloud, Telefonía, Videoconferencia, Chat y el asistente | Nextcloud |

### 6.1 El proveedor da de alta una empresa

1. Añade la empresa a `tenants/registry.json`, con su nombre, los servicios que
   contrata (`telefonia`, `videoconferencia`, `chat`) y, si se quiere, el modelo de
   IA por defecto (`ai_provider`).
2. Regenera la configuración y levanta los servicios nuevos:

```powershell
python scripts/nexo-tenant.py render
docker compose up -d --build
```

3. Comprueba que las tareas de inicialización terminaron con `Exited (0)` (sección 3).
   Se crean automáticamente el realm `nexo-<empresa>`, los grupos de servicio
   (`<empresa>-servicio-telefonia`, etc.), el grupo `<empresa>-administradores` y los
   servicios propios de la empresa.

### 6.2 El proveedor crea al administrador de la empresa

**Opción A, con el script** (recomendada). La cuenta queda con una clave temporal,
que la persona debe cambiar en su primer acceso, y dentro del grupo
`<empresa>-administradores` y de los servicios contratados. El script se puede
repetir sin problema. Desde PowerShell, en la raíz del repositorio (cambia los
valores de `TENANT`, `ADMIN_USER`, `ADMIN_EMAIL` y `ADMIN_PASSWORD`):

```powershell
cmd.exe /c "docker exec -i -e TENANT=acme -e ADMIN_USER=admin.acme -e ADMIN_EMAIL=admin@acme.test -e ADMIN_PASSWORD=ClaveTemporal#2026 nexo-keycloak sh -s < scripts\crear-admin-empresa.sh"
```

**Opción B, desde Keycloak.**

1. Abre `https://TU_IP:8443/administracion/` e inicia sesión con `KC_ADMIN_USER` y
   `KC_ADMIN_PASSWORD` de `.env`.
2. En **Manage realms**, selecciona `nexo-acme` (o `nexo-beta`).
3. En **Users**, pulsa **Add user**, escribe el usuario, nombre y correo, activa
   **Email verified** y crea la cuenta.
4. En **Credentials**, define una contraseña y deja activada **Temporary**.
5. En **Groups**, pulsa **Join Group** y añádela a `acme-administradores` y a los
   grupos de servicio que correspondan.

Entrega al administrador su usuario y la clave temporal por un canal seguro.

### 6.3 El administrador crea sectores

1. Entra en `https://TU_IP:8443/` con su cuenta. En el primer acceso, cambia la clave
   temporal. Si acabas de recibir el permiso, cierra sesión y vuelve a entrar para
   actualizar el menú.
2. En el menú de aplicaciones, abre **Sectores y usuarios**. Solo lo ven los
   administradores de empresa.
3. En **Crear sector**, escribe el nombre (por ejemplo **Psicología**,
   **Administración** o **Asuntos generales**) y pulsa **Crear sector**.
4. El sector aparece en **Sectores existentes**, con su número de usuarios. Es un
   grupo `<empresa>-area-<nombre>` que también se crea en Keycloak.

### 6.4 El administrador crea usuarios

1. En el menú de aplicaciones, abre **Cuentas** (o usa el enlace de **Sectores y
   usuarios**).
2. Pulsa **Cuenta nueva** y completa el identificador, el nombre y el correo.
   Escribe un nombre corto como `kent`; el formulario antepone el prefijo de la
   empresa y guarda `acme.kent` para ACME (o `beta.kent` para BETA). El ID debe
   quedar en minúsculas y usar solo letras, números, punto, guion o guion bajo.
   La validación del servidor comprueba el prefijo antes de crear la cuenta. El
   nombre mostrado sí puede llevar mayúsculas y espacios (`Quillas ACME`).
3. En **Grupos**, elige el sector del usuario y los grupos de servicio que
   necesita (`<empresa>-servicio-telefonia`, `-videoconferencia`, `-chat`). Los
   servicios controlan qué aplicaciones ve cada persona; los sectores organizan a
   la gente.
4. Define una contraseña temporal y crea la cuenta. Se sincroniza en Keycloak
   como temporal; el usuario deberá cambiarla en el primer acceso.
5. La cuenta se crea también en Keycloak. Entrega al usuario su identificador y la
   clave temporal por un canal seguro. Para entrar, debe usar el identificador
   (`acme.kent`), no el nombre mostrado ni el correo del administrador que creó
   la cuenta. Keycloak pedirá cambiar la clave antes de abrir Nextcloud.

El administrador de empresa solo puede ver y gestionar los grupos y usuarios de su
empresa.

### 6.5 Cambios posteriores

Todo se hace desde **Cuentas** de Nextcloud y se replica a Keycloak:

- **Cambiar de sector o de servicios:** edita los grupos de la cuenta.
- **Restablecer la clave:** define una contraseña nueva; el usuario deberá
  cambiarla otra vez al entrar.
- **Cambiar el nombre o el correo:** edita la cuenta.
- **Dar de baja:** elimina la cuenta; también desaparece de Keycloak.

La identidad vive en Keycloak. Tras sincronizarse, la clave local de Nextcloud queda
bloqueada con un valor aleatorio: `/docs/admin-login` no permite entrar con la clave
inicial y las políticas de Keycloak se aplican siempre.

### 6.6 Entrar, cerrar sesión y cambiar de cuenta

- **Primer acceso del usuario:** abre `https://TU_IP:8443/`, escribe su ID completo
  (por ejemplo, `acme.kent`) y su clave temporal, y elige una clave nueva cuando
  Keycloak lo pida. Si Edge completa automáticamente el correo del administrador,
  reemplázalo por el ID de la cuenta nueva antes de continuar.
- **Cerrar sesión:** termina también la sesión de Keycloak y borra las cookies del
  sitio. Se puede entrar enseguida con otra cuenta sin errores de «state has
  expired».

Nextcloud, Matrix y la extensión de telefonía se aprovisionan en el primer acceso.
No crees cuentas independientes dentro de Element o Asterisk. Las identidades y el
directorio Matrix están separados por empresa.

## 7. Primer acceso y configuración de Chat

Accesos del laboratorio:

| Empresa | Portal | Element | Jitsi |
|---|---|---|---|
| ACME | `https://TU_IP:8443/acme/` | `https://TU_IP:8443/acme/element/` | `https://TU_IP:8443/acme/jitsi/` |
| BETA | `https://TU_IP:8443/beta/` | `https://TU_IP:8443/beta/element/` | `https://TU_IP:8443/beta/jitsi/` |
| Tradicional | `https://TU_IP:8443/` | `https://TU_IP:8443/element/` | `https://TU_IP:8443/jitsi/` |

En el portal de cada empresa, selecciona su proveedor de identidad cuando
Nextcloud lo solicite. Los enlaces visibles dependen de los grupos asignados en
Keycloak. Las salas Jitsi permanecen separadas por empresa.

### Asistente IA (AIRI)

Se abre desde el menú de Nextcloud, en **Asistente IA**, dentro de Nextcloud y sin
ocupar toda la pantalla. El personaje por defecto es **Oshin** (se pronuncia «O
shin»), con avatar 3D.

El proveedor habilita la función por empresa mediante `ai_provider` en el registro.
Después, el administrador entra en **Sectores y usuarios** y concede acceso a **Todos**
(incluidos los usuarios nuevos), **Nadie** o **Solo usuarios seleccionados**. Los permisos
usan el grupo ordinario `<empresa>-servicio-asistente-ia` de Nextcloud/Keycloak, no Teams.

- **Voz y modelo por defecto.** Responde con el modelo del proveedor (Gemini y,
  como respaldo, Groq) y habla con Pocket TTS, que corre en el servidor. Cada frase
  tarda unos segundos en generarse en un equipo con pocos núcleos.
- **Escuchar.** La entrada por voz usa la API de Voz Web del navegador (gratuita y
  local), en español. Requiere Chrome, Edge o Safari y permitir el micrófono.
- **Quién configura.** Todos los usuarios pueden cambiar el avatar y la tarjeta del
  personaje. Los ajustes de modelo y voz solo los ve el administrador de la empresa:
  si configura su propia API de chat o de voz, se aplica a toda la empresa y se
  guarda en el servidor.
- **Nombre y personalidad.** La tarjeta de Oshin en AIRI define el personaje que se
  ve, y el prompt del servidor (`SYSTEM_PROMPT` en `assistant/providers.py`) define
  cómo responde el modelo: se llama Oshin y conserva su personalidad (curiosa,
  divertida, sarcástica en tono suave, despistada y con miedo a las alturas, y habla
  en español de Perú). Para
  cambiarla, edita ese prompt y reconstruye la imagen del asistente
  (`docker compose up -d --build assistant`).
- **Historial.** Cada usuario guarda su propio historial de conversación.

### Llamadas

- **Dentro de la empresa.** Abre un chat directo en **Element** e inicia la
  llamada desde ahí. Asterisk bloquea la marcación de extensiones de la misma
  empresa, incluso con el prefijo `9`.
- **Entre empresas.** Abre **Telefonía** en el menú de Nextcloud y marca `9 + extensión`
  del destino. Por ejemplo, desde ACME marca `92706` para llamar a beta1 (extensión
  `2706`) y desde BETA marca `91362` para llamar a acme1 (extensión `1362`), si tu
  extensión tiene habilitadas las llamadas entre empresas. Cada usuario ve su
  extensión en el estado «registrado» del softphone (`sip:EXT@empresa.nexo.local`).
- **Dos softphones en un mismo equipo.** Abre cada cuenta en una ventana InPrivate
  distinta, porque Keycloak reutiliza la sesión del navegador. Usa audífonos o
  silencia un micrófono para evitar el acople de audio.

### Configurar Chat

Chat utiliza cifrado extremo a extremo (E2EE). Keycloak verifica la cuenta,
pero cada dispositivo de Element tiene sus propias claves criptográficas. En la
primera sesión de **cada usuario**:

1. Abre **Chat**.
2. Entra en **Ajustes rápidos → Ajustes → Encryption**.
3. Pulsa **Create recovery key**.
4. Guarda la clave en un gestor de contraseñas o en otro lugar seguro.
5. Pulsa **Continuar** para finalizar.

La clave de recuperación es privada e individual. No la compartas, no la guardes
en `.env` y no uses la clave de una persona para verificar la cuenta de otra.
Al abrir la misma cuenta en otro navegador o dispositivo, introduce su clave de
recuperación cuando Element la solicite. No es necesario repetir la verificación
cada vez que se abre una sesión ya verificada, salvo que se borren los datos del
navegador o se cierre la sesión.

Puedes abrir varias aplicaciones distintas simultáneamente, pero mantén una sola
pestaña de Chat por perfil del navegador: Element bloquea las instancias
simultáneas de la misma sesión para proteger su almacenamiento criptográfico.

## 8. Cambiar la IP del servidor

Edita únicamente `NEXO_HOST` en `.env` y vuelve a ejecutar:

```powershell
docker compose up -d --build
docker compose ps --all
```

El arranque actualiza el certificado y las URLs de los servicios. Después,
instala el nuevo `certs/server.crt` en los equipos clientes.

Para ver la IP correcta ejecuta `ipconfig | findstr /i "IPv4"` y usa la del adaptador
Wi-Fi o Ethernet real, no la de VirtualBox (`192.168.56.x`) ni la de WSL o Docker
(`172.x`). Si el equipo cambia de red, la IP puede cambiar: repite este paso y
vuelve a iniciar sesión en los softphones para que se registren de nuevo.

## 9. Diagnóstico

```powershell
docker compose logs proxy
docker compose logs keycloak
docker compose logs synapse
docker compose logs voip-gateway
docker compose logs asterisk
```

- **Llamada conectada pero sin audio:** durante la llamada ejecuta
  `docker exec nexo-asterisk asterisk -rx "pjsip show channelstats"`. Un canal con
  `Receive` en 0 indica que su audio no llega al servidor: revisa las reglas UDP del
  servidor y del cliente (sección 5) y el permiso de micrófono del navegador.
- **Element pide «Confirm your digital identity»:** es la verificación de cifrado de
  una sesión nueva. Elige «Can't confirm?» y luego «Reset identity». Si la sala vieja
  no se descifra, crea una sala nueva sin cifrado.
- **El asistente responde error 413:** el historial de la conversación es demasiado
  largo para el límite de tamaño de Nginx. Abre un **Nuevo chat**.
- **502:** comprueba que el servicio correspondiente esté activo y reinicia el
  proxy con `docker compose restart proxy` si se recreó un upstream por separado.
- **400 al abrir administración:** usa `https://` en el puerto `8443`.
- **No aparecen los grupos de empresa:** comprueba que estás en `nexo-acme` o
  `nexo-beta`. El realm general `nexo` tiene su propia lista de grupos.
- **Keycloak muestra «Invalid username or password»:** comprueba que escribiste el
  ID completo de la cuenta (por ejemplo, `acme.kent`) y su clave temporal asignada
  al crearla, no el correo o la clave del administrador. Si el usuario o la clave
  se corrigieron después de crear la cuenta, restablece la contraseña en **Cuentas**
  y vuelve a intentar el acceso.
- **Aviso de certificado:** comprueba que `NEXO_HOST` coincida con la dirección
  usada y que el certificado esté instalado en el usuario actual de Windows.
- **Failed to load service worker:** instala el certificado, cierra por completo
  el navegador y vuelve a abrir Chat.
- **El asistente no responde o dice que la sesión caducó:** vuelve a abrirlo desde el
  menú de Nextcloud. Si el problema continúa, revisa `docker compose logs assistant`.
- **El asistente no habla:** comprueba `docker compose logs pocket-tts` (puede tardar
  en arrancar tras reiniciar) y que el audio esté activado en AIRI.
- **Telefonía de empresa no disponible:** comprueba que el usuario pertenece al
  grupo de servicio de telefonía de su empresa y revisa los logs de
  `voip-gateway` y `asterisk`.

## 10. Apagar

```powershell
docker compose down
```

Esto conserva usuarios, mensajes, datos y extensiones. Para volver a iniciar la
plataforma:

```powershell
docker compose up -d --build
```

`docker compose down -v` borra también los volúmenes persistentes y solo debe
usarse cuando se quiera reiniciar completamente el laboratorio.

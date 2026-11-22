# Guía para ejecutar Nexo Unificado

Esta guía permite levantar toda la plataforma desde cero en Windows. Ejecuta los
comandos en **PowerShell**, desde la raíz del repositorio, donde se encuentra
`docker-compose.yml`.

## 1. Requisitos

- Docker Desktop para Windows con WSL2, instalado y en ejecución.
- Git para obtener el repositorio.
- Puertos libres: `8081` y `8443` TCP; `10000` y `20000–20199` UDP.
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

`.env` no debe compartirse ni subirse a Git. Las contraseñas de los usuarios
finales tampoco van ahí: sus cuentas se crean posteriormente en Keycloak.

## 3. Levantar todos los servicios

Con Docker Desktop en ejecución:

```powershell
docker compose up -d --build
docker compose ps --all
```

El primer arranque puede tardar porque descarga imágenes, construye los servicios
y ejecuta las tareas de inicialización. Espera a que finalicen antes de probar
el acceso.

Las tareas `certs`, `synapse-init`, `synapse-oidc-patch`, `nextcloud-init`,
`nextcloud-menu-init` y `host-update` deben terminar con `Exited (0)`: es su
estado normal. Los servicios persistentes deben quedar activos y, cuando tienen
comprobación de salud, `healthy`.

Si alguna inicialización falla, revisa su salida antes de repetir el arranque:

```powershell
docker compose logs certs
docker compose logs synapse-oidc-patch
docker compose logs nextcloud-init
docker compose logs nextcloud-menu-init
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
netsh advfirewall firewall add rule name="Nexo JVB" dir=in action=allow protocol=UDP localport=10000 profile=any
netsh advfirewall firewall add rule name="Nexo WebRTC" dir=in action=allow protocol=UDP localport=20000-20199 profile=any
```

Los demás equipos deben usar la IP configurada en `NEXO_HOST`; no uses
`127.0.0.1` ni `localhost` desde un cliente remoto.

## 6. Crear usuarios

1. Abre `https://TU_IP:8443/keycloak/admin/`.
2. Entra con `KC_ADMIN_USER` y `KC_ADMIN_PASSWORD` definidos en `.env`.
3. Selecciona el realm `nexo`.
4. Entra en **Users → Add user**, completa los datos y habilita la cuenta.
5. En **Credentials**, asigna una contraseña temporal o definitiva.

Nextcloud, Matrix y la extensión de telefonía se aprovisionan automáticamente en
el primer acceso. No crees cuentas independientes dentro de Element o Asterisk.

## 7. Primer acceso y configuración de Chat

Abre `https://TU_IP:8443/` e inicia sesión con la cuenta creada en Keycloak.
Desde Nextcloud puedes abrir Telefonía, Videoconferencia y Chat bajo la misma
IP y el mismo puerto.

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

## 9. Diagnóstico

```powershell
docker compose logs proxy
docker compose logs keycloak
docker compose logs synapse
docker compose logs voip-gateway
docker compose logs asterisk
```

- **502:** comprueba que el servicio correspondiente esté activo y reinicia el
  proxy con `docker compose restart proxy` si se recreó un upstream por separado.
- **Aviso de certificado:** comprueba que `NEXO_HOST` coincida con la dirección
  usada y que el certificado esté instalado en el usuario actual de Windows.
- **Failed to load service worker:** instala el certificado, cierra por completo
  el navegador y vuelve a abrir Chat.
- **Telefonía no disponible:** revisa los logs de `voip-gateway` y que el cliente
  OIDC `voip` exista en el realm `nexo`.

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

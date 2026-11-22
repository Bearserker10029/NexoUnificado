# Guía para ejecutar Nexo Unificado

## 1. Requisitos

- Docker Desktop para Windows con WSL2.
- Puertos libres: `8081` y `8443` TCP; `10000` y `20000–20199` UDP.
- Trabajar desde la raíz del proyecto, donde está `docker-compose.yml`.

## 2. Configurar `.env`

Si el archivo no existe:

```powershell
Copy-Item .env.example .env
.\scripts\new-secrets.ps1
```

Define `NEXO_HOST` con la IPv4 de tu equipo, obtenida mediante `ipconfig`. No
incluyas `https://` ni el puerto. Las contraseñas de usuarios finales no van en
este archivo; esas cuentas se administran en Keycloak.

## 3. Levantar la plataforma

```powershell
docker compose up -d --build
docker compose ps --all
```

Las tareas `certs`, `synapse-init`, `nextcloud-init`, `nextcloud-menu-init` y
`host-update` terminan con `Exited (0)`: es su estado normal. Los servicios
persistentes deben quedar activos y, cuando tienen comprobación, `healthy`.

## 4. Firewall para otros equipos

En PowerShell como administrador:

```powershell
netsh advfirewall firewall add rule name="Nexo HTTPS" dir=in action=allow protocol=TCP localport=8443 profile=any
netsh advfirewall firewall add rule name="Nexo JVB" dir=in action=allow protocol=UDP localport=10000 profile=any
netsh advfirewall firewall add rule name="Nexo WebRTC" dir=in action=allow protocol=UDP localport=20000-20199 profile=any
```

## 5. Crear usuarios

1. Abre `https://TU_IP:8443/keycloak/admin/`.
2. Entra con la cuenta de administrador definida en `.env`.
3. Selecciona el realm `nexo` y crea cada persona desde **Users**.
4. Asigna su clave en **Credentials**.

Nextcloud, Matrix y la extensión de telefonía se aprovisionan automáticamente en
el primer acceso. No crees cuentas independientes dentro de Element o Asterisk.

## 6. Usar la plataforma

Abre `https://TU_IP:8443/` y acepta el certificado autofirmado del laboratorio.
Desde Nextcloud, el menú abre Telefonía, Videoconferencia y Chat bajo la misma
IP y el mismo puerto. Telefonía y Chat aprovechan la sesión de Keycloak; Jitsi
no solicita una cuenta adicional.

## 7. Diagnóstico

```powershell
docker compose logs proxy
docker compose logs keycloak
docker compose logs synapse
docker compose logs voip-gateway
docker compose logs asterisk
```

- **502:** comprueba que el upstream esté activo y reinicia `nexo-proxy` si fue
  recreado manualmente sin Compose.
- **Aviso de certificado:** verifica que `NEXO_HOST` coincida con la IP usada y
  que el SAN de `certs/server.crt` la incluya.
- **Telefonía no disponible:** revisa los logs de `voip-gateway` y que el cliente
  OIDC `voip` exista en el realm `nexo`.

## 8. Apagar

```powershell
docker compose down
```

Esto conserva los datos. `docker compose down -v` borra también los volúmenes y
solo debe usarse cuando se quiera reiniciar completamente el laboratorio.

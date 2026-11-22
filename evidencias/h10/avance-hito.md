# H10 · Soporte multiempresa en Nexo Unificado

Fecha de implementación: 2026-11-22.

## Resultado

El archivo `docker-compose.yml` conserva el despliegue tradicional y sus rutas. La capa `docker-compose.override.yml`, cargada automáticamente por Compose, añade las instancias aisladas sin sustituirlo. `docker-compose.multiempresa.yml` se conserva como copia equivalente para compatibilidad y consulta.

| Empresa | Rango SIP | Extensión TLS de prueba | Realm Keycloak | Homeserver Matrix | Acceso |
|---|---|---|---|---|---|
| ACME | 1000–1999 | 1001 | `nexo-acme` | `acme.nexo.local` | `/acme/` |
| BETA | 2000–2999 | 2001 | `nexo-beta` | `beta.nexo.local` | `/beta/` |

Las extensiones WebRTC dinámicas usan 1100–1999 y 2100–2999 para no colisionar con las extensiones TLS de laboratorio.

## División de roles implementada

- **Misma empresa:** Element usa las llamadas 1:1 nativas de Matrix (`m.call.invite`, SDP/ICE y WebRTC). No hay Asterisk en esa ruta.
- **Entre empresas:** el terminal marca `9 + extensión`. Por ejemplo, ACME 1001 llama a BETA 2001 mediante `92001`. Asterisk quita el 9, comprueba que el destino no pertenece al contexto de origen y ejecuta `Dial(PJSIP/2001)`.
- **Grupos:** Jitsi conserva las videoconferencias grupales, con una pila web/Prosody/Jicofo/JVB por empresa y autorización OIDC en Nginx.
- **PSTN:** no se habilitó ninguna troncal. Los contextos deniegan por defecto; la ruta interempresas es la base para una futura salida controlada.

## Decisión sobre Synapse

### Opción evaluada: espacios aislados en un solo homeserver

No se eligió. Los espacios organizan salas, pero no constituyen una frontera de inquilino: el directorio de usuarios, las invitaciones y los mensajes directos siguen perteneciendo al mismo homeserver. Impedir toda búsqueda y conversación cruzada requeriría módulos/políticas adicionales y una revisión continua de cada API.

### Opción recomendada e implementada: homeserver por empresa

Cada empresa tiene `server_name`, base SQLite, medios, clave de firma y dominio Matrix propios. Los listeners no habilitan federación, por lo que tampoco basta con escribir manualmente `@beta1:beta.nexo.local` desde ACME. Element apunta al homeserver de su empresa y mantiene las llamadas 1:1 nativas dentro de ese dominio.

En una LAN de laboratorio, WebRTC puede usar candidatos de host. Para clientes detrás de NAT simétrico o redes externas se necesitará planificar TURN; no se añadió un servicio nuevo en este hito.

## Identidad, contratación y menú

Se eligió **un realm por empresa** y grupos de servicios dentro de cada realm:

- `acme-servicio-chat`, `acme-servicio-telefonia`, `acme-servicio-videoconferencia`.
- `beta-servicio-chat`, `beta-servicio-telefonia`, `beta-servicio-videoconferencia`.

Los clientes OIDC `nextcloud`, `synapse` y `nexo-portal` se generan por realm. Nextcloud configura un proveedor por empresa y entradas de menú distintas, restringidas al grupo correspondiente. No basta con ocultar el enlace: el gateway también verifica empresa y grupo antes de entregar telefonía o autorizar Jitsi.

## Transporte SIP y CDR

- WebRTC sigue registrándose por **WSS 8443**, terminado en Nginx.
- Los terminales SIP de laboratorio usan **TLS 5061 interno**.
- No se publica UDP/TCP 5060 ni UDP 5060; tampoco se publica 5061 al host.
- `cdr_custom.conf` crea `cdr-custom/interempresas.csv` con inicio, llamante, origen, destino marcado, empresa de origen, origen, destino sin prefijo, disposición, segundos facturables y `uniqueid`.
- `unanswered=yes` conserva también intentos no contestados para conciliación; el campo `billsec` permite facturar únicamente tiempo contestado.

## Alta parametrizada de una empresa

Desde la raíz del repositorio:

```powershell
python scripts/nexo-tenant.py add GAMMA --range-prefix 3 --display-name "Gamma S.A.C." `
  --services chat,telefonia,videoconferencia
```

Este único comando actualiza `tenants/registry.json` y genera:

- contexto y rango en `tenants/gamma/asterisk/extensions.conf`;
- plantilla de endpoint PJSIP y extensión TLS inicial;
- realm, clientes OIDC y grupos contratados;
- homeserver, Element y rutas Nginx;
- servicios Synapse/Jitsi de `docker-compose.override.yml`, cargado automáticamente por Compose, y de su copia compatible `docker-compose.multiempresa.yml`.

`render` regenera todo desde el registro, sin editar a mano archivos derivados:

```powershell
python scripts/nexo-tenant.py render
```

## Despliegue

1. Ejecutar `.\scripts\new-secrets.ps1` para completar los secretos técnicos ausentes, incluidos `TENANT_ACME_SIP_PASSWORD` y `TENANT_BETA_SIP_PASSWORD`.
2. Ejecutar sin parámetros `-f`; el override multiempresa se carga automáticamente:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps --all
```

3. Abrir los puertos UDP 10001 y 10002 para JVB de ACME y BETA, además de los puertos ya usados por el sistema.
4. Los realm nuevos se importan al arrancar Keycloak. El modo de importación no sobrescribe realms existentes; un cambio posterior de servicios en un realm ya creado debe sincronizarse desde la administración de Keycloak.

## Usuarios de prueba

`scripts/crear-usuarios-h10.sh` crea `acme1`, `acme2` y `beta1`, asigna sus claves y los agrega a los grupos contratados. Las claves se pasan por variables, no se almacenan en el repositorio:

```bash
# Git Bash o WSL, con Docker Desktop accesible desde el CLI:
KC_ADMIN_USER=nexo_admin KC_ADMIN_PASSWORD='...' \
ACME1_PASSWORD='...' ACME2_PASSWORD='...' BETA1_PASSWORD='...' \
./scripts/crear-usuarios-h10.sh
```

Para acceder al menú de cada empresa, usar el proveedor Nextcloud `keycloak-acme` o `keycloak-beta`; `occ user_oidc:provider --output=json` muestra sus identificadores numéricos. Los endpoints SIP-TLS 1001/2001 se registran con las claves `TENANT_*_SIP_PASSWORD`; no son las claves personales de Keycloak.

## Evidencias obtenidas

La ejecución real de `python -m unittest tests.test_multiempresa -v` terminó con **8 pruebas OK**. El resultado completo está en `validacion-estatica.txt`; el entorno está en `entorno.txt`.

Comprobado automáticamente:

- rangos y contextos ACME/BETA, ruta 9 y denegación por defecto;
- campos CDR de facturación por inquilino;
- plantillas TLS y endpoints WSS; ausencia de puertos SIP publicados;
- homeservers distintos sin listener de federación;
- realms y grupos de servicios distintos;
- Element asociado al homeserver correcto y pilas Jitsi independientes;
- conservación de rutas tradicionales e inclusión opcional de empresas;
- sintaxis Python de los generadores, gateway y pruebas.

También se comprobó `sh -n` en los entrypoints y scripts nuevos y se analizó el YAML base y la capa multiempresa con un parser YAML.

## Pruebas funcionales ejecutadas con Docker

Docker Engine 29.9.3 y Docker Compose 5.7.0 sí estaban disponibles mediante los ejecutables de Docker Desktop. Se desplegó la capa completa, `docker-compose config --quiet` validó la unión de archivos y `contenedores.txt` conserva el estado final.

`scripts/validar-h10.py` terminó correctamente y generó `funcional.txt` con estas evidencias reales:

1. identidades Matrix `@acme1:acme.nexo.local`, `@acme2:acme.nexo.local` y `@beta1:beta.nexo.local`;
2. sala directa ACME1–ACME2, aceptación de ACME2 y evento `m.call.invite`;
3. bloqueo de invitación ACME1–BETA1 con HTTP 502 y ausencia de `beta1` en el directorio ACME;
4. recorrido `1001 → 92001 → Dial(PJSIP/2001)` por el contexto `tenant-acme`;
5. CDR real con fecha, origen `1001`, destino marcado `92001`, empresa `acme` y detalle `origen=1001,destino=2001,tipo=interempresas`.

La última línea de `cdr-interempresas-real.txt` es la evidencia válida. La disposición es `FAILED` y `billsec=0` porque los endpoints TLS 1001/2001 no tenían contactos registrados. Por tanto, la prueba demuestra enrutamiento y registro, **no audio SIP contestado**.

La prueba de Element demuestra sala directa y señalización nativa de llamada 1:1, sin Asterisk. La negociación y recepción de audio/video WebRTC debe completarse con ambos usuarios conectados a Element y permisos de micrófono/cámara; la prueba API no afirma haber verificado medios.

También se comprobó:

- `/_matrix/client/versions` responde correctamente en ACME y BETA;
- Element ACME/BETA responde HTTP 200;
- los discovery OIDC de `nexo-acme` y `nexo-beta` responden HTTP 200;
- Jitsi ACME/BETA sin sesión responde HTTP 302 hacia su login OIDC, conservando `:8443`;
- Nginx supera `nginx -t` y Asterisk carga `cdr_custom.so`.

Para repetir la validación se pueden definir `ACME1_MATRIX_TOKEN`, `ACME2_MATRIX_TOKEN` y `BETA1_MATRIX_TOKEN`; como alternativa, el script admite las claves de laboratorio y realiza el login. Conviene reutilizar tokens para no activar el límite antiabuso de Synapse. La evidencia se sobrescribe en `funcional.txt`.

Comandos de apoyo:

```powershell
docker exec nexo-asterisk asterisk -rx "dialplan show tenant-acme"
docker exec nexo-asterisk asterisk -rx "dialplan show tenant-beta"
docker exec nexo-asterisk asterisk -rx "pjsip show endpoints"
docker exec nexo-asterisk asterisk -rx "pjsip show contacts"
docker exec nexo-asterisk tail -n 20 /var/log/asterisk/cdr-custom/interempresas.csv
```

## Archivos principales

- `scripts/nexo-tenant.py`: alta y generación idempotente.
- `tenants/registry.json`: fuente declarativa de empresas.
- `asterisk/extensions.conf`, `pjsip.conf.template`, `cdr_custom.conf`: integración sin eliminar el contexto `internal`.
- `voip-gateway/app.py`: OIDC multi-realm, autorización y rangos SIP por empresa.
- `matrix/tenant-entrypoint.sh`: renderizado de Synapse.
- `nextcloud/tenants-oidc-setup.sh`: proveedores y menú por contratación.
- `tests/test_multiempresa.py`: regresión estática.
- `scripts/validar-h10.py`: prueba funcional reproducible.

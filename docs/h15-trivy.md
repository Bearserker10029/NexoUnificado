# H15 · Escaneo de vulnerabilidades con Trivy (antes / después)

Método: contenedor temporal `aquasec/trivy:latest` con el socket de Docker (nada instalado en el host), severidad `HIGH,CRITICAL`, lista de imágenes de `docker compose config --images` (`evidencias/h15/imagenes.txt`). Sin `.trivyignore` ni filtros: se reportan también los hallazgos **sin parche**. Reproducible con `scripts/h15-trivy.sh antes|despues`; tabla con `scripts/h15-tabla.py`.

- Reportes: `evidencias/h15/antes/` y `evidencias/h15/despues/` (JSON + tabla de texto por imagen).
- Tabla completa (todas las filas CVE): `evidencias/h15/tabla-vulnerabilidades.csv`.
- Verificación de servicios tras el cambio: `evidencias/h15/verificacion-servicios.txt`.

## Correcciones aplicadas (solo imágenes con versión parcheada disponible; cambio de etiqueta en `docker-compose.yml`)

| Imagen inicial | Imagen corregida | HIGH+CRIT antes (CRIT) | HIGH+CRIT despues (CRIT) | CVE corregidos | CVE nuevos |
|---|---|---|---|---|---|
| alpine:3.20 | alpine:3.22 | 2 (0) | 0 (0) | 2 | 0 |
| docker:27-cli | docker:28-cli | 121 (8) | 117 (7) | 12 | 8 |
| nginx:1.27-alpine | nginx:1.29-alpine | 70 (3) | 58 (1) | 32 | 20 |
| prom/prometheus:v2.55.1 | prom/prometheus:v3.5.0 | 60 (2) | 56 (2) | 5 | 1 |
| prom/node-exporter:v1.8.2 | prom/node-exporter:v1.9.1 | 52 (1) | 48 (1) | 5 | 1 |
| prom/blackbox-exporter:v0.25.0 | prom/blackbox-exporter:v0.27.0 | 56 (3) | 50 (2) | 6 | 0 |
| grafana/grafana:11.3.0 | grafana/grafana:11.6.0 | 105 (7) | 114 (8) | 11 | 20 |


## Resultado honesto

- Las actualizaciones **reducen** CVE en nginx (70→58), alpine (2→0), blackbox, node-exporter y prometheus, pero la mejora es **modesta**: la mayoría de los hallazgos restantes vienen de binarios Go o paquetes del sistema base que dependen de los mantenedores de cada imagen.
- **Grafana 11.6.0 aumentó** los hallazgos (105→114) con la base de datos actual: la subida **se revirtió** a `11.3.0` (el escaneo "después" de 11.6.0 se conserva como evidencia). No se aplica un cambio que empeora y añade riesgo de migración.
- `docker:28-cli` mejora marginalmente (121→117).
- **No corregidas** (decisión consciente): `nextcloud:35-apache`, `ghcr.io/jitsi/*:stable-11509`, `matrixdotorg/synapse:latest`, `vectorim/element-web:latest`, `andrius/asterisk:20.21.0_debian-trixie`, `mariadb:11.4`, `keycloak:26.8.2`, `clamav/clamav:stable`: se requeriría saltar versión mayor/cambiar tags flotantes con riesgo para SSO, Matrix y telefonía, o no hay versión parcheada. Quedan como riesgo residual documentado.
- `nexo-assistant`, `nexo-pocket-tts` y `nexo-voip-gateway` son imágenes construidas localmente; las dos primeras no estaban construidas en esta máquina y **no se escanearon** (`antes/nexo-*.log`); `nexo-voip-gateway` sí.
- Limitaciones: la base de vulnerabilidades de Trivy cambia día a día (hubo CVE "nuevos" al reescanear con la base más reciente); las pruebas de login y llamada se hicieron a nivel de protocolo (ver abajo), no con un usuario real ni un softphone.

## Verificación de servicios (local, tras recrear solo los servicios afectados)

- Proxy `nginx:1.29-alpine` healthy; `/healthz` responde por 8443 (TLS) y 8081.
- **Login:** `/` redirige a `/docs/apps/user_oidc/login/1` que redirige (303) al endpoint de autorización de Keycloak del realm `nexo`; el discovery OIDC responde 200. No se ingresó un usuario real en esta verificación.
- **Llamada:** Asterisk con transportes `transport-tls` (5061) y `transport-ws` (8088); 5061 abierto, 5060/UDP cerrado. No se realizó una llamada real entre dos clientes.
- Prometheus: todos los targets `up`; Element, Jitsi, softphone y Grafana (vía proxy) HTTP 200.

# Nexo Unificado · Entorno base (hito H2)

Proxy inverso con TLS, portal web responsivo y monitoreo (Prometheus, Grafana y Blackbox),
sobre redes Docker separadas que reproducen la segmentación de la Figura 2 del informe.

## Requisitos

- Docker Desktop con el backend WSL2 activado (comprueba con `docker --version` y `docker compose version`).
- Puertos libres en tu laptop: 8080 y 8443.

## Levantar el entorno

Abre PowerShell dentro de esta carpeta y ejecuta:

    docker compose up -d
    docker compose ps

La primera vez descarga las imágenes (unos minutos). Cuando todos los servicios estén en
`healthy` o `running`:

- Portal: https://localhost:8443  (el navegador avisará que el certificado es autofirmado: es normal en laboratorio)
- Monitoreo: https://localhost:8443/grafana/  (usuario `admin`, la clave está en el archivo `.env`)
- En Grafana abre la carpeta "Nexo Unificado" > "Estado de la plataforma".

Para apagar: `docker compose down`. Para borrar también los datos: `docker compose down -v`.

## Evidencias del hito H2

Capturas de pantalla sugeridas (que se vea la fecha y el nombre del equipo):

1. PowerShell con `docker compose ps` (contenedores activos y en estado healthy).
2. El portal en el navegador, con el candado/aviso de HTTPS visible.
3. El tablero de Grafana con "Portal disponible: ACTIVO" y la disponibilidad.
4. Opcional: la ventana del portal en tamaño de celular (F12 > modo dispositivo) para mostrar el diseño responsivo.

Además, `.\evidencias.ps1` genera `evidencia_h2.txt` con el estado de los contenedores,
la redirección a HTTPS, las cabeceras de seguridad y la versión de TLS negociada.

## Estructura

- `docker-compose.yml`: definición de todos los servicios y redes (`pub`, `srv`, `mgmt`).
- `nginx/`: configuración del proxy (TLS 1.2 y 1.3, cabeceras de seguridad, límite de peticiones).
- `portal/`: página de inicio responsiva.
- `prometheus/`, `blackbox/`, `grafana/`: monitoreo y medición de disponibilidad para el SLA.
- `firewall/nexo.nft`: reglas de nftables para el servidor Ubuntu del V305 (no aplican en Windows).
- `.env`: credenciales locales. No se sube a Git. Plantilla en `.env.example`.

## Notas

- Este entorno es la base. Voz (H3), chat (H4), documentos (H5) y video (H6) se agregan como servicios nuevos en el mismo `docker-compose.yml`.
- Para el V305 se usa el mismo Compose en un Ubuntu Server, más `firewall/nexo.nft`.

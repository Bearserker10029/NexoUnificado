# H7 – MFA (TOTP) con SSO Keycloak

Entorno: Docker Compose local, `NEXO_HOST=127.0.0.1`, volúmenes nuevos, realm `nexo`.
Usuarios de prueba creados con `scripts/h7-configurar-totp.sh` (`ana.prueba`,
`beto.prueba`; clave de prueba pasada por variable de entorno, no está en el repo).

## Configuración
- `scripts/h7-configurar-totp.sh`: fija política TOTP (SHA1, 6 dígitos, 30 s), activa la
  acción obligatoria `CONFIGURE_TOTP` como acción por defecto y la asigna a los usuarios.
- `scripts/h7-totp.py`: genera el código TOTP desde la clave base32 (RFC 6238) porque
  la prueba se hizo sin teléfono. Con un teléfono se escanea el QR de la captura 02.

## Flujo capturado
| # | Captura | Qué muestra |
|---|---------|-------------|
| 01 | `01-login-usuario-clave.jpg` | Login Keycloak (usuario + contraseña) al entrar a Nextcloud |
| 02 | `02-enrolar-totp-primer-login.jpg` | Primer login: Keycloak obliga a configurar el autenticador |
| 03 | `03-nextcloud-tras-enrolar-totp.jpg` | Nextcloud tras enrolar |
| 04 | `04-segunda-pantalla-pide-codigo-totp.jpg` | Login posterior: usuario/clave aceptados, **segunda pantalla pide el código TOTP** |
| 05 | `05-acceso-concedido-nextcloud.jpg` | Código correcto: acceso concedido a Nextcloud |
| 06 | `06-element-sin-reautenticar.jpg` | Mismo usuario entra a Element sin credenciales ni código nuevos |
| 07 | `07-menu-unificado-nextcloud.jpg` | Menú unificado de Nextcloud (Telefonía, Videoconferencia, Chat, Asistente IA…) |
| 08 | `08-telefonia-sso-sin-reautenticar.jpg` | Telefonía WebRTC abre como "ana Prueba" con extensión SIP registrada |

## Límites reales
- Certificado autofirmado; Element avisa que no puede cargar el service worker por eso.
- Los códigos TOTP se generaron con script, no con una app móvil.
- Para que Synapse alcance el issuer `https://127.0.0.1:8443` desde su contenedor se
  usó un puente `socat` solo de prueba (con una IP de LAN real no hace falta).
- Solo se verificó SSO sin reautenticación hacia Nextcloud, Element y Telefonía;
  Videoconferencia, Grafana y Asistente IA no se abrieron en esta prueba.
- Capturas 02 muestra el QR/clave de una cuenta de prueba en un volumen desechable.

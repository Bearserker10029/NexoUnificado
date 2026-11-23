# H5 – Edición simultánea (Nextcloud Office + Collabora Online)

**Estado: edición en tiempo real demostrada entre dos sesiones del MISMO usuario.
Edición entre dos cuentas distintas: PENDIENTE de verificar (ver límites).**

## Qué ya existía y se verificó (no se duplicó nada)
- Servicio `collabora` (collabora/code) en `docker-compose.yml`, sin puertos publicados.
- Rutas `/browser`, `/hosting/*`, `/cool/*` en `nginx/conf.d/default.conf` hacia
  `collabora:9980` y listener interno `8082` para las llamadas WOPI.
- Conector `richdocuments` instalado y configurado por `nextcloud/collabora-setup.sh`
  (servicio `collabora-init`). Config activa en `configuracion-collabora-tls.txt`.
- Collabora llega al navegador solo por Nginx con TLS (`https://…:8443/hosting/discovery`
  responde 200 y las URLs anunciadas son `https://127.0.0.1:8443/browser/…`).

## Prueba
1. Se abre `Documents/Welcome to Nextcloud Hub.docx` como `ana.prueba` (sesión 1), captura 01.
2. Se crea un enlace público con permiso de edición y se abre en una segunda pestaña
   del navegador (sesión 2).
3. La sesión 2 escribe una frase; aparece en la sesión 1 sin recargar (captura 02, el
   contador pasa de 209 a 215 palabras y se ve el cursor del otro editor).
4. La sesión 1 escribe otra frase; aparece en la sesión 2 (captura 03, 225 palabras).
5. Se cierran los editores y se descarga el `.docx` del servidor: contiene ambas frases
   (guardado correcto).

## Archivos
| Archivo | Contenido |
|---------|-----------|
| `01-ana-abre-documento-en-collabora.jpg` | Documento abierto en modo "Editando" |
| `02-cambio-de-sesion-2-visto-en-sesion-1.jpg` | Frase de la sesión 2 visible en la sesión 1 |
| `03-cambio-de-sesion-1-visto-en-sesion-2.jpg` | Frase de la sesión 1 visible en la sesión 2 |
| `04-sesion-1-contador-225-palabras.jpg` | Sesión 1 con 225 palabras y ambas frases |
| `sesiones-wopi.txt` | Tabla `oc_richdocuments_wopi`: identidad de cada sesión de edición |
| `configuracion-collabora-tls.txt` | Discovery por TLS, puertos y configuración de richdocuments |

## Límites reales
- **No son dos usuarios distintos.** Ambas pestañas compartían cookies, así que el
  enlace público se abrió con la sesión de `ana.prueba`; `sesiones-wopi.txt` lo confirma
  (`editor_uid` idéntico, sin invitado). Es edición simultánea real contra el mismo
  documento (dos sesiones de Collabora), no una prueba entre cuentas diferentes.
- Intento de invitado real: abrir el enlace desde `https://localhost:8443` (otro jar de
  cookies) pide nombre de invitado pero Collabora no carga: su CSP solo permite
  incrustarse desde `https://127.0.0.1:8443` (`net.frame_ancestors`). No se cambió la
  configuración del repo para forzarlo.
- Para cerrar el pendiente: abrir un segundo navegador o perfil, entrar a
  `https://127.0.0.1:8443/` como `beto.prueba` (usuario creado por
  `scripts/h7-configurar-totp.sh`, pide enrolar TOTP), compartirle el documento con
  permiso de edición y repetir los pasos 3-4.
- Rendimiento: no se midió. La carga del editor tardó unos segundos en un equipo de
  desarrollo con el panel del navegador a tamaño reducido; con más usuarios o
  documentos grandes no se probó.
- Certificado autofirmado; el service worker de Element/Nextcloud no se registra por eso.
- Se usó el documento de ejemplo de Nextcloud; el contenido de prueba insertado
  queda en la cuenta de prueba de un volumen desechable.

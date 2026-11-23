# H14 – Antivirus (ClamAV + Nextcloud "Antivirus for files")

Configuración repetible: `scripts/h14-configurar-antivirus.sh` (modo `daemon`,
host `clamav`, puerto `3310`, acción ante infectado: `delete`).

## Prueba
1. Se sube un archivo limpio (`limpio.txt`) → HTTP 201, queda guardado.
2. Se sube el archivo de prueba EICAR (`eicar.com.txt`, 68 bytes, cadena estándar
   inofensiva) por WebDAV → **HTTP 415**, "Virus Eicar-Test-Signature is detected…
   Upload cannot be completed". El archivo no queda en el almacenamiento.
3. Se repite como usuario final `ana.prueba` desde la interfaz web → mismo bloqueo.

## Archivos
| Archivo | Contenido |
|---------|-----------|
| `eicar.com.txt` | Archivo de prueba EICAR usado |
| `limpio.txt` | Archivo de contraste |
| `subida-webdav.txt` | Respuestas HTTP de ambas subidas y listado posterior |
| `log-clamav-deteccion.txt` | `instream(...): Eicar-Test-Signature FOUND` en ClamAV |
| `log-nextcloud-deteccion.txt` | Eventos `files_antivirus` ("Infected file deleted") y rechazo en Nextcloud (usuario admin anonimizado) |
| `captura-subida-eicar-bloqueada.jpg` | Subida de EICAR como `ana.prueba` rechazada |

## Límites reales
- El recuadro rojo de la captura lo inyectó un script de prueba en la página para
  mostrar la respuesta; el texto es el mensaje real devuelto por Nextcloud (HTTP 415).
  La subida se hizo con `fetch` (PUT WebDAV) desde la sesión del usuario, no arrastrando
  un archivo con el selector de archivos.
- La subida 1 y 2 con `curl` usan la cuenta local de administración, no un usuario SSO.
- Solo se probó EICAR; no se midió rendimiento con archivos grandes ni el escaneo
  masivo en segundo plano (`occ files_antivirus:scan` no se ejecutó).
- Si ClamAV no está disponible, el comportamiento de Nextcloud (rechazar o permitir)
  no se probó.

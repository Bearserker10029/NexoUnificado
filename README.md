# Nexo Unificado · Entorno base y VoIP (H2 + H3)

Entorno Docker Compose con Nginx como proxy TLS, portal estático, Prometheus,
Grafana y Blackbox. H3 añade **Asterisk 20.21.0**, dos extensiones SIP con
TLS + SDES-SRTP y un cliente WebRTC basado en Tryit-JsSIP.

## Requisitos

- Docker Desktop con WSL2.
- PhonerLite 3.46 para las pruebas SIP del laboratorio.
- Wireshark/TShark para las evidencias.
- Puertos libres: 8081, 8443, 5061/TCP y 20000–20199/UDP.

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

Servicios:

- Portal: <https://localhost:8443>
- Grafana: <https://localhost:8443/grafana/> (usuario `admin`; clave en `.env`).
- Cliente WebRTC: <https://localhost:8443/voip/>
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

## Estructura y apagado

- `docker-compose.yml`: servicios y redes `pub`, `srv`, `mgmt`.
- `nginx/`, `portal/`: proxy TLS y portal.
- `asterisk/`, `voip/`: VoIP SIP y WebRTC de H3.
- `prometheus/`, `blackbox/`, `grafana/`: monitoreo para el SLA.
- `firewall/nexo.nft`: reglas para el servidor Ubuntu del V305.

```powershell
docker compose down
# Solo si también se desean borrar los volúmenes persistentes:
docker compose down -v
```

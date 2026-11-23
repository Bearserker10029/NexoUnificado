# Informe de hacking ético · SIPVicious contra la central Asterisk de Nexo_Unificado

- **Fecha de ejecución:** 2026-11-23 (hora local -05:00, ver `escucha-asterisk.txt` y `sipvicious-salida.txt`).
- **Autorización:** auditoría autorizada por el equipo del proyecto (TEL139 PUCP) contra el **propio sistema**; la ejecución fue solicitada por quien cierra el hito H15 / pruebas de hacking ético. *(Pendiente: nombre/firma o acta del equipo si la rúbrica lo exige.)*
- **Entorno:** local de desarrollo (Docker Desktop), servicio `asterisk` del compose en la red `nexo_srv` (172.22.0.2).
- **Herramienta:** contenedor temporal `kalilinux/kali-rolling` en la red `nexo_srv`, paquete `sipvicious 0.3.3-2.1` (los comandos del paquete se llaman `svmap` y `svwar`, equivalentes a `sipvicious_svmap` / `sipvicious_svwar`).

## Resultados
| Herramienta | Comando | Resultado |
|---|---|---|
| svmap | `svmap 172.22.0.2 -p 5060` | `found nothing` |
| svwar | `svwar -e100-120 -m INVITE 172.22.0.2 -p 5060` | `socket error: timed out` / `found nothing` |

**No se encontraron extensiones ni servidor SIP.** Es el resultado esperado: Asterisk **no escucha SIP/UDP en 5060**. Sockets en escucha (`escucha-asterisk.txt`): TCP 5061 (SIP/TLS), TCP 8088 (WebSocket interno, expuesto solo como WSS por Nginx en 8443) y puertos UDP efímeros de medios; no existe 5060.

## Limitación (declarada textualmente)
**SIPVicious no audita TLS ni WSS.** Solo habla SIP sobre UDP/TCP en claro; por tanto esta prueba demuestra que la superficie SIP en claro no existe, pero **no** evalúa la robustez del canal TLS 5061 ni del WSS. Para eso se requieren otras herramientas (p. ej. `sslscan`/`testssl.sh`, o un cliente SIP/TLS), fuera del alcance de este informe. No se habilitó 5060/UDP para obtener un hallazgo, pues debilitaría justamente la defensa que se demuestra.

## Vínculo con las defensas aplicadas
- **TLS (5061) y WSS:** la señalización solo viaja cifrada; no hay SIP/UDP que enumerar.
- **SRTP:** los medios van cifrados (RTP en 20000-20199/udp).
- **Segmentación:** Asterisk vive en `nexo_srv`, sin publicar 5060; en H13 (diseño, avance parcial) VLAN 20 solo alcanza 5061 y RTP.
- **Denegación por defecto:** `firewall/nexo.nft` (policy drop) y el diseño OPNsense (deny by default) no abren 5060/UDP.

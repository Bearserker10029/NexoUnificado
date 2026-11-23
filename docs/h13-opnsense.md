# H13 · Segmentación con OPNsense (VLAN + firewall + WireGuard)

> **Estado: AVANCE PARCIAL (diseño, reglas y scripts de prueba listos; VM no desplegada).**
> La VM de OPNsense no se ha instalado ni probado en este laboratorio, por lo que no hay
> evidencias de reglas aplicadas ni de pruebas permitidas/denegadas. H13 **no se declara
> completado**. Ver "Pendiente" al final. La segmentación con redes Docker
> (`nexo_pub`, `nexo_srv`, `nexo_mgmt`) y `firewall/nexo.nft` es una capa adicional, no sustituye este hito.

## 1. Topología

VM OPNsense con dos interfaces: **WAN** (adaptador puente/NAT hacia el laboratorio) y **LAN** (troncal 802.1Q con las VLAN).

| VLAN | Nombre    | Subred           | Gateway (OPNsense) | Notas                          |
|------|-----------|------------------|--------------------|--------------------------------|
| 10   | Usuarios  | 192.168.10.0/24  | 192.168.10.1       | DHCP                           |
| 20   | Voz       | 192.168.20.0/24  | 192.168.20.1       | Teléfonos/softphones           |
| 30   | Servidores| 192.168.30.0/24  | 192.168.30.1       | Servidor Docker: **192.168.30.10** (estática) |
| 99   | Gestión   | 192.168.99.0/24  | 192.168.99.1       | Administración                 |
| —    | WireGuard | 10.99.0.0/24     | 10.99.0.1          | Cliente de gestión: 10.99.0.2  |

Servidor Docker (Ubuntu): `192.168.30.10/24`, gateway `192.168.30.1`, en la VLAN 30. Puertos publicados por Nexo: **8443/tcp** (proxy HTTPS), **8081/tcp** (healthz HTTP), **5061/tcp** (SIP/TLS), **20000-20199/udp** (RTP/SRTP), **22/tcp** (SSH). **5060/UDP nunca se abre.**

## 2. Reglas de firewall (deny by default)

OPNsense deniega por defecto en toda interfaz sin reglas. Se agrega además una regla explícita final de bloqueo con log por interfaz. Orden de evaluación: arriba → abajo, primer acierto gana.

| # | Interfaz | Acción | Proto | Origen | Destino | Puerto | Descripción |
|---|----------|--------|-------|--------|---------|--------|-------------|
| 1 | VLAN10 | Pass  | TCP | VLAN10 net | 192.168.30.10 | 8443 | Usuarios → HTTPS del proxy |
| 2 | VLAN10 | Pass  | UDP/TCP | VLAN10 net | 192.168.10.1 | 53 | DNS (opcional) |
| 3 | VLAN10 | Block (log) | any | any | RFC1918 (alias) | any | Sin acceso a otras VLAN |
| 4 | VLAN10 | Pass  | any | VLAN10 net | any | any | Salida a Internet (NAT) |
| 5 | VLAN20 | Pass  | TCP | VLAN20 net | 192.168.30.10 | 5061 | Voz → SIP/TLS |
| 6 | VLAN20 | Pass  | UDP | VLAN20 net | 192.168.30.10 | 20000-20199 | Voz → RTP/SRTP |
| 7 | VLAN20 | Block (log) | any | any | any | any | Resto denegado |
| 8 | VLAN99 | Pass  | TCP | VLAN99 net | 192.168.30.10 | 22 | Gestión → SSH |
| 9 | VLAN99 | Pass  | TCP | VLAN99 net | 192.168.30.10 | 8443 | Gestión → HTTPS |
| 10 | VLAN99 | Block (log) | any | any | any | any | Resto denegado |
| 11 | VLAN30 | Pass  | any | 192.168.30.10 | !RFC1918 | any | Servidor sale a Internet (actualizaciones) |
| 12 | VLAN30 | Block (log) | any | any | RFC1918 (alias) | any | Servidor no inicia hacia otras VLAN |
| 13 | WAN | Block (log) | any | any | any | any | Default; sin port-forward de SIP |
| 14 | WAN | Pass | UDP | any | WAN address | 51820 | WireGuard |
| 15 | WireGuard | Pass | TCP | 10.99.0.2 | 192.168.30.10 | 22, 8443 | VPN → solo gestión |
| 16 | WireGuard | Pass | TCP | 10.99.0.2 | 192.168.99.0/24 | 22, 443 | VPN → administración OPNsense/hosts de gestión |
| 17 | WireGuard | Block (log) | any | any | any | any | Resto denegado |

Alias `RFC1918 = 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16`. El tráfico de retorno lo cubre el estado (stateful), no se necesitan reglas inversas.

## 3. NAT

Firewall → NAT → Outbound: **modo automático**. Las redes internas salen por WAN con enmascaramiento. **No se crean reglas de NAT de entrada (port-forward)**: SIP/RTP no se publican hacia Internet.

## 4. WireGuard

- Instancia en OPNsense: UDP **51820**, túnel `10.99.0.1/24`.
- Peer de gestión: `10.99.0.2/32`. `AllowedIPs` en el servidor: `10.99.0.2/32`; en el cliente: `192.168.30.10/32, 192.168.99.0/24`.
- Plantilla del cliente: [`firewall/opnsense/wg-cliente.conf.example`](../firewall/opnsense/wg-cliente.conf.example) con **claves de ejemplo**. Las claves reales jamás se versionan (`.gitignore` bloquea `wg*.conf` sin `.example`, `*.key`).
- Evidencia esperada: `wg show` con `latest handshake` y ping/HTTPS a 192.168.30.10:8443; fallo hacia VLAN10/20.

## 5. Matriz de pruebas esperadas

Script: [`scripts/h13-pruebas.sh`](../scripts/h13-pruebas.sh) (se ejecuta desde un host en cada VLAN; guarda salida en `evidencias/h13/`).

| Origen | Prueba | Resultado esperado |
|--------|--------|--------------------|
| VLAN10 | `curl -k https://192.168.30.10:8443/healthz` | `ok` (HTTP 200) |
| VLAN10 | `ssh 192.168.30.10` | Falla (timeout) |
| VLAN10 | 5061 / RTP | Falla |
| VLAN20 | TCP 5061 | Abre |
| VLAN20 | TCP 8443 / 22 | Falla |
| VLAN99 | TCP 22 y 8443 | Abre |
| VLAN99 | TCP 5061 | Falla |
| WireGuard | handshake + 8443 y 22 | OK |
| WireGuard | VLAN10/20 | Falla |
| Cualquiera | UDP 5060 | Cerrado (nunca publicado) |

> Nota: `/healthz` también responde por TLS en 8443 (bloque HTTPS de `default.conf`), de modo que la prueba permitida de VLAN 10 y el monitoreo viajan cifrados y cuadran con la regla 1. El `/healthz` HTTP del puerto 80 (publicado en 8081) se mantiene para el healthcheck interno de Docker.

## 6. Pendiente (impedimento y plan)

- [ ] Instalar OPNsense en VM (2 NIC), crear VLAN 10/20/30/99, aplicar reglas 1-17 y WireGuard.
- [ ] Mover el servidor Ubuntu a VLAN 30 con IP 192.168.30.10 (netplan) y ajustar `firewall/nexo.nft` si cambia la gestión.
- [ ] Ejecutar `scripts/h13-pruebas.sh` y capturar pantallas de cada regla en `evidencias/h13/`.

Impedimento actual: el trabajo de esta rama se realizó sin acceso a la VM/hipervisor del laboratorio, por lo que no existen capturas. Se documenta sin declarar el hito cerrado.

# H12 — Aprovisionamiento con Ansible

## Alcance

Los playbooks describen el estado deseado de la pila completa, incluidos el modo
multiempresa y fail2ban. No instalan Docker ni modifican el SSH del host: comprueban
que el daemon y Compose respondan, crean los directorios, generan los secretos una
sola vez, despliegan y verifican los servicios.

El despliegue reutiliza la raíz del checkout y cualquier `.env` existente. Si no hay
`.env`, genera secretos locales en `ansible/.secrets` y crea uno con modo `0600`;
ambos están ignorados y no deben copiarse a evidencias. Un `nexo_dir` alternativo
recibe una copia de la configuración sin secretos.

## Playbooks

- `ansible/prepare.yml`: comprueba Docker, Compose y permisos sobre el daemon; crea
  los directorios de ejecución y secretos.
- `ansible/deploy.yml`: incluye la preparación, copia los archivos necesarios, genera
  o conserva `.env`, valida los tres archivos Compose y levanta la pila.
- `ansible/verify.yml`: comprueba HTTP/HTTPS, Keycloak, Element, Jitsi, Nextcloud,
  telefonía y Grafana, además de los servicios base y multiempresa en ejecución.
- `ansible/site.yml`: entrada principal; ejecuta `deploy.yml` y `verify.yml`.

## Ejecución local

Requisitos: Linux o WSL2, Python 3, Ansible Core 2.16 o posterior, Docker con Compose
y permisos para usar el socket. En Windows, habilita la integración de Docker Desktop
con WSL o expón los comandos `docker` y `docker compose` dentro de WSL.

Desde la raíz del repositorio:

```bash
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
ansible-playbook ansible/prepare.yml
ansible-playbook ansible/site.yml
```

En una instalación existente cuyo `NEXO_HOST` no cambió, puedes conservar intacta la
configuración OIDC persistida con `-e skip_host_update=true`. No uses esta opción tras
cambiar el host ni en el primer aprovisionamiento del laboratorio.

Para repetir automáticamente la evidencia de idempotencia:

```bash
ANSIBLE_PLAYBOOK=ansible-playbook scripts/h12-idempotencia.sh
```

La segunda corrida debe terminar con `changed=0`. Las comprobaciones `command`, `uri`,
`debug` y `assert` no representan cambios de configuración.

## Servidor Linux del laboratorio

Usa un inventario propio, no versionado, con un host de documentación como referencia:

```ini
[nexo]
servidor-ejemplo ansible_host=192.0.2.20 ansible_user=USUARIO
```

`192.0.2.20` pertenece a TEST-NET-1 y debe reemplazarse localmente, nunca guardarse
como una IP real. El usuario necesita Docker ya instalado y permisos para operarlo.
El mismo comando sirve sin editar tareas:

```bash
ansible-playbook -i INVENTARIO_LOCAL ansible/site.yml \
  -e asterisk_public_ip=IP_DEL_SERVIDOR -e nexo_dir=/opt/nexo-unificado
```

No uses `docker compose down -v`: los volúmenes conservan cuentas y datos.

## Evidencias

`evidencias/h12/01-primera-ejecucion.txt` y `02-segunda-ejecucion.txt` contienen las
salidas completas. `resumen.txt` resume los contadores observados y las comprobaciones.

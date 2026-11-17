# Nexo Unificado, guía para correr el proyecto

Esta guía es para cualquier miembro del grupo que necesite levantar la plataforma en su máquina. Todo corre con un solo `docker compose up -d` desde la raíz del proyecto. No hay scripts adicionales.

## 1. Requisitos

- Docker Desktop para Windows con el motor WSL2 activo.
- Los puertos libres en tu equipo: 8443, 8444, 8000, 8008, 8090 en TCP y 10000 en UDP.
- Estar dentro de la carpeta raíz del proyecto, donde está el `docker-compose.yml` unificado.

## 2. Configurar el .env

Crea el archivo `.env` en la raíz tomando como referencia el siguiente bloque. La IP que aparece es la de tu máquina en la red, la obtienes con `ipconfig`. En el ejemplo se usa 192.168.1.35, reemplázala por la tuya en todas las variables.

```
HOST_IP=192.168.1.35
NEXO_URL=https://192.168.1.35:8443
ASTERISK_PUBLIC_IP=192.168.1.35
DOCKER_HOST_ADDRESS=192.168.1.35
PUBLIC_URL=https://192.168.1.35:8444
JICOFO_AUTH_PASSWORD=pon_aqui_una_clave_larga_aleatoria
JICOFO_COMPONENT_SECRET=pon_aqui_otra_clave_larga_aleatoria
JVB_AUTH_PASSWORD=pon_aqui_otra_clave_larga_aleatoria
```

Advertencias importantes sobre este archivo.

- No repitas nombres de variables. Docker Compose toma la última ocurrencia y un duplicado con un valor de ejemplo genera config apuntando al host equivocado. Este error es silencioso y costó horas de diagnóstico.
- Si solo vas a probar desde tu propio equipo, puedes dejar todo con `127.0.0.1` y `localhost`, la plataforma funciona igual.
- Si tu router cambia tu IP al reiniciar, reserva la IP de tu tarjeta de red en el router y así el `.env` queda fijo para siempre.

## 3. Levantar la plataforma

```
docker compose up -d
```

La primera vez descarga todas las imágenes y puede tardar varios minutos. En ese primer arranque el servicio `nexo-synapse-init` genera la configuración inicial de Synapse de forma automática y sale con código cero. En los arranques siguientes detecta que la config ya existe y no toca nada.

Verifica que todo esté bien con:

```
docker compose ps
```

Debes ver doce contenedores activos. Los contenedores `nexo-certs` y `nexo-synapse-init` aparecen como `Exited`, que es su estado normal porque son tareas de una sola ejecución.

## 4. Firewall de Windows

Para que otros equipos de la red entren, crea estas reglas una sola vez en PowerShell como administrador.

```
netsh advfirewall firewall add rule name="Nexo Jitsi" dir=in action=allow protocol=TCP localport=8444 profile=any
netsh advfirewall firewall add rule name="Nexo Portal" dir=in action=allow protocol=TCP localport=8443 profile=any
netsh advfirewall firewall add rule name="Nexo Matrix" dir=in action=allow protocol=TCP localport=8008,8090 profile=any
netsh advfirewall firewall add rule name="Nexo JVB" dir=in action=allow protocol=UDP localport=10000 profile=any
```

El `profile=any` importa. Si tu red está marcada como pública, las reglas sin ese perfil no aplican y el síntoma es un `ERR_CONNECTION_CLOSED` al entrar desde otros equipos.

## 5. Crear usuarios de Matrix

Synapse viene con el registro cerrado, así que las cuentas se crean por línea de comandos. Un comando por usuario, con la clave que prefieras.

```
docker exec nexo-synapse register_new_matrix_user -c /data/homeserver.yaml -u ana -p CLAVE_ANA --no-admin http://localhost:8008
docker exec nexo-synapse register_new_matrix_user -c /data/homeserver.yaml -u beto -p CLAVE_BETO --no-admin http://localhost:8008
docker exec nexo-synapse register_new_matrix_user -c /data/homeserver.yaml -u carla -p CLAVE_CARLA --no-admin http://localhost:8008
```

Anota las claves en un `usuarios.txt` dentro de `matrix` para no perderlas, y no subas ese archivo al repositorio.

Si durante una sesión de pruebas quieres que cada quien se cree su cuenta desde Element, habilita el registro temporal así y reinicia Synapse.

```
docker exec nexo-synapse sed -i 's/enable_registration: false/enable_registration: true/' /data/homeserver.yaml
docker restart nexo-synapse
```

Con eso la pantalla de Element muestra la opción de crear cuenta. Vuelve a poner el valor en `false` cuando terminen las pruebas, porque con el registro abierto cualquiera en la red puede entrar.

## 6. Probar la plataforma

Desde tu propio navegador, con localhost o con tu IP.

- Portal y Grafana en `https://192.168.1.35:8443`, Grafana en la ruta `/grafana/`.
- Jitsi en `https://192.168.1.35:8444/SoporteNexo`. Solo pide un nombre para mostrar, no tiene usuarios. Acepta el aviso del certificado autofirmado.
- Element en `http://192.168.1.35:8090`. Entra con el id completo, por ejemplo `@ana:nexo.local`, más su clave.

Desde el celular u otro equipo en el mismo Wi-Fi, las mismas URLs. El audio y video de Jitsi entre varios dispositivos confirma que el puerto UDP 10000 está libre.

Si cambiaste el `element-config.json` para apuntar a otra IP, recuerda que el navegador de cada cliente usa esa URL tal cual, y recarga con Ctrl+F5 para descartar la config cacheada.

## 7. Problemas conocidos y su causa

Estos son los errores que ya nos costaron trabajo, para que no los repitan.

- `not found` al descargar `matrixdotorg/synapse:1.165.0` o `vectorim/element-web:1.12.35`. Esos tags no existen en Docker Hub. El compose usa `latest` y la versión exacta se lee del contenedor para el inventario de licencias.
- Los contenedores de Jitsi reinician con el root de solo lectura. Causa, tenían `no-new-privileges:true`. Esas imágenes usan s6-overlay y lo exigen fuera. El resto de la plataforma sí lo mantiene.
- `FATAL ERROR: Jicofo auth password must be set` en prosody. Causa, faltaban las variables JICOFO y JVB en el environment de prosody, no solo en jicofo y jvb.
- `ERR_CONNECTION_CLOSED` al entrar al 8444. Causas conocidas, reglas del firewall sin `profile=any`, o el mapeo de puertos apuntando a puertos internos distintos de los que la imagen realmente escucha.
- Sala de Jitsi abierta pero con el aviso de desconectado. Causa típica, el navegador tiene cacheado un `config.js` viejo. Recarga con Ctrl+F5. Si persiste, revisa que la URL de señalización en `/run/web/config/config.js` dentro del contenedor apunte a tu IP.
- No montar volúmenes sobre `/config` en los contenedores de Jitsi. En Docker Desktop de Windows el montaje interfiere con la generación interna de la config, la cual se reconstruye en cada arranque desde las variables de entorno y no necesita volúmenes.

## 8. Apagar y limpiar

```
docker compose down
```

Esto detiene todo pero conserva los datos en los volúmenes, usuarios de Matrix, certificados y config de Synapse. Si necesitas empezar de cero el chat, además borra el volumen con `docker volume rm nexo_synapse_data` y el init lo regenerará en el próximo arranque.

## 9. Notas para el inventario de licencias

Las imágenes y versiones que usa este compose son las mismas que documenta el anexo B del SLA. Synapse y Element usan el tag `latest` porque los tags fijos no existen en Docker Hub, y su versión exacta se verifica dentro del contenedor. El resto de imágenes van con versión fija, igual que en el anexo.

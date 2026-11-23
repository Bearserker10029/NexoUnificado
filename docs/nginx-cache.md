# Caché de estáticos en Nginx (optimización de borde)

- `proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=nexo:10m inactive=60m;` en el contexto `http` (`nginx/conf.d/default.conf`).
- Activa en `/element/` y `/jitsi/` (`proxy_cache nexo`, 200/302 → 10 min, 404 → 1 min) con cabecera `X-Cache-Status` para verificarla.
- **Sin caché** en `/_matrix/`, `/_synapse/` ni `/voip/`: ahí hay sesiones, SSO y datos dinámicos; cachear rompería el login.
- Nginx respeta `Cache-Control` del upstream: el `index.html` de Element (`no-cache`) siempre da MISS; los bundles estáticos dan HIT (`evidencias/nginx-cache/prueba-stack-real.txt`).
- **Justificación:** demostración de optimización de borde y caché de estáticos, **no** una ganancia de latencia medible: con un solo servidor y red local la mejora no es medible y no se pretende que lo sea.
- También se agregó `/healthz` por TLS (8443) para monitoreo cifrado y para la regla de VLAN 10 de H13.

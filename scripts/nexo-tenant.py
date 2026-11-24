#!/usr/bin/env python3
"""Aprovisionamiento declarativo de empresas para Nexo Unificado.

No modifica docker-compose.yml ni la configuracion tradicional. Genera el override
Compose automatico, su copia de compatibilidad y archivos por empresa desde
tenants/registry.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TENANTS = ROOT / "tenants"
REGISTRY = TENANTS / "registry.json"
SERVICES = {"chat", "telefonia", "videoconferencia"}
AI_PROVIDERS = ("gemini", "ollama")


def load_registry() -> dict:
    if not REGISTRY.exists():
        return {"version": 1, "tenants": []}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def save_registry(registry: dict) -> None:
    TENANTS.mkdir(exist_ok=True)
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_name(value: str) -> str:
    name = value.lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,30}", name):
        raise ValueError("El nombre debe tener 2-31 caracteres: letra inicial, minusculas, numeros o guion")
    return name


def tenant_services(tenant: dict) -> set[str]:
    return set(tenant.get("services", sorted(SERVICES)))


def add_tenant(args: argparse.Namespace) -> None:
    name = validate_name(args.name)
    if not 1 <= args.range_prefix <= 9:
        raise ValueError("range-prefix debe estar entre 1 y 9")
    services = sorted(set(args.services.split(",")))
    unknown = set(services) - SERVICES
    if unknown:
        raise ValueError(f"Servicios desconocidos: {', '.join(sorted(unknown))}")
    registry = load_registry()
    tenants = registry["tenants"]
    if any(t["name"] == name for t in tenants):
        raise ValueError(f"La empresa {name} ya existe; use render para regenerar o update en registry.json")
    if any(int(t["range_prefix"]) == args.range_prefix for t in tenants):
        raise ValueError(f"El prefijo {args.range_prefix} ya esta asignado")
    tenants.append({"name": name, "display_name": args.display_name or args.name.upper(),
                    "range_prefix": args.range_prefix, "services": services})
    if args.ai_provider:
        tenants[-1]["ai_provider"] = args.ai_provider
    tenants.sort(key=lambda t: t["name"])
    save_registry(registry)
    render(registry)
    print(f"Empresa {name} aprovisionada: extensiones {args.range_prefix}000-{args.range_prefix}999.")
    print("Defina sus secretos SIP en .env y ejecute docker compose up -d --build.")


def tenant_sectors(tenant: dict) -> list[dict]:
    """Valida y normaliza los sectores opcionales de una empresa."""
    prefix = int(tenant["range_prefix"])
    low, high = prefix * 1000, prefix * 1000 + 999
    sectors, names, used = [], set(), []
    for raw in tenant.get("sectors", []):
        name = str(raw.get("name", "")).lower()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", name) or name in names:
            raise ValueError(f"Sector invalido o duplicado en {tenant['name']}: {raw.get('name')!r}")
        names.add(name)
        match = re.fullmatch(r"(\d{4})-(\d{4})", str(raw.get("range", "")))
        if not match:
            raise ValueError(f"Sector {name}: range debe tener formato 'NNNN-NNNN'")
        start, end = int(match.group(1)), int(match.group(2))
        if not low <= start <= end <= high:
            raise ValueError(f"Sector {name}: el subrango debe quedar dentro de {low}-{high}")
        if any(start <= u_end and u_start <= end for u_start, u_end in used):
            raise ValueError(f"Sector {name}: el subrango se solapa con otro sector")
        used.append((start, end))
        allow = raw.get("allow_intercompany", False)
        if not isinstance(allow, bool):
            raise ValueError(f"Sector {name}: allow_intercompany debe ser booleano")
        sectors.append({"name": name, "start": start, "end": end, "allow": allow})
    return sectors


def intercompany_class_of_service(sectors: list[dict]) -> str:
    """Lineas de dialplan que aplican la clase de servicio interempresas.

    Sin sectores se conserva el comportamiento tradicional (todas las extensiones pueden marcar 9).
    """
    if not sectors:
        return ""
    lines = [" same => n,Set(CALLER_NUM=${FILTER(0-9,${CALLERID(num)})})",
             " same => n,GotoIf($[\"${CALLER_NUM}\" = \"\"]?sector-denegado)"]
    for sector in sectors:
        if sector["allow"]:
            lines.append(f" same => n,GotoIf($[${{CALLER_NUM}} >= {sector['start']} & ${{CALLER_NUM}} <= {sector['end']}]"
                         f"?sector-permitido)")
    lines.append(" same => n,Goto(sector-denegado)")
    lines.append(" same => n(sector-permitido),NoOp(Sector con allow_intercompany)")
    return "\n".join(lines) + "\n"


def sector_denied_block(sectors: list[dict]) -> str:
    if not sectors:
        return ""
    return (" same => n(sector-denegado),Log(WARNING,Interempresas denegada por clase de servicio: "
            "${CALLERID(num)} -> ${EXTEN})\n same => n,Playback(invalid)\n same => n,Hangup(21)\n")


def render_asterisk(tenant: dict) -> None:
    name = tenant["name"]
    prefix = int(tenant["range_prefix"])
    target = TENANTS / name / "asterisk"
    target.mkdir(parents=True, exist_ok=True)
    sectors = tenant_sectors(tenant)
    cos = intercompany_class_of_service(sectors)
    cos_denied = sector_denied_block(sectors)
    (target / "extensions.conf").write_text(f"""; Generado por scripts/nexo-tenant.py. No editar a mano.
[tenant-{name}]
exten => _{prefix}XXX,1,Log(NOTICE,Llamada interna de {name} reservada a Element: ${{EXTEN}})
 same => n,Hangup(21)

; 9 + extension destino. La validacion impide usar esta ruta dentro de la misma empresa.
exten => _9ZXXX,1,Set(TENANT_ORIGEN={name})
 same => n,Set(TENANT_PREFIJO={prefix})
 same => n,GotoIf($[\"${{EXTEN:1:1}}\" = \"${{TENANT_PREFIJO}}\"]?misma-empresa)
 same => n,GotoIf($["${{PJSIP_ENDPOINT(${{EXTEN:1}},context):0:7}}" != "tenant-"]?destino-denegado)
{cos} same => n,Set(CHANNEL(accountcode)={name})
 same => n,Set(CDR(userfield)=origen=${{CALLERID(num)}},destino=${{EXTEN:1}},tipo=interempresas)
 same => n,Set(CDR(tenant_origen)={name})
 same => n,Set(CDR(origen)=${{CALLERID(num)}})
 same => n,Set(CDR(destino)=${{EXTEN:1}})
 same => n,Set(CDR(tipo)=interempresas)
 same => n,Log(NOTICE,INTEREMPRESA origen={name}/${{CALLERID(num)}} destino=${{EXTEN:1}})
 same => n,Dial(PJSIP/${{EXTEN:1}},30)
 same => n,Hangup()
 same => n(misma-empresa),Log(WARNING,Ruta interempresas innecesaria denegada: ${{EXTEN}})
 same => n,Playback(invalid)
 same => n,Hangup(21)
 same => n(destino-denegado),Hangup(21)
{cos_denied}
; Denegar por defecto: PSTN y otros rangos no son alcanzables sin el prefijo 9.
exten => _X.,1,Log(WARNING,Destino no autorizado en {name} desde ${{CALLERID(num)}}: ${{EXTEN}})
 same => n,Playback(invalid)
 same => n,Hangup(21)
""", encoding="utf-8")
    # 1001/2001 son extensiones TLS de laboratorio; el gateway usa 1100+/2100+ para WSS.
    extension = prefix * 1000 + 1
    secret = f"TENANT_{name.upper().replace('-', '_')}_SIP_PASSWORD"
    (target / "pjsip.conf.template").write_text(f"""; Generado por scripts/nexo-tenant.py. No editar a mano.
[tenant-{name}-endpoint](!)
type=endpoint
context=tenant-{name}
transport=transport-tls
disallow=all
allow=opus,ulaw,alaw
direct_media=no
rewrite_contact=yes
force_rport=yes
rtp_symmetric=yes
dtmf_mode=rfc4733
media_encryption=sdes

[{extension}](tenant-{name}-endpoint)
auth=auth-{extension}
aors=aor-{extension}
callerid=\"{name.upper()} {extension}\" <{extension}>

[auth-{extension}]
type=auth
auth_type=userpass
username={extension}
password=${{{secret}}}

[aor-{extension}]
type=aor
max_contacts=1
remove_existing=yes
qualify_frequency=0
""", encoding="utf-8")


def render_keycloak(tenant: dict) -> None:
    name = tenant["name"]
    target = TENANTS / name / "keycloak"
    target.mkdir(parents=True, exist_ok=True)
    services = tenant_services(tenant)
    groups = [{"name": f"{name}-servicio-{service}"} for service in sorted(services)]
    groups.append({"name": f"{name}-administradores",
                   "clientRoles": {"realm-management": ["manage-users"]}})
    clients = []
    clients.append({
        "clientId": "nextcloud", "name": f"Nextcloud {name}", "enabled": True,
        "protocol": "openid-connect", "publicClient": False, "secret": "${KC_NEXTCLOUD_CLIENT_SECRET}",
        "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
        "redirectUris": ["${NEXO_URL}/docs/apps/user_oidc/code*"], "webOrigins": ["${NEXO_URL}"],
        "rootUrl": "${NEXO_URL}", "baseUrl": "/docs/",
        "attributes": {"post.logout.redirect.uris": "${NEXO_URL}/docs/*"},
        "protocolMappers": [{"name": "grupos-servicios", "protocol": "openid-connect",
            "protocolMapper": "oidc-group-membership-mapper",
            "config": {"claim.name": "groups", "full.path": "false", "id.token.claim": "true",
                       "access.token.claim": "true", "userinfo.token.claim": "true"}}]
    })
    clients.append({
        "clientId": "nexo-portal", "name": f"Servicios Nexo {name}", "enabled": True,
        "optionalClientScopes": ["offline_access", "microprofile-jwt", "kc-admin-api"],
        "protocol": "openid-connect", "publicClient": False, "secret": "${KC_VOIP_CLIENT_SECRET}",
        "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
        "redirectUris": ["${NEXO_URL}/voip-sso/" + name + "/callback"],
        "webOrigins": ["${NEXO_URL}"], "rootUrl": "${NEXO_URL}/" + name + "/",
        "attributes": {"post.logout.redirect.uris": "${NEXO_URL}/" + name + "/*",
                       "pkce.code.challenge.method": "S256"},
        "protocolMappers": [{"name": "grupos-servicios", "protocol": "openid-connect",
            "protocolMapper": "oidc-group-membership-mapper",
            "config": {"claim.name": "groups", "full.path": "false", "id.token.claim": "true",
                       "access.token.claim": "true", "userinfo.token.claim": "true"}}]
    })
    if "chat" in services:
        clients.append({
            "clientId": "synapse", "name": f"Synapse {name}", "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "secret": "${KC_SYNAPSE_CLIENT_SECRET}",
            "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
            "redirectUris": ["${NEXO_URL}/" + name + "/_synapse/client/oidc/callback"],
            "webOrigins": ["${NEXO_URL}"], "attributes": {"post.logout.redirect.uris": "+"}
        })
    realm = {"realm": f"nexo-{name}", "enabled": True, "displayName": tenant["display_name"],
             "sslRequired": "external", "registrationAllowed": False, "loginWithEmailAllowed": True,
             "groups": groups, "clients": clients}
    (target / "realm.json.template").write_text(json.dumps(realm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_matrix(tenant: dict) -> None:
    name = tenant["name"]
    target = TENANTS / name / "matrix"
    target.mkdir(parents=True, exist_ok=True)
    (target / "homeserver.yaml.template").write_text(f"""# Generado: homeserver exclusivo de {name}.
server_name: \"{name}.nexo.local\"
public_baseurl: \"${{NEXO_URL}}/{name}/\"
report_stats: false
pid_file: /data/homeserver.pid
media_store_path: /data/media_store
signing_key_path: /data/{name}.signing.key
database:
  name: sqlite3
  args:
    database: /data/homeserver.db
listeners:
  - port: 8008
    tls: false
    type: http
    x_forwarded: true
    resources:
      - names: [client, media]
        compress: false
registration_shared_secret: \"${{KC_SYNAPSE_CLIENT_SECRET}}\"
enable_registration: false
enable_registration_without_verification: false
user_directory:
  search_all_users: false
oidc_providers:
  - idp_id: keycloak
    idp_name: \"{tenant['display_name']}\"
    issuer: \"${{NEXO_URL}}/keycloak/realms/nexo-{name}\"
    discover: false
    authorization_endpoint: \"${{NEXO_URL}}/keycloak/realms/nexo-{name}/protocol/openid-connect/auth\"
    token_endpoint: \"${{NEXO_URL}}/keycloak/realms/nexo-{name}/protocol/openid-connect/token\"
    userinfo_endpoint: \"${{NEXO_URL}}/keycloak/realms/nexo-{name}/protocol/openid-connect/userinfo\"
    jwks_uri: \"${{NEXO_URL}}/keycloak/realms/nexo-{name}/protocol/openid-connect/certs\"
    client_id: \"synapse\"
    client_secret: \"${{KC_SYNAPSE_CLIENT_SECRET}}\"
    scopes: [\"openid\", \"profile\", \"email\"]
    user_mapping_provider:
      config:
        localpart_template: \"{{{{ user.preferred_username }}}}\"
        display_name_template: \"{{{{ user.name }}}}\"
sso:
  client_whitelist:
    - \"${{NEXO_URL}}/{name}/element/\"
""", encoding="utf-8")
    element = {
        "default_server_config": {"m.homeserver": {"base_url": "${NEXO_URL}/" + name,
                                                        "server_name": f"{name}.nexo.local"}},
        "brand": f"Nexo · {tenant['display_name']}", "disable_guests": True,
        "disable_custom_urls": True, "force_verification": True,
        "sso_redirect_options": {"immediate": True}, "show_labs_settings": False,
        "features": {"feature_group_calls": False}
    }
    (target / "element-config.json.template").write_text(json.dumps(element, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def auth_block(name: str) -> str:
    return f"""        auth_request /_nexo_tenant_auth_{name};
        error_page 401 = @nexo_tenant_login_{name};
"""


def render_nginx(tenant: dict, provider_id: int) -> None:
    """provider_id: id del proveedor user_oidc de la empresa (keycloak=1, luego una por empresa en orden)."""
    name = tenant["name"]
    services = tenant_services(tenant)
    target = TENANTS / "nginx"
    target.mkdir(parents=True, exist_ok=True)
    parts = [f"""# Generado para {name}; se incluye dentro del servidor HTTPS existente.
    # Sin pagina propia por empresa: todos entran por la pagina unica de acceso.
    location = /{name}/ {{
        return 302 https://$http_host/voip-sso/entrar;
    }}
    location = /_nexo_tenant_auth_{name} {{
        internal;
        proxy_pass http://voip-gateway:5000/authorize;
        proxy_pass_request_body off;
        proxy_set_header Content-Length \"\";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header Cookie $http_cookie;
    }}
    location @nexo_tenant_login_{name} {{
        return 302 https://$http_host/voip-sso/{name}/login?next=$request_uri;
    }}
"""]
    if "chat" in services:
        parts.append(f"""    # Synapse compara la URL solicitada con public_baseurl (.../{name}/) y, al llegar sin
    # el prefijo, redirige en bucle. En este endpoint se conserva el prefijo en el Host.
    location ~ ^/{name}/_matrix/client/(v3|r0|unstable)/login/sso/redirect {{
        rewrite ^/{name}/(.*)$ /$1 break;
        proxy_set_header Host "$http_host/{name}";
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_pass http://synapse-{name}:8008;
    }}
    location /{name}/_matrix/ {{
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        client_max_body_size 50M;
        proxy_pass http://synapse-{name}:8008/_matrix/;
    }}
    location /{name}/_synapse/client/ {{
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_pass http://synapse-{name}:8008/_synapse/client/;
    }}
    location /{name}/element/ {{
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_pass http://element-{name}:80/;
    }}
""")
    if "telefonia" in services:
        parts.append(f"""    location /{name}/voip/ {{
        add_header Content-Security-Policy \"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' wss:; img-src 'self' data:; media-src 'self' blob: data:; frame-ancestors 'self'\" always;
        alias /usr/share/nginx/voip/;
        try_files $uri $uri/ =404;
    }}
    location /{name}/voip-sso/ {{
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_pass http://voip-gateway:5000/;
    }}
""")
    if "videoconferencia" in services:
        auth = auth_block(name)
        parts.append(f"""    location /{name}/jitsi/ {{
{auth}        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Accept-Encoding \"\";
        sub_filter '<base href=\"/\" />' '<base href=\"/{name}/jitsi/\" />';
        sub_filter_once on;
        proxy_pass http://jitsi-web-{name}:8000/;
    }}
    location /{name}/jitsi/http-bind {{
{auth}        proxy_http_version 1.1;
        proxy_set_header Connection \"\";
        proxy_set_header Host $http_host;
        proxy_pass http://jitsi-web-{name}:8000/http-bind;
    }}
    location /{name}/jitsi/xmpp-websocket {{
{auth}        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $http_host;
        proxy_pass http://jitsi-web-{name}:8000/xmpp-websocket;
    }}
""")
    (target / f"tenant-{name}.conf").write_text("".join(parts), encoding="utf-8")


def jitsi_services(name: str, index: int) -> str:
    port = 10001 + index
    domain = f"{name}.meet.jitsi"
    common = f"""      PUBLIC_URL: https://${{NEXO_HOST:-localhost}}:8443/{name}/jitsi
      XMPP_SERVER: jitsi-prosody-{name}
      XMPP_DOMAIN: {domain}
      XMPP_MUC_DOMAIN: muc.{domain}
      XMPP_INTERNAL_MUC_DOMAIN: internal-muc.{domain}
      XMPP_HIDDEN_DOMAIN: hidden.{domain}
      TZ: America/Lima
"""
    return f"""  jitsi-web-{name}:
    image: ghcr.io/jitsi/web:stable-11509
    container_name: nexo-jitsi-web-{name}
    restart: unless-stopped
    environment:
{common}      HTTP_PORT: \"8000\"
      HTTPS_PORT: \"8443\"
    depends_on: [ jitsi-prosody-{name} ]
    networks: [ srv ]
  jitsi-prosody-{name}:
    image: ghcr.io/jitsi/prosody:stable-11509
    container_name: nexo-jitsi-prosody-{name}
    restart: unless-stopped
    environment:
{common}      JICOFO_AUTH_USER: ${{JICOFO_AUTH_USER:-focus}}
      JICOFO_AUTH_PASSWORD: ${{JICOFO_AUTH_PASSWORD:?Define JICOFO_AUTH_PASSWORD}}
      JICOFO_COMPONENT_SECRET: ${{JICOFO_COMPONENT_SECRET:?Define JICOFO_COMPONENT_SECRET}}
      JVB_AUTH_USER: ${{JVB_AUTH_USER:-jvb}}
      JVB_AUTH_PASSWORD: ${{JVB_AUTH_PASSWORD:?Define JVB_AUTH_PASSWORD}}
    networks:
      srv:
        aliases: [ xmpp.{domain} ]
  jicofo-{name}:
    image: ghcr.io/jitsi/jicofo:stable-11509
    container_name: nexo-jicofo-{name}
    restart: unless-stopped
    environment:
{common}      JICOFO_AUTH_PASSWORD: ${{JICOFO_AUTH_PASSWORD:?Define JICOFO_AUTH_PASSWORD}}
      JICOFO_COMPONENT_SECRET: ${{JICOFO_COMPONENT_SECRET:?Define JICOFO_COMPONENT_SECRET}}
    depends_on: [ jitsi-prosody-{name} ]
    networks: [ srv ]
  jvb-{name}:
    image: ghcr.io/jitsi/jvb:stable-11509
    container_name: nexo-jvb-{name}
    restart: unless-stopped
    environment:
{common}      DOCKER_HOST_ADDRESS: ${{NEXO_HOST:-127.0.0.1}}
      JVB_ADVERTISE_IPS: ${{NEXO_HOST:-127.0.0.1}}
      JVB_PORT: \"{port}\"
      JVB_AUTH_PASSWORD: ${{JVB_AUTH_PASSWORD:?Define JVB_AUTH_PASSWORD}}
    ports:
      - \"{port}:{port}/udp\"
    depends_on: [ jitsi-prosody-{name} ]
    networks: [ srv ]
"""


def render_compose(registry: dict) -> None:
    output = ["""# GENERADO por scripts/nexo-tenant.py. Carga automatica junto al despliegue base.
services:
"""]
    if registry["tenants"]:
        output.append("  asterisk:\n    environment:\n")
        for tenant in registry["tenants"]:
            secret = f"TENANT_{tenant['name'].upper().replace('-', '_')}_SIP_PASSWORD"
            output.append(f"      {secret}: ${{{secret}:-}}\n")
    output.append("""\
  keycloak:
    volumes:
      - ./tenants:/opt/keycloak/nexo/tenants:ro
  proxy:
    volumes:
      - ./tenants/nginx:/etc/nginx/tenants:ro
  voip-gateway:
    environment:
      NEXO_TENANTS: /tenants/registry.json
    volumes:
      - ./tenants/registry.json:/tenants/registry.json:ro
""")
    output.append("""  nextcloud-tenants-init:
    image: nextcloud:35-apache
    container_name: nexo-nextcloud-tenants-init
    restart: \"no\"
    depends_on:
      nextcloud-menu-init:
        condition: service_completed_successfully
        # menu-init reescribe el menu base en cada arranque; sin esto el menu
        # de las empresas quedaba pisado hasta recrear este contenedor.
        restart: true
    environment:
      NEXO_URL: https://${NEXO_HOST:-localhost}:8443
      KC_NEXTCLOUD_CLIENT_SECRET: ${KC_NEXTCLOUD_CLIENT_SECRET:?}
    volumes:
      - nextcloud_data:/var/www/html
      - ./nextcloud/apps/nexo_sync:/var/www/html/custom_apps/nexo_sync:ro
      - ./tenants/registry.json:/tenants/registry.json:ro
      - ./nextcloud/tenants-oidc-setup.sh:/tenants-oidc-setup.sh:ro
    entrypoint: [ \"/bin/sh\", \"/tenants-oidc-setup.sh\" ]
    networks: [ srv ]
""")
    for index, tenant in enumerate(registry["tenants"]):
        name = tenant["name"]
        services = tenant_services(tenant)
        if "chat" in services:
            output.append(f"""  synapse-{name}:
    image: matrixdotorg/synapse:latest
    container_name: nexo-synapse-{name}
    restart: unless-stopped
    entrypoint: [ \"/bin/sh\", \"/nexo/tenant-entrypoint.sh\" ]
    environment:
      NEXO_URL: https://${{NEXO_HOST:-localhost}}:8443
      KC_SYNAPSE_CLIENT_SECRET: ${{KC_SYNAPSE_CLIENT_SECRET:?}}
      SSL_CERT_FILE: /data/nexo-ca-bundle.pem
      REQUESTS_CA_BUNDLE: /data/nexo-ca-bundle.pem
    volumes:
      - synapse_{name}_data:/data
      - ./tenants/{name}/matrix/homeserver.yaml.template:/template/homeserver.yaml:ro
      - ./matrix/tenant-entrypoint.sh:/nexo/tenant-entrypoint.sh:ro
      - ./certs/public:/certs:ro
    depends_on:
      keycloak:
        condition: service_started
      certs:
        condition: service_completed_successfully
    networks: [ srv ]
  element-{name}:
    image: vectorim/element-web:latest
    container_name: nexo-element-{name}
    restart: unless-stopped
    user: root
    entrypoint: [ \"/bin/sh\", \"/nexo/tenant-element-entrypoint.sh\" ]
    environment:
      NEXO_URL: https://${{NEXO_HOST:-localhost}}:8443
    volumes:
      - ./tenants/{name}/matrix/element-config.json.template:/template/config.json:ro
      - ./matrix/tenant-element-entrypoint.sh:/nexo/tenant-element-entrypoint.sh:ro
    depends_on: [ synapse-{name} ]
    networks: [ srv ]
""")
        if "videoconferencia" in services:
            output.append(jitsi_services(name, index))
    output.append("\nvolumes:\n")
    for tenant in registry["tenants"]:
        if "chat" in tenant_services(tenant):
            output.append(f"  synapse_{tenant['name']}_data:\n")
    content = "".join(output)
    # Compose carga el override automaticamente; se conserva la copia con nombre
    # para compatibilidad con comandos y documentacion anteriores.
    for filename in ("docker-compose.override.yml", "docker-compose.multiempresa.yml"):
        (ROOT / filename).write_text(content, encoding="utf-8")


def render(registry: dict) -> None:
    seen = set()
    for index, tenant in enumerate(registry["tenants"]):
        tenant["name"] = validate_name(tenant["name"])
        prefix = int(tenant["range_prefix"])
        if prefix in seen or not 1 <= prefix <= 9:
            raise ValueError("Prefijos de extensiones ausentes, duplicados o fuera de rango")
        seen.add(prefix)
        unknown = tenant_services(tenant) - SERVICES
        if unknown:
            raise ValueError(f"Servicios desconocidos en {tenant['name']}: {unknown}")
        provider = tenant.get("ai_provider")
        if provider is not None and provider not in AI_PROVIDERS:
            raise ValueError(f"Proveedor IA desconocido en {tenant['name']}: {provider!r}")
        render_asterisk(tenant)
        render_keycloak(tenant)
        render_matrix(tenant)
        render_nginx(tenant, index + 2)
    active = {t["name"] for t in registry["tenants"]}
    for path in (TENANTS / "nginx").glob("tenant-*.conf") if (TENANTS / "nginx").exists() else []:
        if path.stem.removeprefix("tenant-") not in active:
            path.unlink()
    (TENANTS / "nginx" / "administracion.conf").write_text(
        "location = /administracion/ {\n"
        "    return 302 https://$http_host/keycloak/admin/master/console/;\n"
        "}\n", encoding="utf-8", newline="\n")
    render_compose(registry)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alta y renderizado multiempresa de Nexo")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="Dar de alta una empresa")
    add.add_argument("name")
    add.add_argument("--range-prefix", type=int, required=True, help="1 para 1xxx, 2 para 2xxx")
    add.add_argument("--display-name")
    add.add_argument("--services", default="chat,telefonia,videoconferencia")
    add.add_argument("--ai-provider", choices=AI_PROVIDERS)
    sub.add_parser("render", help="Regenerar archivos desde registry.json")
    args = parser.parse_args()
    try:
        if args.command == "add":
            add_tenant(args)
        else:
            registry = load_registry()
            render(registry)
            print(f"Configuracion regenerada para {len(registry['tenants'])} empresas.")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

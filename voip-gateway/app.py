import base64
import hashlib
import json
import os
import re
import secrets
import socket
import threading
import zlib
from pathlib import Path
from urllib.parse import urlencode

import jwt
import requests
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session
from itsdangerous import BadData, URLSafeTimedSerializer
from jwt import PyJWKClient
from werkzeug.middleware.proxy_fix import ProxyFix

NEXO_URL = os.environ["NEXO_URL"].rstrip("/")
CLIENT_SECRET = os.environ["KC_VOIP_CLIENT_SECRET"]
AMI_HOST = os.environ.get("VOIP_AMI_HOST", "asterisk")
AMI_PORT = int(os.environ.get("VOIP_AMI_PORT", "5038"))
AMI_USER = os.environ["VOIP_AMI_USER"]
AMI_SECRET = os.environ["VOIP_AMI_SECRET"]
DATA_DIR = Path("/data")
USERS_PATH = DATA_DIR / "users.json"
PJSIP_PATH = DATA_DIR / "pjsip-users.conf"
PROVISION_LOCK = threading.Lock()
TENANTS_PATH = os.environ.get("NEXO_TENANTS")


def _load_tenants():
    if not TENANTS_PATH:
        return {}
    with open(TENANTS_PATH, encoding="utf-8") as handle:
        return {item["name"]: item for item in json.load(handle)["tenants"]}


TENANTS = _load_tenants()


def _oidc(tenant=None):
    if tenant is None:
        realm = "nexo"
        client_id = os.environ.get("VOIP_OIDC_CLIENT_ID", "voip")
        redirect_uri = f"{NEXO_URL}/voip-sso/callback"
    else:
        if tenant not in TENANTS:
            raise KeyError(tenant)
        realm = f"nexo-{tenant}"
        client_id = "nexo-portal"
        redirect_uri = f"{NEXO_URL}/voip-sso/{tenant}/callback"
    issuer = f"{NEXO_URL}/keycloak/realms/{realm}"
    internal_issuer = f"http://keycloak:8080/realms/{realm}"
    return {
        "client_id": client_id,
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{internal_issuer}/protocol/openid-connect/token",
        "jwks_uri": f"{internal_issuer}/protocol/openid-connect/certs",
        "redirect_uri": redirect_uri,
    }


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["VOIP_SESSION_SECRET"],
    SESSION_COOKIE_NAME="nexo_voip",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=28800,
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
oidc_flow_cookie = URLSafeTimedSerializer(app.secret_key, salt="nexo-oidc-flow")
OIDC_FLOW_LIFETIME = 600
jwks_clients = {}


def _jwks(uri):
    if uri not in jwks_clients:
        jwks_clients[uri] = PyJWKClient(uri)
    return jwks_clients[uri]


def _write_atomic(path, content, mode=0o600):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _load_users():
    if not USERS_PATH.exists():
        return {}
    with open(USERS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _extension_for(subject, users, tenant=None):
    used = {entry["extension"] for entry in users.values()}
    start = 2000 if tenant is None else int(TENANTS[tenant]["range_prefix"]) * 1000 + 100
    size = 1000 if tenant is None else 900
    candidate = start + (zlib.crc32(subject.encode("utf-8")) % size)
    for _ in range(size):
        extension = str(candidate)
        if extension not in used:
            return extension
        candidate = start + ((candidate - start + 1) % size)
    raise RuntimeError("No quedan extensiones SIP disponibles en esta empresa")


def _pjsip_config(users):
    sections = ["; Generado por voip-gateway desde identidades de Keycloak.\n"]
    for entry in sorted(users.values(), key=lambda item: item["extension"]):
        extension = entry["extension"]
        tenant = entry.get("tenant")
        context = f"tenant-{tenant}" if tenant else "internal"
        domain = f"{tenant}.nexo.local" if tenant else "nexo.local"
        display_name = entry.get("display_name") or entry["username"]
        display_name = display_name.replace("\r", " ").replace("\n", " ")
        display_name = display_name.replace('"', "").replace("<", "").replace(">", "")
        sections.append(f"""
[{extension}]
type=endpoint
transport=transport-ws
context={context}
disallow=all
allow=opus,ulaw,alaw
auth=auth-{extension}
aors={extension}
callerid="{display_name}" <{extension}>
webrtc=yes
from_domain={domain}
media_encryption=dtls
media_encryption_optimistic=no
dtls_cert_file=/etc/asterisk/keys/server.crt
dtls_private_key=/etc/asterisk/keys/server.key
dtls_verify=fingerprint
dtls_setup=actpass
ice_support=yes
rtcp_mux=yes
use_avpf=yes
bundle=yes
direct_media=no
rewrite_contact=yes
force_rport=yes
rtp_symmetric=yes
dtmf_mode=rfc4733
device_state_busy_at=1
tos_audio=ef
cos_audio=5

[auth-{extension}]
type=auth
auth_type=userpass
username={extension}
password={entry["sip_password"]}

[{extension}]
type=aor
max_contacts=3
remove_existing=yes
qualify_frequency=0
""")
    return "\n".join(sections)


def _ami_response(connection, action_id):
    lines = []
    while True:
        line = connection.readline()
        if not line:
            raise RuntimeError("AMI cerró la conexión")
        line = line.decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            if any(f"ActionID: {action_id}" == item for item in lines):
                return "\n".join(lines)
            lines = []
            continue
        lines.append(line)


def _ami_action(connection, action, **fields):
    action_id = secrets.token_hex(8)
    payload = {"Action": action, "ActionID": action_id, **fields}
    raw = "".join(f"{key}: {value}\r\n" for key, value in payload.items()) + "\r\n"
    connection.write(raw.encode("utf-8"))
    connection.flush()
    response = _ami_response(connection, action_id)
    if "Response: Success" not in response:
        raise RuntimeError(f"AMI rechazó {action}: {response}")
    return response


def _reload_asterisk():
    with socket.create_connection((AMI_HOST, AMI_PORT), timeout=10) as tcp:
        connection = tcp.makefile("rwb")
        _ami_action(connection, "Login", Username=AMI_USER, Secret=AMI_SECRET)
        try:
            _ami_action(connection, "Command", Command="module reload res_pjsip.so")
        finally:
            try:
                _ami_action(connection, "Logoff")
            except RuntimeError:
                pass


def _provision(subject, username, display_name, tenant=None, groups=None):
    if tenant is not None:
        services = set(TENANTS[tenant].get("services", []))
        if "telefonia" not in services or f"{tenant}-servicio-telefonia" not in set(groups or []):
            raise PermissionError("La identidad no tiene contratada Telefonía")
    with PROVISION_LOCK:
        users = _load_users()
        if subject in users:
            entry = users[subject]
            if entry.get("tenant") != tenant:
                raise PermissionError("La identidad pertenece a otra empresa")
            return entry
        entry = {
            "username": username,
            "display_name": display_name or username,
            "extension": _extension_for(subject, users, tenant),
            "sip_password": secrets.token_urlsafe(24),
            "tenant": tenant,
        }
        previous = PJSIP_PATH.read_text(encoding="utf-8") if PJSIP_PATH.exists() else ""
        updated = dict(users)
        updated[subject] = entry
        _write_atomic(PJSIP_PATH, _pjsip_config(updated), 0o644)
        try:
            _reload_asterisk()
        except Exception:
            _write_atomic(PJSIP_PATH, previous, 0o644)
            raise
        _write_atomic(USERS_PATH, json.dumps(updated, ensure_ascii=False, indent=2))
        return entry


def _start_login(tenant=None):
    try:
        oidc = _oidc(tenant)
    except KeyError:
        return jsonify(error="Empresa no encontrada"), 404
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    next_url = request.args.get("next", "")
    admin_url = f"/voip-sso/{tenant}/empresa/"
    if tenant and next_url and next_url != admin_url and not re.fullmatch(
        rf"/{re.escape(tenant)}/[A-Za-z0-9_?&=./%-]*", next_url
    ):
        return jsonify(error="Destino de retorno inválido"), 400
    query = urlencode({
        "client_id": oidc["client_id"], "response_type": "code",
        "scope": "openid profile email kc-admin-api" if tenant and next_url == admin_url else "openid profile email",
        "redirect_uri": oidc["redirect_uri"],
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    response = redirect(f"{oidc['authorization_endpoint']}?{query}")
    response.set_cookie(
        f"nexo_oidc_{state}",
        oidc_flow_cookie.dumps({
            "state": state, "tenant": tenant, "nonce": nonce, "verifier": verifier, "next": next_url,
        }),
        max_age=OIDC_FLOW_LIFETIME, path=f"/voip-sso/{tenant}/callback" if tenant else "/voip-sso/callback",
        secure=True, httponly=True, samesite="Lax",
    )
    return response


def _finish_callback(tenant=None):
    state = request.args.get("state", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", state):
        return jsonify(error="Estado OIDC inválido"), 400
    cookie_name = f"nexo_oidc_{state}"
    try:
        flow = oidc_flow_cookie.loads(request.cookies.get(cookie_name, ""), max_age=OIDC_FLOW_LIFETIME)
    except BadData:
        return render_template("login_retry.html"), 400
    if flow["tenant"] != tenant or flow["state"] != state:
        return jsonify(error="La empresa no coincide con el inicio OIDC"), 400
    code = request.args.get("code")
    if not code:
        return jsonify(error="Keycloak no devolvió un código"), 400
    try:
        oidc = _oidc(tenant)
    except KeyError:
        return jsonify(error="Empresa no encontrada"), 404
    response = requests.post(oidc["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": oidc["redirect_uri"], "client_id": oidc["client_id"],
        "client_secret": CLIENT_SECRET, "code_verifier": flow["verifier"],
    }, timeout=15)
    response.raise_for_status()
    token = response.json()
    signing_key = _jwks(oidc["jwks_uri"]).get_signing_key_from_jwt(token["id_token"])
    identity = jwt.decode(token["id_token"], signing_key.key, algorithms=["RS256"],
                          audience=oidc["client_id"], issuer=oidc["issuer"],
                          options={"require": ["exp", "iat", "sub"]})
    if identity.get("nonce") != flow["nonce"]:
        return jsonify(error="Nonce OIDC inválido"), 400
    next_url = flow["next"]
    previous_identity = session.get("identity", {})
    is_admin = tenant and f"{tenant}-administradores" in identity.get("groups", [])
    if not (is_admin and previous_identity.get("tenant") == tenant
            and previous_identity.get("subject") == identity["sub"]):
        session.clear()
    session.permanent = True
    session["identity"] = {
        "subject": identity["sub"],
        "username": identity.get("preferred_username", identity["sub"]),
        "display_name": identity.get("name") or identity.get("preferred_username"),
        "tenant": tenant,
        "groups": identity.get("groups", []),
    }
    if tenant and next_url == f"/voip-sso/{tenant}/empresa/":
        if not is_admin:
            abort(403, "Se requiere una cuenta administradora de la empresa.")
        session["company_access_token"] = token["access_token"]
        session["company_csrf"] = secrets.token_urlsafe(32)
    response = redirect(next_url or (f"/{tenant}/voip/" if tenant else "/voip/"))
    response.delete_cookie(
        cookie_name, path=f"/voip-sso/{tenant}/callback" if tenant else "/voip-sso/callback",
        secure=True, httponly=True, samesite="Lax",
    )
    return response


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/login")
def login():
    return _start_login()


@app.get("/<tenant>/login")
def tenant_login(tenant):
    return _start_login(tenant)


@app.get("/callback")
def callback():
    return _finish_callback()


@app.get("/<tenant>/callback")
def tenant_callback(tenant):
    return _finish_callback(tenant)


@app.route("/<tenant>/empresa/", methods=["GET", "POST"])
def company_admin(tenant):
    if tenant not in TENANTS:
        abort(404)
    path = f"/voip-sso/{tenant}/empresa/"
    login_url = f"/voip-sso/{tenant}/login?" + urlencode({"next": path})
    identity = session.get("identity", {})
    token = session.get("company_access_token")
    if identity.get("tenant") != tenant or not token:
        if request.method == "POST":
            abort(403)
        return redirect(login_url)
    if f"{tenant}-administradores" not in identity.get("groups", []):
        abort(403)

    def keycloak(method, resource, **kwargs):
        response = requests.request(
            method, f"http://keycloak:8080/admin/realms/nexo-{tenant}/{resource}",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
            allow_redirects=False, **kwargs,
        )
        response.raise_for_status()
        return response

    csrf = session["company_csrf"]
    area_prefix = f"{tenant}-area-"
    services = {f"{tenant}-servicio-{service}" for service in TENANTS[tenant].get("services", [])}
    action = request.form.get("action") if request.method == "POST" else None
    try:
        if request.method == "POST":
            if not secrets.compare_digest(request.form.get("csrf", "").encode(), csrf.encode()):
                abort(403)
            if action == "area":
                label = request.form.get("area", "").strip()
                if not label or len(label) > 80 or "/" in label or not label.isprintable():
                    abort(400, "Introduce un nombre de área válido.")
                keycloak("POST", "groups", json={"name": area_prefix + label})
                flash("Área creada.")
            elif action == "user":
                fields = {name: request.form.get(name, "").strip()
                          for name in ("username", "firstName", "lastName", "email")}
                password = request.form.get("password", "")
                if not all(fields.values()) or not 8 <= len(password) <= 128:
                    abort(400, "Completa todos los datos y usa una contraseña temporal de 8 a 128 caracteres.")
                keycloak("POST", "users", json={
                    **fields, "enabled": True,
                    "credentials": [{"type": "password", "value": password, "temporary": True}],
                })
                flash("Usuario creado. Ya puedes asignarle grupos.")
            elif action == "assign":
                user_id = request.form.get("user_id", "")
                group_id = request.form.get("group_id", "")
                if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in (user_id, group_id)):
                    abort(400)
                group = keycloak("GET", f"groups/{group_id}").json()
                name = group["name"]
                if group.get("path") != "/" + name or not (name.startswith(area_prefix) or name in services):
                    abort(403, "Solo se pueden asignar áreas y servicios de esta empresa.")
                keycloak("PUT", f"users/{user_id}/groups/{group_id}", json={})
                flash("Grupo asignado.")
            else:
                abort(400)
            return redirect(path, code=303)

        query = request.args.get("buscar", "").strip()[:128]
        users = keycloak("GET", "users", params={"search": query, "max": 50}).json()
        groups = []
        offset = 0
        while True:
            batch = keycloak("GET", "groups", params={"first": offset, "max": 100}).json()
            groups.extend(group for group in batch
                          if group["name"].startswith(area_prefix) or group["name"] in services)
            if len(batch) < 100:
                break
            offset += len(batch)
        return render_template(
            "company_admin.html", company=TENANTS[tenant]["display_name"],
            users=users, groups=groups, csrf=csrf, path=path, query=query,
            area_prefix=area_prefix,
        )
    except requests.HTTPError as error:
        status = error.response.status_code
        if status == 401:
            session.pop("company_access_token", None)
            return render_template("login_retry.html", retry_url=login_url), 401
        if status == 409 and action:
            messages = {
                "area": "Ya existe un área con ese nombre. Puedes seleccionarla en Asignar un grupo.",
                "user": "El nombre de usuario o el correo ya está en uso. Busca la cuenta existente o utiliza otros datos.",
                "assign": "No se pudo completar la asignación. Revisa el usuario y el grupo e inténtalo de nuevo.",
            }
            flash(messages[action], "error")
            return redirect(path, code=303)
        if status in (400, 403, 404, 409):
            abort(status, "Keycloak rechazó la operación. Comprueba los datos y tu sesión de empresa.")
        abort(502, "Keycloak no pudo completar la operación.")
    except requests.RequestException:
        abort(502, "No se pudo conectar con Keycloak.")


# --- Sincronización Nextcloud -> Keycloak -------------------------------------
# La app nexo_sync de Nextcloud llama a este endpoint (red interna srv) cada vez que
# el administrador de una empresa crea/borra usuarios o los mueve de sector desde
# Nextcloud. Keycloak sigue siendo la fuente de identidad (SSO, Matrix, SIP).
SYNC_SECRET = os.environ.get("NEXO_SYNC_SECRET", "")
KC_ADMIN_USER = os.environ.get("KC_ADMIN_USER", "")
KC_ADMIN_PASSWORD = os.environ.get("KC_ADMIN_PASSWORD", "")
KC_INTERNAL = "http://keycloak:8080"
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _kc_master_token():
    response = requests.post(
        f"{KC_INTERNAL}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": KC_ADMIN_USER, "password": KC_ADMIN_PASSWORD},
        timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def _sync_group_ok(tenant, name):
    services = {f"{tenant}-servicio-{item}" for item in TENANTS[tenant].get("services", [])}
    if TENANTS[tenant].get("ai_provider", "gemini") is not None:
        services.add(f"{tenant}-servicio-asistente-ia")
    is_area = name.startswith(f"{tenant}-area-") and len(name) <= 100
    return is_area or name in services or name == f"{tenant}-administradores"


def _find_login_provider(identifier):
    """Devuelve el id de proveedor user_oidc (keycloak=1, luego una empresa por orden del registro)
    del realm donde existe el usuario o correo, o None."""
    token = _kc_master_token()
    realms = [("nexo", 1)] + [(f"nexo-{name}", index + 2) for index, name in enumerate(TENANTS)]
    for realm, provider_id in realms:
        for params in ({"username": identifier, "exact": "true"}, {"email": identifier, "exact": "true"}):
            response = requests.get(f"{KC_INTERNAL}/admin/realms/{realm}/users", params=params,
                                    headers={"Authorization": f"Bearer {token}"}, timeout=10)
            if response.ok and response.json():
                return provider_id
    return None


@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    """Página única de acceso: identifica la empresa de la persona y la envía a su login SSO."""
    if request.method == "GET":
        response = app.make_response(render_template("entrar.html", error=None))
        if request.args.get("salir"):
            # Tras cerrar sesion: el navegador borra todas las cookies del sitio (Nextcloud, Keycloak,
            # asistente y gateway). Solo cookies: "storage" borraria tambien los historiales de chat.
            response.headers["Clear-Site-Data"] = '"cookies"'
        return response
    identifier = request.form.get("identifier", "").strip().lower()[:254]
    provider_id = _find_login_provider(identifier) if identifier and KC_ADMIN_PASSWORD else None
    if provider_id is None:
        return render_template("entrar.html", error="No encontramos una cuenta con ese usuario o correo.",
                               identifier=identifier), 404
    # user_oidc lo reenvía a Keycloak gracias al ajuste aplicado por nextcloud/login-hint.php.
    return redirect(f"/docs/apps/user_oidc/login/{provider_id}?{urlencode({'login_hint': identifier})}", code=303)


@app.post("/internal/sync")
def internal_sync():
    # Nginx añade X-Forwarded-Proto; este endpoint solo es para la red interna.
    if request.headers.get("X-Forwarded-Proto") or not SYNC_SECRET or not KC_ADMIN_PASSWORD:
        abort(404)
    supplied = request.headers.get("X-Nexo-Sync-Secret", "")
    if not secrets.compare_digest(supplied.encode(), SYNC_SECRET.encode()):
        abort(403)
    data = request.get_json(silent=True) or {}
    tenant = data.get("tenant", "")
    action = data.get("action", "")
    if tenant not in TENANTS:
        return jsonify(error="Empresa desconocida"), 404
    realm_url = f"{KC_INTERNAL}/admin/realms/nexo-{tenant}"
    headers = {"Authorization": f"Bearer {_kc_master_token()}"}

    def kc(method, resource, **kwargs):
        response = requests.request(method, f"{realm_url}/{resource}", headers=headers,
                                    timeout=10, allow_redirects=False, **kwargs)
        response.raise_for_status()
        return response

    def find_user(username):
        found = kc("GET", "users", params={"username": username, "exact": "true"}).json()
        return found[0] if found else None

    def find_group(name):
        found = kc("GET", "groups", params={"search": name, "exact": "true"}).json()
        return next((item for item in found if item["name"] == name), None)

    def ensure_group(name):
        if not _sync_group_ok(tenant, name):
            abort(403, "Grupo no permitido para esta empresa")
        group = find_group(name)
        if group is None:
            kc("POST", "groups", json={"name": name})
            group = find_group(name)
        return group

    username = str(data.get("username", "")).lower()
    if action != "ensure_group" and not USERNAME_RE.match(username):
        return jsonify(error="Nombre de usuario no válido"), 400

    if action == "ensure_group":
        ensure_group(data.get("group", ""))
        return jsonify(ok=True)
    if action == "ensure_user":
        # El uid de Nextcloud (unique-uid=0) es este username: sin prefijo de empresa, dos realms
        # podrian compartir cuenta y por tanto archivos. Se exige, no solo se recomienda.
        if not username.startswith(tenant):
            return jsonify(error=f"El usuario debe empezar por el prefijo de la empresa ({tenant})"), 400
        user = find_user(username)
        created = user is None
        if created:
            display = (data.get("display_name") or username).strip()
            first, _, last = display.partition(" ")
            kc("POST", "users", json={
                "username": username, "enabled": True, "emailVerified": True,
                "firstName": first or username, "lastName": last or "-",
                "email": data.get("email") or f"{username}@{tenant}.nexo.local",
                "credentials": [{"type": "password", "temporary": True,
                                 "value": data.get("password") or secrets.token_urlsafe(24)}],
            })
            user = find_user(username)
            for service in TENANTS[tenant].get("services", []):
                kc("PUT", f"users/{user['id']}/groups/{ensure_group(f'{tenant}-servicio-{service}')['id']}", json={})
        return jsonify(ok=True, created=created)
    user = find_user(username)
    if user is None:
        return jsonify(error="Usuario inexistente en Keycloak"), 404
    if action == "set_membership":
        group = ensure_group(data.get("group", ""))
        method = "PUT" if data.get("member") else "DELETE"
        kc(method, f"users/{user['id']}/groups/{group['id']}", **({"json": {}} if method == "PUT" else {}))
        return jsonify(ok=True)
    if action == "update_user":
        display = (data.get("display_name") or "").strip()
        update = {}
        if display and display != username:
            first, _, last = display.partition(" ")
            update.update(firstName=first, lastName=last or "-")
        if data.get("email"):
            update["email"] = data["email"]
        if update:
            kc("PUT", f"users/{user['id']}", json={**user, **update})
        return jsonify(ok=True)
    if action == "set_password":
        kc("PUT", f"users/{user['id']}/reset-password",
           json={"type": "password", "temporary": True, "value": data.get("password", "")})
        return jsonify(ok=True)
    if action == "delete_user":
        kc("DELETE", f"users/{user['id']}")
        return jsonify(ok=True)
    return jsonify(error="Acción desconocida"), 400


@app.get("/authorize")
def authorize():
    original = request.headers.get("X-Original-URI", "")
    match = re.match(r"^/([a-z][a-z0-9-]{1,30})/jitsi(?:/|$)", original)
    if not match:
        return "", 403
    tenant = match.group(1)
    identity = session.get("identity")
    if not identity or identity.get("tenant") != tenant:
        return "", 401
    if tenant not in TENANTS or "videoconferencia" not in TENANTS[tenant].get("services", []):
        return "", 403
    if f"{tenant}-servicio-videoconferencia" not in identity.get("groups", []):
        return "", 403
    return "", 204


def _config(identity):
    entry = _provision(**identity)
    tenant = identity.get("tenant")
    domain = f"{tenant}.nexo.local" if tenant else "nexo.local"
    return jsonify({
        "socket": {"uri": f"wss://{request.host}/asterisk/ws", "via_transport": "wss"},
        "registrar_server": f"sip:{domain}", "realm": domain, "register": True,
        "register_expires": 600, "session_timers": False, "contact_uri": None,
        "instance_id": None, "use_preloaded_route": False,
        "pcConfig": {"rtcpMuxPolicy": "require", "iceServers": []},
        "callstats": {"enabled": False, "AppID": None, "AppSecret": None},
        "uri": f"sip:{entry['extension']}@{domain}",
        "authorization_user": entry["extension"], "password": entry["sip_password"],
        "display_name": entry["display_name"], "extension": entry["extension"], "tenant": tenant,
    })


@app.get("/config.json")
def voip_config():
    identity = session.get("identity")
    if not identity or identity.get("tenant") is not None:
        return jsonify(login_url="/voip-sso/login"), 401
    return _config(identity)


@app.get("/<tenant>/config.json")
def tenant_voip_config(tenant):
    if tenant not in TENANTS:
        return jsonify(error="Empresa no encontrada"), 404
    identity = session.get("identity")
    if not identity or identity.get("tenant") != tenant:
        return jsonify(login_url=f"/voip-sso/{tenant}/login?next=/{tenant}/voip/"), 401
    return _config(identity)


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(PermissionError)
def forbidden(error):
    return jsonify(error=str(error)), 403


@app.errorhandler(requests.RequestException)
def oidc_unavailable(error):
    return jsonify(error="Keycloak no está disponible temporalmente"), 503

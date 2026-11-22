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
from flask import Flask, jsonify, redirect, request, session
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
    if tenant and next_url and not re.fullmatch(rf"/{re.escape(tenant)}/[A-Za-z0-9_?&=./%-]*", next_url):
        return jsonify(error="Destino de retorno inválido"), 400
    session.clear()
    session.permanent = True
    session.update(oidc_state=state, oidc_nonce=nonce, oidc_verifier=verifier,
                   oidc_tenant=tenant, next_url=next_url)
    query = urlencode({
        "client_id": oidc["client_id"], "response_type": "code",
        "scope": "openid profile email", "redirect_uri": oidc["redirect_uri"],
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return redirect(f"{oidc['authorization_endpoint']}?{query}")


def _finish_callback(tenant=None):
    if tenant != session.get("oidc_tenant"):
        return jsonify(error="La empresa no coincide con el inicio OIDC"), 400
    if request.args.get("state") != session.pop("oidc_state", None):
        return jsonify(error="Estado OIDC inválido"), 400
    code = request.args.get("code")
    if not code:
        return jsonify(error="Keycloak no devolvió un código"), 400
    verifier = session.pop("oidc_verifier", None)
    nonce = session.pop("oidc_nonce", None)
    session.pop("oidc_tenant", None)
    try:
        oidc = _oidc(tenant)
    except KeyError:
        return jsonify(error="Empresa no encontrada"), 404
    response = requests.post(oidc["token_endpoint"], data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": oidc["redirect_uri"], "client_id": oidc["client_id"],
        "client_secret": CLIENT_SECRET, "code_verifier": verifier,
    }, timeout=15)
    response.raise_for_status()
    token = response.json()
    signing_key = _jwks(oidc["jwks_uri"]).get_signing_key_from_jwt(token["id_token"])
    identity = jwt.decode(token["id_token"], signing_key.key, algorithms=["RS256"],
                          audience=oidc["client_id"], issuer=oidc["issuer"],
                          options={"require": ["exp", "iat", "sub"]})
    if identity.get("nonce") != nonce:
        return jsonify(error="Nonce OIDC inválido"), 400
    next_url = session.pop("next_url", "")
    session.clear()
    session.permanent = True
    session["identity"] = {
        "subject": identity["sub"],
        "username": identity.get("preferred_username", identity["sub"]),
        "display_name": identity.get("name") or identity.get("preferred_username"),
        "tenant": tenant,
        "groups": identity.get("groups", []),
    }
    if next_url:
        return redirect(next_url)
    return redirect(f"/{tenant}/voip/" if tenant else "/voip/")


@app.get("/healthz")
def healthz():
    return jsonify(status="ok", tenants=sorted(TENANTS))


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

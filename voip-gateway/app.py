import base64
import hashlib
import json
import os
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
CLIENT_ID = os.environ.get("VOIP_OIDC_CLIENT_ID", "voip")
CLIENT_SECRET = os.environ["KC_VOIP_CLIENT_SECRET"]
ISSUER = f"{NEXO_URL}/keycloak/realms/nexo"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/protocol/openid-connect/auth"
INTERNAL_ISSUER = "http://keycloak:8080/realms/nexo"
TOKEN_ENDPOINT = f"{INTERNAL_ISSUER}/protocol/openid-connect/token"
JWKS_URI = f"{INTERNAL_ISSUER}/protocol/openid-connect/certs"
REDIRECT_URI = f"{NEXO_URL}/voip-sso/callback"
AMI_HOST = os.environ.get("VOIP_AMI_HOST", "asterisk")
AMI_PORT = int(os.environ.get("VOIP_AMI_PORT", "5038"))
AMI_USER = os.environ["VOIP_AMI_USER"]
AMI_SECRET = os.environ["VOIP_AMI_SECRET"]
DATA_DIR = Path("/data")
USERS_PATH = DATA_DIR / "users.json"
PJSIP_PATH = DATA_DIR / "pjsip-users.conf"
PROVISION_LOCK = threading.Lock()

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
jwks_client = PyJWKClient(JWKS_URI)


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


def _extension_for(subject, users):
    used = {entry["extension"] for entry in users.values()}
    candidate = 2000 + (zlib.crc32(subject.encode("utf-8")) % 1000)
    for _ in range(1000):
        extension = str(candidate)
        if extension not in used:
            return extension
        candidate = 2000 + ((candidate - 1999) % 1000)
    raise RuntimeError("No quedan extensiones SIP disponibles")


def _pjsip_config(users):
    sections = ["; Generado por voip-gateway desde identidades de Keycloak.\n"]
    for entry in sorted(users.values(), key=lambda item: item["extension"]):
        extension = entry["extension"]
        display_name = entry.get("display_name") or entry["username"]
        display_name = display_name.replace("\r", " ").replace("\n", " ")
        display_name = display_name.replace('"', "").replace("<", "").replace(">", "")
        sections.append(f"""
[{extension}]
type=endpoint
transport=transport-ws
context=internal
disallow=all
allow=opus,ulaw,alaw
auth=auth-{extension}
aors={extension}
callerid="{display_name}" <{extension}>
webrtc=yes
from_domain=nexo.local
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
            _ami_action(
                connection,
                "Command",
                Command="module reload res_pjsip.so",
            )
        finally:
            try:
                _ami_action(connection, "Logoff")
            except RuntimeError:
                pass


def _provision(subject, username, display_name):
    with PROVISION_LOCK:
        users = _load_users()
        if subject in users:
            return users[subject]
        entry = {
            "username": username,
            "display_name": display_name or username,
            "extension": _extension_for(subject, users),
            "sip_password": secrets.token_urlsafe(24),
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


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/login")
def login():
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    session.permanent = True
    session["oidc_state"] = state
    session["oidc_nonce"] = nonce
    session["oidc_verifier"] = verifier
    query = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return redirect(f"{AUTHORIZATION_ENDPOINT}?{query}")


@app.get("/callback")
def callback():
    if request.args.get("state") != session.pop("oidc_state", None):
        return jsonify(error="Estado OIDC inválido"), 400
    code = request.args.get("code")
    if not code:
        return jsonify(error="Keycloak no devolvió un código"), 400
    verifier = session.pop("oidc_verifier", None)
    nonce = session.pop("oidc_nonce", None)
    response = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    response.raise_for_status()
    token = response.json()
    signing_key = jwks_client.get_signing_key_from_jwt(token["id_token"])
    identity = jwt.decode(
        token["id_token"],
        signing_key.key,
        algorithms=["RS256"],
        audience=CLIENT_ID,
        issuer=ISSUER,
        options={"require": ["exp", "iat", "sub"]},
    )
    if identity.get("nonce") != nonce:
        return jsonify(error="Nonce OIDC inválido"), 400
    session.clear()
    session.permanent = True
    session["identity"] = {
        "subject": identity["sub"],
        "username": identity.get("preferred_username", identity["sub"]),
        "display_name": identity.get("name") or identity.get("preferred_username"),
    }
    return redirect("/voip/")


@app.get("/config.json")
def voip_config():
    identity = session.get("identity")
    if not identity:
        return jsonify(login_url="/voip-sso/login"), 401
    entry = _provision(**identity)
    return jsonify({
        "socket": {
            "uri": f"wss://{request.host}/asterisk/ws",
            "via_transport": "wss",
        },
        "registrar_server": "sip:nexo.local",
        "realm": "nexo.local",
        "register": True,
        "register_expires": 600,
        "session_timers": False,
        "uri": f"sip:{entry['extension']}@nexo.local",
        "authorization_user": entry["extension"],
        "password": entry["sip_password"],
        "display_name": entry["display_name"],
        "extension": entry["extension"],
    })


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(requests.RequestException)
def oidc_unavailable(error):
    return jsonify(error="Keycloak no está disponible temporalmente"), 503

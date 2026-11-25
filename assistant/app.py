# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import jwt
import requests
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session
from itsdangerous import BadData, URLSafeTimedSerializer

import nextcloud
from providers import EndpointError, ProviderError, provider_for, public_https_url

PREFIX = "/airi"
CLIENT_ID = "nexo-assistant"
NEXO_URL = os.environ["NEXO_URL"].rstrip("/")
CALLBACK = f"{NEXO_URL}{PREFIX}/callback"
KEYCLOAK = "http://keycloak:8080"
REGISTRY = Path("/tenants/registry.json")
CONFIG_PATH = Path(os.getenv("ASSISTANT_DATA", "/data")) / "tenant-config.json"
CONFIG_LOCK = threading.Lock()
STAGE = Path(__file__).with_name("stage")
AUTH_SECONDS = 300
app = Flask(__name__, static_folder="web/assets", static_url_path=f"{PREFIX}/assets", template_folder="web")
app.config.update(
    SECRET_KEY=os.getenv("AI_SESSION_SECRET") or secrets.token_hex(32),
    SESSION_COOKIE_NAME="nexo_assistant",
    SESSION_COOKIE_PATH=f"{PREFIX}/",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=32 * 1024,
)
FILE_TOKENS = {}  # token de Nextcloud de cada sesión; vive solo en el servidor, nunca en la cookie
FILE_TOKENS_LOCK = threading.Lock()
speech_ticket = URLSafeTimedSerializer(app.secret_key, salt="nexo-assistant-speech")


def tenants():
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return {
            t["name"]: t for t in data["tenants"]
            if re.fullmatch(r"[a-z][a-z0-9-]{1,30}", t["name"])
        }
    except (OSError, ValueError, TypeError, KeyError):
        abort(503, "No se pudo leer la configuración de las empresas.")


def load_config(tenant):
    """Configuración propia de la empresa (modelo de IA, voz y personaje); {} si usa los valores predeterminados."""
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config = data.get(tenant, {})
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(tenant, config):
    with CONFIG_LOCK:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if config:
            data[tenant] = config
        else:
            data.pop(tenant, None)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = CONFIG_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, CONFIG_PATH)


def realm_for(tenant):
    return f"nexo-{tenant}" if tenant else "nexo"


def issuer(tenant):
    return f"{NEXO_URL}/keycloak/realms/{realm_for(tenant)}"


def keycloak_endpoint(tenant):
    return f"{KEYCLOAK}/realms/{realm_for(tenant)}/protocol/openid-connect"


@lru_cache(maxsize=16)
def jwks(tenant):
    return jwt.PyJWKClient(f"{keycloak_endpoint(tenant)}/certs", timeout=5)


def user_for(tenant):
    user = session.get("user", {})
    if user.get("issuer") == issuer(tenant) and user.get("expires", 0) > time.time():
        return user
    return None


def assistant_url(tenant):
    return f"{PREFIX}/" + (f"?{urlencode({'tenant': tenant})}" if tenant else "")


def begin_login(tenant, after=""):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    pending = {
        "tenant": tenant, "verifier": verifier, "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32), "expires": time.time() + AUTH_SECONDS, "after": after,
    }
    session["oidc"] = pending
    query = urlencode({
        "client_id": CLIENT_ID, "redirect_uri": CALLBACK, "response_type": "code",
        "scope": "openid profile", "state": pending["state"], "nonce": pending["nonce"],
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return redirect(f"{issuer(tenant)}/protocol/openid-connect/auth?{query}")


@app.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; media-src 'self' blob:; frame-ancestors 'self'; "
        "form-action 'self'; base-uri 'none'; object-src 'none'"
    ))
    return response


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get(f"{PREFIX}/")
def index():
    tenant = request.args.get("tenant", "")
    company = tenants().get(tenant)
    if tenant and company is None:
        abort(404)
    user = user_for(tenant)
    if not user:
        return begin_login(tenant)
    provider = provider_for(tenant, company, load_config(tenant))
    status = ""
    if not provider:
        status = "El asistente está deshabilitado para tu empresa."
    elif not (user.get("assistant") or user.get("admin")):
        status = "El administrador de tu empresa no te ha dado acceso al asistente."
    elif not provider.ready:
        status = "El proveedor de IA todavía no está configurado."
    elif (STAGE / "index.html").is_file():
        return redirect(f"{PREFIX}/stage/?{urlencode({'tenant': tenant})}#/")
    return render_template(
        "index.html", tenant=tenant, company=(company or {}).get("display_name", "Nexo Unificado"),
        status=status,
    )


@lru_cache(maxsize=1)
def stage_script_hashes():
    html = (STAGE / "index.html").read_bytes()
    scripts = re.findall(rb"<script\b[^>]*>(.*?)</script>", html, re.DOTALL)
    return " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(script).digest()).decode() + "'"
        for script in scripts if script
    )


@app.get(f"{PREFIX}/stage/")
def stage_index():
    tenant = request.args.get("tenant", "")
    user = user_for(tenant)
    if not user:
        return redirect(assistant_url(tenant))
    provider = provider_for(tenant, tenants().get(tenant), load_config(tenant))
    if not (user.get("assistant") or user.get("admin")) or not provider or not provider.ready:
        return redirect(assistant_url(tenant))
    index_file = STAGE / "index.html"
    if not index_file.is_file():
        abort(404)
    profile = hmac.new(app.secret_key.encode(), json.dumps([user["issuer"], user["sub"]]).encode(), "sha256").hexdigest()
    metas = (
        f'<meta name="nexo-profile" content="{profile}">'
        f'<meta name="nexo-admin" content="{"true" if user.get("admin") else "false"}">'
    )
    html = index_file.read_bytes().replace(b"<head>", f"<head>{metas}".encode(), 1)
    response = Response(html, mimetype="text/html")
    response.headers["Content-Security-Policy"] = (
        # 'unsafe-eval': el render Live2D (Pixi) lo exige. data:: AIRI carga el módulo de audio de la
        # animación de labios (AudioWorklet) desde una URL data:. El resto sigue siendo del mismo origen.
        f"default-src 'self'; script-src 'self' 'wasm-unsafe-eval' 'unsafe-eval' data: {stage_script_hashes()}; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
        "connect-src 'self' blob: data:; worker-src 'self' blob:; media-src 'self' blob: data:; "
        "frame-ancestors 'self'; form-action 'self'; base-uri 'none'; object-src 'none'"
    )
    return response


@app.get(f"{PREFIX}/stage/<path:asset>")
def stage_asset(asset):
    if asset.lower().endswith(".html"):
        abort(404)
    return send_from_directory(STAGE, asset)


@app.get(f"{PREFIX}/callback")
def callback():
    pending = session.pop("oidc", {})
    state = request.args.get("state", "")
    if not pending or pending["expires"] < time.time() or not secrets.compare_digest(
        state.encode(), pending["state"].encode()
    ):
        abort(400, "La solicitud de inicio de sesión ha caducado o es inválida.")
    tenant = pending["tenant"]
    if tenant and tenant not in tenants():
        abort(404)
    if request.args.get("iss", issuer(tenant)) != issuer(tenant):
        abort(400, "Emisor de sesión inválido.")
    code = request.args.get("code")
    if not code:
        abort(401, "No se pudo iniciar sesión en el asistente.")
    try:
        tokens = requests.post(
            f"{keycloak_endpoint(tenant)}/token",
            data={"grant_type": "authorization_code", "client_id": CLIENT_ID,
                  "code": code, "redirect_uri": CALLBACK, "code_verifier": pending["verifier"]},
            timeout=8, allow_redirects=False,
        )
        tokens.raise_for_status()
        token = tokens.json()["id_token"]
        access = tokens.json().get("access_token")
        access_ttl = int(tokens.json().get("expires_in") or 0)
        public_key = jwks(tenant).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, public_key.key, algorithms=["RS256"], audience=CLIENT_ID,
            issuer=issuer(tenant), options={"require": ["sub", "iat", "exp", "nonce"]},
        )
        if claims.get("azp", CLIENT_ID) != CLIENT_ID or claims["nonce"] != pending["nonce"]:
            raise jwt.InvalidTokenError()
    except (requests.RequestException, jwt.PyJWTError, ValueError, KeyError):
        abort(401, "Keycloak no pudo verificar la sesión del asistente.")
    session.clear()
    # Aislamiento entre empresas: el uid de Nextcloud es el username, así que solo cuentas con el
    # prefijo de su empresa pueden usar el token de archivos (evita colisiones de uid entre realms).
    if access and nextcloud.enabled() and tenant and str(claims.get("preferred_username", "")).startswith(tenant):
        sid = secrets.token_urlsafe(32)
        with FILE_TOKENS_LOCK:
            now = time.time()
            for key in [k for k, v in FILE_TOKENS.items() if v["expires"] < now]:
                del FILE_TOKENS[key]
            FILE_TOKENS[sid] = {"token": access, "expires": now + access_ttl - 10, "issuer": claims["iss"]}
        session["files"] = sid
    groups = claims.get("groups") if isinstance(claims.get("groups"), list) else []
    session["user"] = {
        "sub": claims["sub"], "issuer": claims["iss"], "expires": claims["exp"],
        "admin": bool(tenant) and f"{tenant}-administradores" in groups,
        "assistant": bool(tenant) and f"{tenant}-servicio-asistente-ia" in groups,
    }
    return redirect(assistant_url(tenant))


CONFIG_TEXT = re.compile(r"[A-Za-z0-9._:/@+-]{1,80}")
KEY_PLACEHOLDER = "nexo-session"


def settings_payload(tenant):
    config = load_config(tenant)
    chat, speech = config.get("chat") or {}, config.get("speech") or {}
    return {
        "chat": {"base_url": chat.get("base_url", ""), "model": chat.get("model", ""),
                 "api_key_set": bool(chat.get("api_key"))},
        "speech": {"base_url": speech.get("base_url", ""), "model": speech.get("model", ""),
                   "voice": speech.get("voice", ""), "api_key_set": bool(speech.get("api_key"))},
    }


def _clean_text(value, label):
    value = (value or "").strip()
    if value and not CONFIG_TEXT.fullmatch(value):
        raise ValueError(f"{label} contiene caracteres no permitidos.")
    return value


def apply_settings(tenant, data):
    """Aplica los ajustes que el administrador hizo en AIRI. Lanza ValueError/EndpointError con un mensaje."""
    config = dict(load_config(tenant))
    for part in ("chat", "speech"):
        if part not in data:
            continue
        item = data[part]
        if not isinstance(item, dict):
            raise ValueError("Formato de ajustes inválido.")
        if item.get("reset") or not (item.get("base_url") or "").strip():
            config.pop(part, None)
            continue
        old = config.get(part) or {}
        key = (item.get("api_key") or "").strip()
        entry = {
            "provider": "openai", "base_url": public_https_url(item["base_url"]),
            "model": _clean_text(item.get("model"), "El modelo"),
            "api_key": old.get("api_key", "") if not key or key == KEY_PLACEHOLDER else key,
        }
        if part == "chat" and not entry["model"]:
            raise ValueError("Indica el modelo de lenguaje.")
        if part == "speech":
            entry["voice"] = _clean_text(item.get("voice"), "La voz")
        config[part] = entry
    save_config(tenant, config)


@app.route(f"{PREFIX}/api/<tenant>/settings", methods=["GET", "PUT"])
def tenant_settings(tenant):
    """Ajustes de la empresa. Solo el administrador; se editan desde la configuración original de AIRI."""
    company = tenants().get(tenant)
    if company is None or company.get("ai_provider", "gemini") is None:
        return jsonify(error="El asistente no está habilitado para esta empresa."), 404
    user = user_for(tenant)
    if not user:
        return jsonify(error="La sesión caducó. Vuelve a abrir el asistente."), 401
    if not user.get("admin"):
        return jsonify(error="Solo el administrador de la empresa puede configurar el asistente."), 403
    if request.method == "PUT":
        if request.headers.get("Origin", NEXO_URL) not in (NEXO_URL, "null") or not request.is_json:
            return jsonify(error="Origen o formato inválido."), 403
        try:
            apply_settings(tenant, request.get_json(silent=True) or {})
        except (ValueError, EndpointError) as exc:
            return jsonify(error=str(exc)), 400
    return jsonify(settings_payload(tenant))


def api_access(tenant):
    user = user_for(tenant)
    if not user:
        return None, None, (jsonify(error="La sesión caducó. Vuelve a abrir el asistente."), 401)
    if request.method == "POST" and (request.headers.get("Origin") != NEXO_URL or not request.is_json):
        return None, None, (jsonify(error="Origen o formato inválido."), 403)
    provider = provider_for(tenant, tenants().get(tenant), load_config(tenant))
    if not provider:
        return None, None, (jsonify(error="El asistente está deshabilitado para esta empresa."), 403)
    if not (user.get("assistant") or user.get("admin")):
        return None, None, (jsonify(error="El administrador de tu empresa no te ha dado acceso al asistente."), 403)
    if not provider.ready:
        return None, None, (jsonify(error="El proveedor de IA todavía no está configurado."), 503)
    return user, provider, None


def files_context(user, messages):
    """Archivos de Nextcloud de la persona usuaria relacionados con su última pregunta."""
    with FILE_TOKENS_LOCK:
        entry = FILE_TOKENS.get(session.get("files"))
    if not entry or entry["expires"] < time.time() or entry["issuer"] != user["issuer"]:
        return None
    return nextcloud.context_for(entry["token"], messages[-1]["text"]) or None


def message_history():
    body = request.get_json(silent=True)
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or not 1 <= len(messages) <= 5 or len(messages) % 2 == 0:
        return None
    for index, message in enumerate(messages):
        role = "user" if index % 2 == 0 else "assistant"
        if not isinstance(message, dict) or message.get("role") != role:
            return None
        message_text = message.get("text")
        limit = 2000 if role == "user" else 3000
        if not isinstance(message_text, str) or not 1 <= len(message_text.strip()) <= limit:
            return None
    return messages


@app.post(f"{PREFIX}/api/<tenant>/chat")
def chat(tenant):
    user, provider, error = api_access(tenant)
    if error:
        return error
    messages = message_history()
    if messages is None:
        return jsonify(error="La pregunta o el historial tienen un formato inválido."), 400
    try:
        answer = provider.reply(messages, files_context(user, messages))
    except ProviderError as exc:
        return jsonify(error=str(exc)), 502
    digest = hashlib.sha256(answer.encode()).hexdigest()
    ticket = speech_ticket.dumps([user["issuer"], user["sub"], digest])
    return jsonify(text=answer, speech_ticket=ticket)


@app.post(f"{PREFIX}/api/<tenant>/speech")
def speech(tenant):
    user, _, error = api_access(tenant)
    if error:
        return error
    payload = request.get_json(silent=True)
    text = payload.get("text") if isinstance(payload, dict) else None
    ticket = payload.get("ticket") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not 1 <= len(text) <= 3000 or not isinstance(ticket, str):
        return jsonify(error="Se requiere una respuesta válida."), 400
    try:
        claims = speech_ticket.loads(ticket, max_age=600)
    except BadData:
        return jsonify(error="La autorización de audio caducó."), 403
    if claims != [user["issuer"], user["sub"], hashlib.sha256(text.encode()).hexdigest()]:
        return jsonify(error="La autorización de audio no corresponde a esta respuesta."), 403
    return synthesize(tenant, text)


def synthesize(tenant, text):
    speech_config = load_config(tenant).get("speech") or {}
    content_type = "audio/wav"
    try:
        if speech_config.get("provider") == "openai" and speech_config.get("base_url"):
            audio = requests.post(
                public_https_url(speech_config["base_url"]) + "/audio/speech",
                headers={"Authorization": f"Bearer {speech_config['api_key']}"} if speech_config.get("api_key") else {},
                json={"model": speech_config.get("model") or "tts-1", "input": text,
                      "voice": speech_config.get("voice") or "alloy", "response_format": "wav"},
                timeout=(5, 115), allow_redirects=False,
            )
            content_type = audio.headers.get("Content-Type", content_type)
        else:
            audio = requests.post("http://pocket-tts:8000/speech", json={"text": text}, timeout=(3, 115))
        audio.raise_for_status()
    except (EndpointError, requests.RequestException):
        return jsonify(error="La voz no está disponible. Puedes volver a intentar reproducirla."), 503
    return audio.content, 200, {"Content-Type": content_type}


def stage_error(message, status):
    return jsonify(error={"message": message}), status


@app.get(f"{PREFIX}/api/<tenant>/v1/models")
def stage_models(tenant):
    _, _, error = api_access(tenant)
    if error:
        return error
    chat = load_config(tenant).get("chat") or {}
    speech = load_config(tenant).get("speech") or {}
    return jsonify(object="list", data=[
        {"id": model, "object": "model", "created": 0, "owned_by": "nexo"}
        for model in (chat.get("model") or "nexo-chat", speech.get("model") or "pocket-tts")
    ])


@app.post(f"{PREFIX}/api/<tenant>/v1/chat/completions")
def stage_chat(tenant):
    user, provider, error = api_access(tenant)
    if error:
        return error
    body = request.get_json(silent=True)
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or any(not isinstance(item, dict) for item in messages):
        return stage_error("Historial inválido.", 400)
    history = []
    for message in messages[-12:]:
        role, content = message.get("role"), message.get("content")
        if role not in ("user", "assistant"):
            continue
        if isinstance(content, list):
            content = " ".join(
                part["text"] for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            )
        if not isinstance(content, str) or not content.strip():
            continue
        if history and history[-1]["role"] == role:
            history.pop()
        if history or role == "user":
            history.append({"role": role, "text": content.strip()[:2000 if role == "user" else 3000]})
    if not history or history[-1]["role"] != "user":
        return stage_error("Se requiere una pregunta de texto.", 400)
    try:
        answer = provider.reply(history[-5:], files_context(user, history))
    except ProviderError as exc:
        return stage_error(str(exc), 502)
    meta = {"id": f"chatcmpl-{secrets.token_hex(12)}", "created": int(time.time()), "model": "nexo-chat"}
    if body.get("stream") is not True:
        return jsonify(**meta, object="chat.completion", choices=[
            {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"},
        ])

    def chunks():
        for delta, reason in [({"role": "assistant"}, None), ({"content": answer}, None), ({}, "stop")]:
            event = {**meta, "object": "chat.completion.chunk",
                     "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return Response(chunks(), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.post(f"{PREFIX}/api/<tenant>/v1/audio/speech")
def stage_speech(tenant):
    _, _, error = api_access(tenant)
    if error:
        return error
    body = request.get_json(silent=True)
    text = body.get("input") if isinstance(body, dict) else None
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000:
        return stage_error("Se requiere texto para sintetizar.", 400)
    return synthesize(tenant, text.strip())

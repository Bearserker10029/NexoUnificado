# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import jwt
import requests
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session
from itsdangerous import BadData, URLSafeTimedSerializer

from providers import PROVIDERS, ProviderError

PREFIX = "/airi"
CLIENT_ID = "nexo-assistant"
NEXO_URL = os.environ["NEXO_URL"].rstrip("/")
CALLBACK = f"{NEXO_URL}{PREFIX}/callback"
KEYCLOAK = "http://keycloak:8080"
REGISTRY = Path("/tenants/registry.json")
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


def begin_login(tenant):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    pending = {
        "tenant": tenant, "verifier": verifier, "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32), "expires": time.time() + AUTH_SECONDS,
    }
    session["oidc"] = pending
    query = urlencode({
        "client_id": CLIENT_ID, "redirect_uri": CALLBACK, "response_type": "code",
        "scope": "openid", "state": pending["state"], "nonce": pending["nonce"],
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
    company = tenants().get(tenant) if tenant else {}
    if company is None:
        abort(404)
    if not user_for(tenant):
        return begin_login(tenant)
    provider_name = company.get("ai_provider")
    provider = PROVIDERS.get(provider_name) if isinstance(provider_name, str) else None
    status = ""
    if not provider:
        status = "El asistente está deshabilitado para tu empresa."
    elif not provider.ready:
        status = "El equipo de Nexo todavía no ha configurado Gemini."
    elif (STAGE / "index.html").is_file():
        return redirect(f"{PREFIX}/stage/?{urlencode({'tenant': tenant})}#/")
    return render_template(
        "index.html", tenant=tenant, company=company.get("display_name", "Nexo Unificado"),
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
    company = tenants().get(tenant, {})
    provider_name = company.get("ai_provider")
    provider = PROVIDERS.get(provider_name) if isinstance(provider_name, str) else None
    if not provider or not provider.ready:
        return redirect(assistant_url(tenant))
    index_file = STAGE / "index.html"
    if not index_file.is_file():
        abort(404)
    profile = hmac.new(app.secret_key.encode(), json.dumps([user["issuer"], user["sub"]]).encode(), "sha256").hexdigest()
    html = index_file.read_bytes().replace(
        b"<head>", f'<head><meta name="nexo-profile" content="{profile}">'.encode(), 1,
    )
    response = Response(html, mimetype="text/html")
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'wasm-unsafe-eval' {stage_script_hashes()}; "
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
    session["user"] = {
        "sub": claims["sub"], "issuer": claims["iss"], "expires": claims["exp"],
    }
    return redirect(assistant_url(tenant))


def api_access(tenant):
    user = user_for(tenant)
    if not user:
        return None, None, (jsonify(error="La sesión caducó. Vuelve a abrir el asistente."), 401)
    if request.method == "POST" and (request.headers.get("Origin") != NEXO_URL or not request.is_json):
        return None, None, (jsonify(error="Origen o formato inválido."), 403)
    company = tenants().get(tenant, {})
    provider_name = company.get("ai_provider")
    provider = PROVIDERS.get(provider_name) if isinstance(provider_name, str) else None
    if not provider:
        return None, None, (jsonify(error="El asistente está deshabilitado para esta empresa."), 403)
    if not provider.ready:
        return None, None, (jsonify(error="El proveedor de IA todavía no está configurado."), 503)
    return user, provider, None


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
        answer = provider.reply(messages)
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
    return synthesize(text)


def synthesize(text):
    try:
        audio = requests.post("http://pocket-tts:8000/speech", json={"text": text}, timeout=(3, 115))
        audio.raise_for_status()
    except requests.RequestException:
        return jsonify(error="La voz no está disponible. Puedes volver a intentar reproducirla."), 503
    return audio.content, 200, {"Content-Type": "audio/wav"}


def stage_error(message, status):
    return jsonify(error={"message": message}), status


@app.get(f"{PREFIX}/api/<tenant>/v1/models")
def stage_models(tenant):
    _, _, error = api_access(tenant)
    if error:
        return error
    return jsonify(object="list", data=[
        {"id": model, "object": "model", "created": 0, "owned_by": "nexo"}
        for model in ("nexo-chat", "pocket-tts")
    ])


@app.post(f"{PREFIX}/api/<tenant>/v1/chat/completions")
def stage_chat(tenant):
    _, provider, error = api_access(tenant)
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
        answer = provider.reply(history[-5:])
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
    return synthesize(text.strip())

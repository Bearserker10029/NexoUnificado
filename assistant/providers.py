# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import ipaddress
import json
import os
import re
import socket
from urllib.parse import urlsplit

import requests


class ProviderError(Exception):
    pass


SYSTEM_PROMPT = (
    "Eres el Asistente IA de Nexo Unificado. Responde en español, "
    "en texto plano apto para lectura en voz alta y en menos de 150 palabras."
)


class Gemini:
    def __init__(self, tenant=None, key=None, model=None):
        if key:
            self.key = key.strip()
            self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
            if not re.fullmatch(r"[a-z0-9.-]+", self.model):
                raise ValueError("Modelo de Gemini inválido")
            return
        raw_keys = os.getenv("GEMINI_API_KEYS", "").strip()
        self.key = os.getenv("GEMINI_API_KEY", "").strip()
        if raw_keys:
            try:
                keys = json.loads(raw_keys)
                key = keys.get(tenant) if isinstance(keys, dict) else None
            except ValueError:
                key = None
            self.key = key.strip() if isinstance(key, str) else ""
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        if not re.fullmatch(r"[a-z0-9.-]+", self.model):
            raise ValueError("GEMINI_MODEL inválido")

    @property
    def ready(self):
        return bool(self.key)

    def reply(self, messages):
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.key},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [
                        {"role": {"user": "user", "assistant": "model"}[m["role"]],
                         "parts": [{"text": m["text"]}]}
                        for m in messages
                    ],
                    "generationConfig": {"maxOutputTokens": 512, "thinkingConfig": {"thinkingLevel": "MINIMAL"}},
                },
                timeout=(5, 45),
                allow_redirects=False,
            )
            response.raise_for_status()
            parts = response.json()["candidates"][0]["content"]["parts"]
            answer = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if answer:
                return answer[:3000]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Gemini no pudo generar una respuesta.") from exc
        raise ProviderError("Gemini no devolvió una respuesta de texto.")


class EndpointError(ValueError):
    pass


def public_https_url(url):
    """Valida una URL que la empresa configura: solo HTTPS hacia direcciones públicas.

    Evita que el servidor del asistente consulte la red interna (SSRF) por orden de un administrador.
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise EndpointError("La URL debe usar HTTPS y no incluir credenciales.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise EndpointError("No se pudo resolver el servidor indicado.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise EndpointError("La URL debe apuntar a un servidor público, no a la red interna.")
    return url.strip().rstrip("/")


class OpenAICompatible:
    """Cualquier servicio con la API de chat de OpenAI (OpenAI, Azure, vLLM, LM Studio expuesto, etc.)."""

    ready = True

    def __init__(self, base_url, key, model):
        self.base_url = base_url
        self.key = key
        self.model = model

    def reply(self, messages):
        try:
            response = requests.post(
                public_https_url(self.base_url) + "/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *[{"role": m["role"], "content": m["text"]} for m in messages],
                    ],
                    "max_tokens": 400,
                    "temperature": 0.2,
                },
                timeout=(5, 60),
                allow_redirects=False,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if isinstance(answer, str) and answer.strip():
                return answer.strip()[:3000]
        except (EndpointError, requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("El modelo configurado por la empresa no pudo generar una respuesta.") from exc
        raise ProviderError("El modelo configurado por la empresa no devolvió texto.")


def custom_provider(config):
    """Proveedor definido por el administrador de la empresa, o None para usar el predeterminado."""
    chat = (config or {}).get("chat") or {}
    kind = chat.get("provider")
    if kind == "gemini" and chat.get("api_key"):
        return Gemini(key=chat["api_key"], model=chat.get("model") or None)
    if kind == "openai" and chat.get("base_url") and chat.get("model"):
        return OpenAICompatible(chat["base_url"], chat.get("api_key", ""), chat["model"])
    return None


class Groq(OpenAICompatible):
    """Groq (API compatible con OpenAI) con la clave que define el proveedor del servicio."""

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, tenant=None):
        raw_keys = os.getenv("GROQ_API_KEYS", "").strip()
        key = os.getenv("GROQ_API_KEY", "").strip()
        if raw_keys:
            try:
                keys = json.loads(raw_keys)
                value = keys.get(tenant) if isinstance(keys, dict) else None
            except ValueError:
                value = None
            key = value.strip() if isinstance(value, str) else ""
        model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", model):
            raise ValueError("GROQ_MODEL inválido")
        super().__init__(self.BASE_URL, key, model)

    @property
    def ready(self):
        return bool(self.key)


class Fallback:
    """Prueba los proveedores del servicio en orden; si uno falla o no tiene cuota, responde el siguiente."""

    def __init__(self, providers):
        self.providers = providers

    @property
    def ready(self):
        return any(provider.ready for provider in self.providers)

    def reply(self, messages):
        last = None
        for provider in self.providers:
            if not provider.ready:
                continue
            try:
                return provider.reply(messages)
            except ProviderError as exc:
                last = exc
        raise last or ProviderError("El proveedor de IA todavía no está configurado.")


PROVIDERS = {"gemini": Gemini, "groq": Groq}


def provider_for(tenant, company, config=None):
    if company is None:
        return None
    custom = custom_provider(config)
    if custom is not None:
        return custom
    names = company.get("ai_provider", "gemini")
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or not names or any(name not in PROVIDERS for name in names):
        return None
    built = [PROVIDERS[name](tenant) for name in names]
    return built[0] if len(built) == 1 else Fallback(built)

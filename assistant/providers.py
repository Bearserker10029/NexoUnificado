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


class Ollama:
    ready = True

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

    def reply(self, messages):
        try:
            response = requests.post(
                "http://ollama:11434/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *[{"role": message["role"], "content": message["text"]} for message in messages],
                    ],
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {"num_gpu": 0, "num_ctx": 2048, "num_predict": 180, "temperature": 0.2},
                },
                timeout=(3, 100),
                allow_redirects=False,
            )
            if response.status_code == 404:
                raise ProviderError("Ollama todavía no tiene el modelo local. Espera a que termine la descarga.")
            response.raise_for_status()
            answer = response.json()["message"]["content"]
            if isinstance(answer, str) and answer.strip():
                return answer.strip()[:3000]
        except requests.Timeout as exc:
            raise ProviderError("El modelo local tardó demasiado. Intenta otra vez.") from exc
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Ollama no pudo generar una respuesta.") from exc
        raise ProviderError("Ollama no devolvió una respuesta de texto.")


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


PROVIDERS = {"gemini": Gemini, "ollama": lambda _: Ollama()}


def provider_for(tenant, company, config=None):
    if company is None:
        return None
    custom = custom_provider(config)
    if custom is not None:
        return custom
    name = company.get("ai_provider", "ollama")
    factory = PROVIDERS.get(name) if isinstance(name, str) else None
    return factory(tenant) if factory else None

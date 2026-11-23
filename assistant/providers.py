# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re

import requests


class ProviderError(Exception):
    pass


SYSTEM_PROMPT = (
    "Eres el Asistente IA de Nexo Unificado. Responde en español, "
    "en texto plano apto para lectura en voz alta y en menos de 150 palabras."
)


class Gemini:
    def __init__(self, tenant=None):
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


PROVIDERS = {"gemini": Gemini, "ollama": lambda _: Ollama()}


def provider_for(tenant, company):
    if company is None:
        return None
    name = company.get("ai_provider", "ollama")
    factory = PROVIDERS.get(name) if isinstance(name, str) else None
    return factory(tenant) if factory else None

# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import os
import re

import requests


class ProviderError(Exception):
    pass


class Gemini:
    def __init__(self):
        self.key = os.getenv("GEMINI_API_KEY", "").strip()
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
                    "systemInstruction": {"parts": [{"text": (
                        "Eres el Asistente IA de Nexo Unificado. Responde en español, "
                        "en texto plano apto para lectura en voz alta y en menos de 150 palabras."
                    )}]},
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


PROVIDERS = {"gemini": Gemini()}

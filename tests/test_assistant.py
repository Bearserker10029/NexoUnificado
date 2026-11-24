# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
import importlib
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://nexo.test:8443"
sys.path.insert(0, str(ROOT / "assistant"))
try:
    with patch.dict(os.environ, {"NEXO_URL": ORIGIN}):
        assistant = importlib.import_module("app")
        providers = importlib.import_module("providers")
finally:
    sys.path.pop(0)


class AssistantTest(unittest.TestCase):
    def setUp(self):
        self.client = assistant.app.test_client()
        self.provider = SimpleNamespace(ready=True, reply=Mock(return_value="Hola desde Nexo."))
        self.enterContext(patch.object(assistant, "REGISTRY", ROOT / "tenants" / "registry.json"))
        self.enterContext(patch.dict(providers.PROVIDERS, {"gemini": lambda _: self.provider}))

    def test_provider_selection_defaults_only_for_registered_tenants(self):
        self.assertIs(providers.provider_for("acme", {}), self.provider)
        self.assertIsNone(providers.provider_for("", None))
        self.assertIsNone(providers.provider_for("beta", {"ai_provider": None}))
        self.assertIsNone(providers.provider_for("beta", {"ai_provider": "invalid"}))

    def test_gemini_uses_the_key_of_each_tenant(self):
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "legacy-fixture",
            "GEMINI_API_KEYS": '{"acme":"acme-fixture"}',
        }):
            self.assertEqual(providers.Gemini("acme").key, "acme-fixture")
            self.assertFalse(providers.Gemini("beta").ready)

    def test_company_model_replaces_the_default_provider(self):
        config = {"chat": {"provider": "openai", "base_url": "https://api.example.test/v1", "model": "m", "api_key": "k"}}
        self.assertIsInstance(providers.provider_for("acme", {}, config), providers.OpenAICompatible)
        with self.assertRaises(providers.EndpointError):
            providers.public_https_url("https://127.0.0.1/v1")

    def test_fallback_uses_the_next_provider_when_one_fails(self):
        broken = SimpleNamespace(ready=True, reply=Mock(side_effect=providers.ProviderError("sin cuota")))
        working = SimpleNamespace(ready=True, reply=Mock(return_value="Respuesta de respaldo."))
        unconfigured = SimpleNamespace(ready=False, reply=Mock())
        chain = providers.Fallback([unconfigured, broken, working])
        self.assertTrue(chain.ready)
        self.assertEqual(chain.reply([{"role": "user", "text": "Hola"}]), "Respuesta de respaldo.")
        unconfigured.reply.assert_not_called()
        with self.assertRaises(providers.ProviderError):
            providers.Fallback([broken]).reply([{"role": "user", "text": "Hola"}])
        self.assertFalse(providers.Fallback([unconfigured]).ready)

    def test_groq_uses_the_provider_key_and_the_openai_compatible_api(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "fixture", "GROQ_MODEL": "openai/gpt-oss-20b"}):
            groq = providers.Groq("acme")
        self.assertTrue(groq.ready)
        with patch.object(providers, "public_https_url", side_effect=lambda url: url),                 patch.object(providers.requests, "post") as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": "Hola desde Groq."}}]}
            self.assertEqual(groq.reply([{"role": "user", "text": "Hola"}]), "Hola desde Groq.")
        self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "openai/gpt-oss-20b")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer fixture"})

    def post(self, path, payload, origin=ORIGIN):
        return self.client.post(path, base_url=ORIGIN, json=payload, headers={"Origin": origin})

    def login_as(self, tenant):
        with self.client.session_transaction(base_url=ORIGIN) as session:
            session["user"] = {"issuer": assistant.issuer(tenant),
                               "sub": "test-user", "expires": time.time() + 60}

    def test_login_selects_tenant_realm_and_uses_pkce(self):
        response = self.client.get("/airi/?tenant=acme", base_url=ORIGIN)
        self.assertEqual(response.status_code, 302)
        target = urlsplit(response.location)
        params = parse_qs(target.query)
        self.assertEqual(target.path, "/keycloak/realms/nexo-acme/protocol/openid-connect/auth")
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["redirect_uri"], [f"{ORIGIN}/airi/callback"])
        self.assertEqual(self.client.get("/airi/callback?state=invalid", base_url=ORIGIN).status_code, 400)

    def test_disabled_and_cross_tenant_requests_do_not_reach_provider(self):
        messages = {"messages": [{"role": "user", "text": "Hola"}]}
        self.login_as("beta")
        self.assertIn("deshabilitado", self.client.get("/airi/?tenant=beta", base_url=ORIGIN).text)
        self.assertEqual(self.post("/airi/api/beta/chat", messages).status_code, 403)
        self.assertEqual(self.post("/airi/api/acme/chat", messages).status_code, 401)
        self.login_as("acme")
        self.assertEqual(self.post("/airi/api/acme/chat", messages, "https://otro.test").status_code, 403)
        self.provider.reply.assert_not_called()

    def test_speech_ticket_only_applies_to_the_exact_reply(self):
        self.login_as("acme")
        chat = self.post("/airi/api/acme/chat", {"messages": [{"role": "user", "text": "Hola"}]})
        self.assertEqual(chat.status_code, 200)
        answer = chat.get_json()
        ticket = answer["speech_ticket"]
        endpoint = "/airi/api/acme/speech"
        with patch.object(assistant.requests, "post") as pocket:
            self.assertEqual(self.post(endpoint, {"text": "Distinto", "ticket": ticket}).status_code, 403)
            pocket.assert_not_called()
            pocket.return_value.content = b"RIFF"
            audio = self.post(endpoint, {"text": answer["text"], "ticket": ticket})
            self.assertEqual(audio.content_type, "audio/wav")
            self.assertEqual(audio.data, b"RIFF")

    def test_airi_chat_stream_is_tenant_scoped(self):
        endpoint = "/airi/api/acme/v1/chat/completions"
        body = {"stream": True, "messages": [
            {"role": "system", "content": "Contexto del personaje"},
            {"role": "user", "content": [{"type": "text", "text": "Hola"}]},
        ]}
        self.login_as("beta")
        self.assertEqual(self.post(endpoint, body).status_code, 401)
        self.login_as("acme")
        response = self.post(endpoint, body)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertIn("Hola desde Nexo.", response.text)
        self.assertTrue(response.text.endswith("data: [DONE]\n\n"))
        self.provider.reply.assert_called_once_with([{"role": "user", "text": "Hola"}])

    def test_airi_voice_uses_pocket_tts(self):
        self.login_as("acme")
        endpoint = "/airi/api/acme/v1/audio/speech"
        with patch.object(assistant.requests, "post") as pocket:
            pocket.return_value.content = b"RIFF"
            response = self.post(endpoint, {"input": "Hola", "voice": "lola"})
        self.assertEqual(response.content_type, "audio/wav")
        self.assertEqual(pocket.call_args.kwargs["json"], {"text": "Hola"})

    def test_airi_shell_requires_the_enabled_company_session(self):
        endpoint = "/airi/stage/?tenant=acme"
        self.login_as("beta")
        self.assertEqual(self.client.get(endpoint, base_url=ORIGIN).status_code, 302)
        self.login_as("acme")
        with TemporaryDirectory() as directory, patch.object(assistant, "STAGE", Path(directory)):
            (Path(directory) / "index.html").write_text("<head><script>boot()</script></head>")
            assistant.stage_script_hashes.cache_clear()
            self.addCleanup(assistant.stage_script_hashes.cache_clear)
            response = self.client.get(endpoint, base_url=ORIGIN)
            self.assertEqual(response.status_code, 200)
            self.assertIn('name="nexo-profile"', response.text)
            self.assertIn("'sha256-", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(self.client.get("/airi/stage/index.html", base_url=ORIGIN).status_code, 404)

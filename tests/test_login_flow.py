import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class LoginFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        environment = {
            "NEXO_URL": "https://nexo.test:8443",
            "KC_VOIP_CLIENT_SECRET": "test-client-secret",
            "VOIP_SESSION_SECRET": "test-session-secret",
            "VOIP_AMI_USER": "test-ami-user",
            "VOIP_AMI_SECRET": "test-ami-secret",
            "KC_ADMIN_PASSWORD": "test-admin-password",
        }
        with patch.dict(os.environ, environment):
            spec = importlib.util.spec_from_file_location(
                "nexo_voip_gateway_login_test", ROOT / "voip-gateway/app.py"
            )
            cls.gateway = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.gateway)
        cls.gateway.app.config.update(TESTING=True)
        cls.gateway.app.template_folder = str(ROOT / "voip-gateway/templates")
        cls.client = cls.gateway.app.test_client()

    def test_redirige_a_su_empresa_y_precarga_el_identificador(self):
        with patch.object(self.gateway, "_find_login_provider", return_value=3) as find_provider:
            response = self.client.post(
                "/entrar", data={"identifier": "Beta.User@Example.test"}
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["Location"],
            "/docs/apps/user_oidc/login/3?login_hint=beta.user%40example.test",
        )
        find_provider.assert_called_once_with("beta.user@example.test")

    def test_conserva_el_identificador_si_no_existe_la_cuenta(self):
        with patch.object(self.gateway, "_find_login_provider", return_value=None):
            response = self.client.post(
                "/entrar", data={"identifier": "Desconocido@Example.test"}
            )
        self.assertEqual(response.status_code, 404)
        self.assertIn('value="desconocido@example.test"', response.get_data(as_text=True))

    def test_keycloak_oculta_solo_los_controles_nativos_de_edge(self):
        css = (ROOT / "keycloak/themes/nexo/login/resources/css/nexo-login.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("::-ms-reveal", css)
        self.assertIn("::-ms-clear", css)
        properties = (ROOT / "keycloak/themes/nexo/login/theme.properties").read_text(
            encoding="utf-8"
        )
        self.assertIn("parent=keycloak.v2", properties)
        self.assertIn("css/nexo-login.css", properties)


if __name__ == "__main__":
    unittest.main()

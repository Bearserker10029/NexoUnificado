import importlib.util
import json
import py_compile
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class MultiempresaEstatico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, "scripts/nexo-tenant.py", "render"], cwd=ROOT, check=True)
        cls.registry = json.loads((ROOT / "tenants/registry.json").read_text(encoding="utf-8"))
        cls.tenants = {item["name"]: item for item in cls.registry["tenants"]}
        with open(ROOT / "docker-compose.yml", encoding="utf-8") as base:
            base_data = yaml.safe_load(base)
        with open(ROOT / "docker-compose.multiempresa.yml", encoding="utf-8") as overlay:
            overlay_data = yaml.safe_load(overlay)
        with open(ROOT / "docker-compose.override.yml", encoding="utf-8") as automatic:
            automatic_data = yaml.safe_load(automatic)
        if automatic_data != overlay_data:
            raise AssertionError("El override automatico debe coincidir con la capa multiempresa")
        for service in ("synapse-acme", "synapse-beta", "element-acme", "element-beta"):
            if service not in automatic_data["services"]:
                raise AssertionError(f"Falta {service} en el override automatico")
        cls.compose = {**base_data, "services": {**base_data["services"], **overlay_data["services"]}}

    def test_empresas_y_rangos(self):
        self.assertEqual(self.tenants["acme"]["range_prefix"], 1)
        self.assertEqual(self.tenants["beta"]["range_prefix"], 2)
        self.assertEqual(len({t["range_prefix"] for t in self.tenants.values()}), len(self.tenants))

    def test_dialplan_interempresas_y_cdr(self):
        for name, prefix in (("acme", 1), ("beta", 2)):
            text = (ROOT / f"tenants/{name}/asterisk/extensions.conf").read_text(encoding="utf-8")
            self.assertIn(f"[tenant-{name}]", text)
            self.assertIn(f"exten => _{prefix}XXX", text)
            self.assertNotIn("Dial(PJSIP/${EXTEN},", text)
            self.assertIn("reservada a Element", text)
            self.assertIn("PJSIP_ENDPOINT(${EXTEN:1},context)", text)
            self.assertIn("exten => _9ZXXX", text)
            self.assertIn("CDR(tenant_origen)", text)
            self.assertIn("CDR(origen)", text)
            self.assertIn("CDR(destino)", text)
            self.assertIn("Dial(PJSIP/${EXTEN:1}", text)
            self.assertIn("misma-empresa", text)
        custom = (ROOT / "asterisk/cdr_custom.conf").read_text(encoding="utf-8")
        for field in ("start", "src", "dst", "accountcode", "userfield", "billsec"):
            self.assertRegex(custom, rf"(?:^|,){{0,1}}{field}(?:,|$)")

    def test_endpoints_tls_y_wss_sin_udp_5060(self):
        ports = []
        for service in self.compose["services"].values():
            ports.extend(service.get("ports", []) or [])
        self.assertFalse(any("5060" in str(port) for port in ports))
        self.assertFalse(any("5061" in str(port) for port in ports), "SIP TLS debe quedar interno")
        pjsip = (ROOT / "asterisk/pjsip.conf.template").read_text(encoding="utf-8")
        self.assertIn("protocol=tls", pjsip)
        self.assertIn("bind=0.0.0.0:5061", pjsip)
        self.assertIn("protocol=ws", pjsip)
        for name, extension in (("acme", 1001), ("beta", 2001)):
            text = (ROOT / f"tenants/{name}/asterisk/pjsip.conf.template").read_text(encoding="utf-8")
            self.assertIn(f"[tenant-{name}-endpoint](!)", text)
            self.assertIn(f"[{extension}](tenant-{name}-endpoint)", text)
            self.assertIn("transport=transport-tls", text)
        gateway = (ROOT / "voip-gateway/app.py").read_text(encoding="utf-8")
        self.assertIn("transport=transport-ws", gateway)
        self.assertIn('context = f"tenant-{tenant}" if tenant else "internal"', gateway)

    def test_homeservers_sin_federacion(self):
        servers = []
        for name in ("acme", "beta"):
            text = (ROOT / f"tenants/{name}/matrix/homeserver.yaml.template").read_text(encoding="utf-8")
            config = yaml.safe_load(text)
            servers.append(config["server_name"])
            self.assertEqual(config["server_name"], f"{name}.nexo.local")
            self.assertFalse(config["enable_registration"])
            self.assertNotIn("federation", config["listeners"][0]["resources"][0]["names"])
            self.assertEqual(config["oidc_providers"][0]["client_id"], "synapse")
            self.assertIn(f"/realms/nexo-{name}", config["oidc_providers"][0]["issuer"])
        self.assertEqual(len(set(servers)), 2)

    def test_homeservers_esperan_el_certificado_publico(self):
        for name in ("synapse", "synapse-acme", "synapse-beta"):
            service = self.compose["services"][name]
            self.assertIn("./certs/public:/certs:ro", service["volumes"])
            self.assertEqual(service["depends_on"]["certs"]["condition"], "service_completed_successfully")

    def test_realms_y_grupos_contratados(self):
        for name in ("acme", "beta"):
            realm = json.loads((ROOT / f"tenants/{name}/keycloak/realm.json.template").read_text(encoding="utf-8"))
            self.assertEqual(realm["realm"], f"nexo-{name}")
            groups = {group["name"] for group in realm["groups"]}
            services = {f"{name}-servicio-{s}" for s in self.tenants[name]["services"]}
            admin = next(group for group in realm["groups"] if group["name"] == f"{name}-administradores")
            self.assertEqual(admin["clientRoles"], {"realm-management": ["manage-users"]})
            self.assertEqual(groups, services | {admin["name"]})
            self.assertIn("nextcloud", {client["clientId"] for client in realm["clients"]})

    def test_element_1a1_y_jitsi_aislados(self):
        for name in ("acme", "beta"):
            element = json.loads((ROOT / f"tenants/{name}/matrix/element-config.json.template").read_text(encoding="utf-8"))
            self.assertEqual(element["default_server_config"]["m.homeserver"]["server_name"], f"{name}.nexo.local")
            nginx = (ROOT / f"tenants/nginx/tenant-{name}.conf").read_text(encoding="utf-8")
            self.assertIn(f"proxy_pass http://synapse-{name}:8008/_matrix/", nginx)
            self.assertIn(f"proxy_pass http://jitsi-web-{name}:8000", nginx)
            self.assertIn("auth_request", nginx)
            for component in ("jitsi-web", "jitsi-prosody", "jicofo", "jvb"):
                self.assertIn(f"{component}-{name}", self.compose["services"])

    def test_proxy_conserva_base_e_incluye_empresas(self):
        nginx = (ROOT / "nginx/conf.d/default.conf").read_text(encoding="utf-8")
        for legacy in ("location /_matrix/", "location /element/", "location /jitsi/", "location = /asterisk/ws"):
            self.assertIn(legacy, nginx)
        self.assertIn("include /etc/nginx/tenants/*.conf", nginx)
        self.assertIn("dialplan show internal", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_python_valido(self):
        for path in ("scripts/nexo-tenant.py", "voip-gateway/app.py", "tests/test_multiempresa.py"):
            py_compile.compile(str(ROOT / path), doraise=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Pruebas funcionales H10. Requiere el despliegue activo y tokens Matrix de laboratorio."""
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("NEXO_TEST_URL", "https://127.0.0.1:8443").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "evidencias/h10/funcional.txt"
TOKENS = {name: os.environ.get(f"{name}_MATRIX_TOKEN") for name in ("ACME1", "ACME2", "BETA1")}
CONTEXT = ssl._create_unverified_context()  # Solo certificado autofirmado del laboratorio.


def api(tenant, path, token, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}/{tenant}/_matrix/client/v3{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CONTEXT, timeout=20) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return error.code, payload


def docker(*args):
    executable = os.environ.get("DOCKER_CLI", "docker")
    return subprocess.run([executable, *args], check=True, text=True, capture_output=True).stdout


def login_tokens():
    for label, tenant, username in (("ACME1", "acme", "acme1"), ("ACME2", "acme", "acme2"), ("BETA1", "beta", "beta1")):
        if TOKENS[label]:
            continue
        password = os.environ.get(f"{label}_PASSWORD")
        if not password:
            raise SystemExit("Defina tokens Matrix o las claves ACME1_PASSWORD, ACME2_PASSWORD y BETA1_PASSWORD")
        status, body = api(tenant, "/login", "", "POST", {
            "type": "m.login.password", "identifier": {"type": "m.id.user", "user": username},
            "password": password, "initial_device_display_name": "Validación H10"})
        if status != 200:
            raise RuntimeError(f"Login Matrix {label}: HTTP {status} {body}")
        TOKENS[label] = body["access_token"]


def main():
    login_tokens()
    lines = [f"URL: {BASE}", ""]
    for label, tenant in (("ACME1", "acme"), ("ACME2", "acme"), ("BETA1", "beta")):
        status, body = api(tenant, "/account/whoami", TOKENS[label])
        assert status == 200 and body["user_id"].endswith(f":{tenant}.nexo.local"), (label, status, body)
        lines.append(f"IDENTIDAD {label}: {body['user_id']}")

    status, room = api("acme", "/createRoom", TOKENS["ACME1"], "POST", {
        "invite": ["@acme2:acme.nexo.local"], "is_direct": True, "preset": "trusted_private_chat"})
    assert status == 200, room
    room_id = room["room_id"]
    lines.append(f"DM ACME creada: {room_id}")
    status, joined = api("acme", f"/rooms/{room_id}/join", TOKENS["ACME2"], "POST", {})
    assert status == 200, joined
    lines.append("ACME2 aceptó la sala directa")
    status, call = api("acme", f"/rooms/{room_id}/send/m.call.invite/nexo-h10-{int(time.time())}",
        TOKENS["ACME1"], "PUT", {"call_id": "nexo-h10", "version": 0, "lifetime": 60000,
            "offer": {"type": "offer", "sdp": "v=0\r\n"}})
    assert status == 200, call
    lines.append(f"SEÑALIZACIÓN m.call.invite ACME1->ACME2: {call['event_id']} (audio/video se verifica en Element)")

    status, body = api("acme", "/createRoom", TOKENS["ACME1"], "POST", {
        "invite": ["@beta1:beta.nexo.local"], "is_direct": True, "preset": "trusted_private_chat"})
    assert status >= 400, (status, body)
    lines.append(f"CHAT ACME->BETA BLOQUEADO: HTTP {status} {json.dumps(body, ensure_ascii=False)}")
    status, body = api("acme", "/user_directory/search", TOKENS["ACME1"], "POST",
                       {"search_term": "beta1", "limit": 10})
    assert status == 200 and not any(item["user_id"].endswith(":beta.nexo.local") for item in body.get("results", [])), body
    lines.append("DIRECTORIO ACME: beta1 no visible")

    lines.append("CONTACTOS SIP:\n" + docker("exec", "nexo-asterisk", "asterisk", "-rx", "pjsip show contacts"))
    lines.append("LLAMADA ACME 1001 -> BETA 2001 mediante 92001 (canal Local temporal; sin audio si no hay registros SIP)")
    docker("exec", "nexo-asterisk", "asterisk", "-rx",
           "dialplan add extension 9100,1,Set(CALLERID(num)=1001) into tenant-acme")
    docker("exec", "nexo-asterisk", "asterisk", "-rx",
           "dialplan add extension 9100,2,Goto(92001,1) into tenant-acme")
    try:
        lines.append(docker("exec", "nexo-asterisk", "asterisk", "-rx",
                            "channel originate Local/9100@tenant-acme application Wait 5"))
        time.sleep(15)
        cdr = docker("exec", "nexo-asterisk", "sh", "-c", "tail -n 20 /var/log/asterisk/cdr-custom/interempresas.csv")
        assert "acme" in cdr and "origen=1001" in cdr and "destino=2001" in cdr, cdr
        lines.append("CDR INTEREMPRESAS:\n" + cdr)
    finally:
        docker("exec", "nexo-asterisk", "asterisk", "-rx", "dialplan remove extension 9100@tenant-acme")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Pruebas superadas; evidencia: {OUT}")


if __name__ == "__main__":
    main()

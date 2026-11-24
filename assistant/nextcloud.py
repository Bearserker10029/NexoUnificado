# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
"""Lee archivos de la persona usuaria en Nextcloud con su propio token de Keycloak (permisos de Nextcloud intactos)."""
import io
import os
import re
import zipfile
from urllib.parse import quote

import requests

BASE = os.getenv("NEXTCLOUD_INTERNAL_URL", "").rstrip("/")
HOST = os.getenv("NEXTCLOUD_HOST", "")
MAX_BYTES = 2 * 1024 * 1024
MAX_FILES = 3
MAX_CHARS = 4000
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log"}
STOPWORDS = {
    "para", "como", "cual", "cuales", "donde", "esta", "este", "estos", "esto", "hola", "sobre", "tiene",
    "tengo", "quiero", "puedes", "dime", "archivo", "archivos", "documento", "documentos", "nextcloud",
    "mis", "que", "los", "las", "una", "uno", "con", "por", "del", "resumen", "resume", "lee", "busca",
}


def enabled():
    return bool(BASE)


def _get(path, token, **kwargs):
    headers = {"Authorization": f"Bearer {token}", "OCS-APIRequest": "true", "Accept": "application/json"}
    if HOST:
        headers["Host"] = HOST
    return requests.get(BASE + path, headers=headers, timeout=(3, 8), allow_redirects=False, **kwargs)


def keywords(question):
    words = []
    for word in re.findall(r"[\wáéíóúñü]{4,}", question.lower()):
        if word not in STOPWORDS and word not in words:
            words.append(word)
    return sorted(words, key=len, reverse=True)[:3]


def _extract(name, data):
    ext = os.path.splitext(name.lower())[1]
    if ext in TEXT_EXT:
        return data.decode("utf-8", "replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:10])
    if ext == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.open("word/document.xml").read(MAX_BYTES).decode("utf-8", "replace")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n")))
    return None


def _download(uid, path, token):
    response = _get(f"/remote.php/dav/files/{quote(uid, safe='')}{quote(path)}", token, stream=True)
    try:
        if response.status_code != 200 or int(response.headers.get("Content-Length") or 0) > MAX_BYTES:
            return None
        return response.raw.read(MAX_BYTES + 1, decode_content=True)[:MAX_BYTES]
    finally:
        response.close()


def context_for(token, question):
    """Texto de los archivos que coinciden con la pregunta, o "" si no hay nada (nunca falla la respuesta)."""
    terms = keywords(question)
    if not (enabled() and token and terms):
        return ""
    try:
        uid = _get("/ocs/v2.php/cloud/user?format=json", token).json()["ocs"]["data"]["id"]
        found = {}
        for term in terms:
            reply = _get(f"/ocs/v2.php/search/providers/files/search?term={quote(term)}&limit=5", token)
            for entry in reply.json()["ocs"]["data"]["entries"]:
                path = (entry.get("attributes") or {}).get("path") or ""
                if path.startswith("/") and ".." not in path.split("/") and path not in found:
                    found[path] = entry.get("title") or os.path.basename(path)
        parts = []
        for path, name in found.items():
            if len(parts) >= MAX_FILES:
                break
            if os.path.splitext(name.lower())[1] not in TEXT_EXT | {".pdf", ".docx"}:
                continue
            data = _download(uid, path, token)
            text = _extract(name, data) if data else None
            if text and text.strip():
                parts.append(f"--- Archivo: {path} ---\n{text.strip()[:MAX_CHARS]}")
        return "\n\n".join(parts)
    except Exception:  # un fallo de Nextcloud o de un formato no debe impedir que la IA responda
        return ""

"""Genera el codigo TOTP (RFC 6238, SHA1, 6 digitos, 30 s) de una clave base32.
Solo para pruebas H7 sin telefono: python scripts/h7-totp.py "<CLAVE-BASE32-DE-KEYCLOAK>"
"""
import base64, hmac, hashlib, struct, sys, time

def totp(secret: str, t: float | None = None) -> str:
    key = base64.b32decode(secret.replace(" ", "").upper())
    counter = int((t if t is not None else time.time()) // 30)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return f"{(struct.unpack('>I', mac[off:off+4])[0] & 0x7FFFFFFF) % 10**6:06d}"

if __name__ == "__main__":
    print(totp(sys.argv[1]))

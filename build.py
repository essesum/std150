"""Шифрует inner.html паролем и собирает публичный index.html.
Запуск: STD150_PASSWORD='...' python3 build.py inner.html gate.html out/index.html
AES-256-GCM, ключ из пароля через PBKDF2-SHA256 (600 000 итераций). Расшифровка — в браузере (WebCrypto).
"""
import base64, json, os, sys, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

src, gate, out = sys.argv[1:4]
pw = os.environ["STD150_PASSWORD"].encode()
ITER = 600_000
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw)
data = open(src, "rb").read()
ct = AESGCM(key).encrypt(iv, data, None)
b = lambda x: base64.b64encode(x).decode()
payload = {"v": hashlib.sha256(ct).hexdigest()[:10], "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}
html = open(gate, encoding="utf-8").read().replace("__PAYLOAD__", json.dumps(payload))
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
open(out, "w", encoding="utf-8").write(html)
print(f"ok: {out} {len(html)/1e6:.1f} MB")

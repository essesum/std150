"""Шифрование/расшифровка архива исходников.
python3 tools/crypt.py decrypt std150-source.zip.enc std150-source.zip   (пароль спросит)
python3 tools/crypt.py encrypt std150-source.zip std150-source.zip.enc"""
import os, sys, getpass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
mode, src, dst = sys.argv[1:4]
pw = (os.environ.get('STD150_PASSWORD') or getpass.getpass('Пароль: ')).encode()
kdf = lambda salt: PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000).derive(pw)
data = open(src, 'rb').read()
if mode == 'encrypt':
    salt, iv = os.urandom(16), os.urandom(12)
    out = b'STD1' + salt + iv + AESGCM(kdf(salt)).encrypt(iv, data, None)
else:
    assert data[:4] == b'STD1', 'не тот файл'
    salt, iv, ct = data[4:20], data[20:32], data[32:]
    out = AESGCM(kdf(salt)).decrypt(iv, ct, None)
open(dst, 'wb').write(out); print('ok', dst)

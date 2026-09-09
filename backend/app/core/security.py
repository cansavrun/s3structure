"""Saf kriptografi yardımcıları; HTTP, Redis veya veritabanı erişimi yoktur."""

import hashlib
import hmac
import re
import secrets

KEY_PATTERN = re.compile(r"^tf_([a-f0-9]{32})\.([A-Za-z0-9_-]{43})$")
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def digest(secret: str, value: str, purpose: str = "api-key") -> str:
    # 256 bit rastgele anahtarlar parola değildir. HMAC + ayrı secret, DB sızıntısına karşı korur.
    return hmac.new(secret.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def mint_key(secret: str) -> tuple[str, str, str]:
    key_id = secrets.token_hex(16)
    raw = f"tf_{key_id}.{secrets.token_urlsafe(32)}"
    return key_id, raw, digest(secret, raw)


def session_store_key(raw: str, secret: str) -> str:
    # Secret rotasyonu hem API anahtarlarını hem açık tarayıcı oturumlarını geçersiz kılar.
    return "session:" + digest(secret, raw, "session")

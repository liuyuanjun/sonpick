import hashlib
import hmac
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from jose import jwt, JWTError

from app.config import get_settings


def _secret() -> bytes:
    return get_settings().secret_key.encode("utf-8")


def hash_password(plain: str) -> str:
    """使用 HMAC-SHA256 加盐哈希密码"""
    salt = os.urandom(16)
    pwd_bytes = plain.encode("utf-8")
    digest = hmac.new(_secret(), salt + pwd_bytes, hashlib.sha256).hexdigest()
    return f"{salt.hex()}:{digest}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt_hex, stored_digest = hashed.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        pwd_bytes = plain.encode("utf-8")
        digest = hmac.new(_secret(), salt + pwd_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, stored_digest)
    except Exception:
        return False


def create_access_token() -> str:
    payload = {
        "sub": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])

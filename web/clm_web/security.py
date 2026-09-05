"""Password hashing and bearer-token helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Any

import jwt


JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password with scrypt and a random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored scrypt hash."""
    try:
        scheme, salt_text, digest_text = encoded.split("$", 2)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(secret: str, subject: str, claims: dict[str, Any], expires_in: int = 900) -> str:
    """Create a short-lived JWT bearer token."""
    now = int(time.time())
    payload = {**claims, "sub": subject, "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(secret: str, token: str) -> dict[str, Any]:
    """Validate and decode a JWT bearer token."""
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])


def new_secret() -> str:
    """Generate a client secret suitable for one-time display."""
    return secrets.token_urlsafe(32)

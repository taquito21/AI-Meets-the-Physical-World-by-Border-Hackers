"""Login: the web client signs in with Supabase Auth and sends its access token as `Authorization: Bearer ...`.

The token is a JWT signed with the project's asymmetric key (ES256), so it is verified locally against the
project's public keys (JWKS, cached), with no call to Supabase per request. The user's profile (company, role)
comes from the `users` table; a valid login without a profile row gets 403.
"""
from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request

from . import db
from .config import settings

_jwks: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    global _jwks
    if _jwks is None:
        if not settings.supabase_jwks_url:
            raise HTTPException(503, "Login is not configured (SUPABASE_URL is missing)")
        _jwks = jwt.PyJWKClient(settings.supabase_jwks_url, cache_keys=True, lifespan=3600)
    return _jwks


def verify_token(token: str) -> str:
    """Return the Supabase user id (the token's `sub`) of a valid access token."""
    try:
        key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience="authenticated",
                            issuer=f"{settings.supabase_url}/auth/v1")
    except jwt.PyJWKClientError:
        raise HTTPException(503, "Could not load the login signing keys")
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Log in again.")
    return claims["sub"]


def current_user(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Log in first")
    user = db.first("users", {"id": verify_token(header[7:].strip())})
    if not user:
        raise HTTPException(403, "This login has no profile yet. Ask your employer to add you.")
    return user


def employer(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["user_class"] != "employer":
        raise HTTPException(403, "Only the employer can do this")
    return user

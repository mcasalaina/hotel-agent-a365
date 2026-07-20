from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient


class AuthenticationError(ValueError):
    """Raised when a browser bearer token fails validation."""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    subject: str
    tenant_id: str
    username: str | None


class EntraTokenValidator:
    def __init__(self, *, tenant_id: str, audience: str, required_scope: str) -> None:
        self._tenant_id = tenant_id
        self._audience = audience
        self._required_scope = required_scope
        self._issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self._jwks = PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
        )

    async def validate(self, token: str) -> AuthenticatedUser:
        try:
            unverified = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_exp": False,
                },
                algorithms=["RS256"],
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("The access token is not a valid JWT") from exc

        if unverified.get("tid") != self._tenant_id:
            raise AuthenticationError("The access token belongs to a different tenant")

        try:
            signing_key = await asyncio.to_thread(self._jwks.get_signing_key_from_jwt, token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["aud", "exp", "iat", "iss", "sub", "tid"],
                },
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("The access token could not be verified") from exc

        scopes = set(str(claims.get("scp", "")).split())
        if self._required_scope not in scopes:
            raise AuthenticationError("The access token is missing the required delegated scope")

        return AuthenticatedUser(
            subject=str(claims["sub"]),
            tenant_id=str(claims["tid"]),
            username=claims.get("preferred_username"),
        )

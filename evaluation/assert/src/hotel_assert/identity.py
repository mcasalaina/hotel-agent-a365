from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx
import jwt

from hotel_assert.constants import AGENT_IDENTITY_FACET, AGENT_USER_FACET
from hotel_assert.redaction import redact_string

_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class IdentityError(RuntimeError):
    """Raised when agent-user identity cannot be proven."""


@dataclass(frozen=True)
class IdentityRequirements:
    tenant_id: str
    audience: str
    agent_user_id: str
    agent_identity_id: str
    parent_blueprint_id: str
    clock_skew_seconds: int = 60

    def __post_init__(self) -> None:
        for name in ("tenant_id", "agent_user_id", "agent_identity_id", "parent_blueprint_id"):
            if not _GUID_RE.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be a GUID")
        if not self.audience.strip():
            raise ValueError("audience must not be empty")


@dataclass(frozen=True)
class ValidatedIdentity:
    token: str = field(repr=False)
    claim_digest: str
    tenant_id: str
    audience: str
    agent_user_id: str
    agent_identity_id: str
    parent_blueprint_id: str
    issued_at: int | None
    expires_at: int

    def audit_record(self) -> dict[str, str | int | None]:
        return {
            "claim_digest": self.claim_digest,
            "tenant_id": self.tenant_id,
            "audience": self.audience,
            "agent_user_id": self.agent_user_id,
            "agent_identity_id": self.agent_identity_id,
            "parent_blueprint_id": self.parent_blueprint_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


def _is_loopback_url(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.username or parsed.password:
        return False
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False
    hostname = parsed.hostname
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _facet_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def _audience_matches(actual: Any, expected: str) -> bool:
    if isinstance(actual, str):
        return actual == expected
    if isinstance(actual, list):
        return expected in actual
    return False


def validate_agent_user_claims(
    claims: Mapping[str, Any],
    requirements: IdentityRequirements,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    current_time = int(time.time()) if now is None else now
    skew = requirements.clock_skew_seconds

    checks = {
        "tid": claims.get("tid") == requirements.tenant_id,
        "aud": _audience_matches(claims.get("aud"), requirements.audience),
        "idtyp": claims.get("idtyp") == "user",
        "oid": claims.get("oid") == requirements.agent_user_id,
        "azp": (claims.get("azp") or claims.get("appid")) == requirements.agent_identity_id,
        "xms_sub_fct": AGENT_USER_FACET in _facet_values(claims.get("xms_sub_fct")),
        "xms_act_fct": AGENT_IDENTITY_FACET in _facet_values(claims.get("xms_act_fct")),
        "xms_par_app_azp": (claims.get("xms_par_app_azp") == requirements.parent_blueprint_id),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise IdentityError(f"Agent-user token claim validation failed: {', '.join(failed)}")

    try:
        not_before = int(claims["nbf"])
        expires_at = int(claims["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IdentityError("Agent-user token is missing valid nbf/exp claims") from exc

    if not_before > current_time + skew:
        raise IdentityError("Agent-user token is not yet valid")
    if expires_at <= current_time - skew:
        raise IdentityError("Agent-user token is expired")

    return dict(claims)


class AgentUserTokenValidator:
    def __init__(
        self,
        requirements: IdentityRequirements,
        *,
        key_client_factory: Callable[[str], Any] = jwt.PyJWKClient,
    ) -> None:
        self.requirements = requirements
        self._key_client_factory = key_client_factory

    def validate(self, token: str) -> ValidatedIdentity:
        try:
            unverified = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_exp": False,
                },
            )
        except jwt.PyJWTError as exc:
            raise IdentityError("Agent-user token is malformed") from exc

        tenant_id = unverified.get("tid")
        issuer = unverified.get("iss")
        if tenant_id != self.requirements.tenant_id or issuer not in {
            f"https://sts.windows.net/{self.requirements.tenant_id}/",
            f"https://login.microsoftonline.com/{self.requirements.tenant_id}/v2.0",
        }:
            raise IdentityError("Agent-user token tenant or issuer is invalid")

        jwks_url = (
            f"https://login.microsoftonline.com/{self.requirements.tenant_id}/discovery/v2.0/keys"
        )
        try:
            signing_key = self._key_client_factory(jwks_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.requirements.audience,
                issuer=issuer,
                leeway=self.requirements.clock_skew_seconds,
            )
        except jwt.PyJWTError as exc:
            raise IdentityError("Agent-user token signature validation failed") from exc

        validated = validate_agent_user_claims(claims, self.requirements)
        safe_claims = {
            key: validated.get(key)
            for key in (
                "aud",
                "azp",
                "appid",
                "exp",
                "iat",
                "idtyp",
                "nbf",
                "oid",
                "tid",
                "xms_act_fct",
                "xms_par_app_azp",
                "xms_sub_fct",
            )
        }
        digest = hashlib.sha256(
            json.dumps(safe_claims, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ValidatedIdentity(
            token=token,
            claim_digest=digest,
            tenant_id=self.requirements.tenant_id,
            audience=self.requirements.audience,
            agent_user_id=self.requirements.agent_user_id,
            agent_identity_id=self.requirements.agent_identity_id,
            parent_blueprint_id=self.requirements.parent_blueprint_id,
            issued_at=validated.get("iat"),
            expires_at=int(validated["exp"]),
        )


class SidecarTokenClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_name: str,
        agent_identity_id: str,
        agent_user_id: str,
        validator: AgentUserTokenValidator,
        timeout_seconds: float = 10.0,
        max_attempts: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not _is_loopback_url(base_url):
            raise ValueError("The Entra auth sidecar must use an HTTP loopback URL")
        if not service_name or "/" in service_name:
            raise ValueError("service_name must be one URL-safe path segment")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.agent_identity_id = agent_identity_id
        self.agent_user_id = agent_user_id
        self.validator = validator
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.transport = transport

    async def acquire(self) -> ValidatedIdentity:
        query = urlencode(
            {
                "AgentIdentity": self.agent_identity_id,
                "AgentUserId": self.agent_user_id,
            }
        )
        url = (
            f"{self.base_url}/AuthorizationHeaderUnauthenticated/"
            f"{quote(self.service_name, safe='')}?{query}"
        )
        transient_statuses = {429, 502, 503, 504}
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
            trust_env=False,
        ) as client:
            response: httpx.Response | None = None
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = await client.get(url)
                except (httpx.NetworkError, httpx.TimeoutException) as exc:
                    if attempt == self.max_attempts:
                        raise IdentityError("Agent-user token broker is unavailable") from exc
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                if response.status_code not in transient_statuses:
                    break
                if attempt == self.max_attempts:
                    raise IdentityError(
                        f"Agent-user token broker returned HTTP {response.status_code}"
                    )
                await asyncio.sleep(2 ** (attempt - 1))
            if response is None or response.status_code != 200:
                status = response.status_code if response is not None else "unknown"
                detail = redact_string(response.text).strip()[:500] if response is not None else ""
                suffix = f": {detail}" if detail else ""
                raise IdentityError(f"Agent-user token broker returned HTTP {status}{suffix}")
            try:
                authorization_header = response.json()["authorizationHeader"]
            except (ValueError, KeyError, TypeError) as exc:
                raise IdentityError("Agent-user token broker returned an invalid payload") from exc

        if not isinstance(authorization_header, str) or not authorization_header.startswith(
            "Bearer "
        ):
            raise IdentityError("Agent-user token broker did not return a bearer token")
        token = authorization_header.removeprefix("Bearer ").strip()
        if not token or " " in token:
            raise IdentityError("Agent-user token broker returned a malformed bearer token")
        return await asyncio.to_thread(self.validator.validate, token)

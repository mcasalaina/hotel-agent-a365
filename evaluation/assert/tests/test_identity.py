from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from hotel_assert.identity import (
    AgentUserTokenValidator,
    IdentityError,
    IdentityRequirements,
    SidecarTokenClient,
    ValidatedIdentity,
    validate_agent_user_claims,
)

TENANT = "11111111-1111-1111-1111-111111111111"
USER = "22222222-2222-2222-2222-222222222222"
AGENT = "33333333-3333-3333-3333-333333333333"
PARENT = "44444444-4444-4444-4444-444444444444"
AUDIENCE = "https://ai.azure.com"


def requirements() -> IdentityRequirements:
    return IdentityRequirements(
        tenant_id=TENANT,
        audience=AUDIENCE,
        agent_user_id=USER,
        agent_identity_id=AGENT,
        parent_blueprint_id=PARENT,
    )


def valid_claims(now: int) -> dict[str, Any]:
    return {
        "tid": TENANT,
        "aud": AUDIENCE,
        "idtyp": "user",
        "oid": USER,
        "azp": AGENT,
        "xms_sub_fct": "1 13",
        "xms_act_fct": "11",
        "xms_par_app_azp": PARENT,
        "nbf": now - 1,
        "iat": now - 1,
        "exp": now + 600,
    }


def test_valid_agent_user_claims() -> None:
    now = int(time.time())
    assert validate_agent_user_claims(valid_claims(now), requirements(), now=now)["oid"] == USER


def test_token_validator_verifies_signature_and_returns_safe_audit_record() -> None:
    now = int(time.time())
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = valid_claims(now)
    claims["iss"] = f"https://login.microsoftonline.com/{TENANT}/v2.0"
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})

    class FakeKeyClient:
        def __init__(self, _: str) -> None:
            pass

        def get_signing_key_from_jwt(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(key=private_key.public_key())

    identity = AgentUserTokenValidator(
        requirements(),
        key_client_factory=FakeKeyClient,
    ).validate(token)
    assert identity.agent_user_id == USER
    assert identity.claim_digest
    assert "token" not in identity.audit_record()

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid_token = jwt.encode(
        claims,
        other_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(IdentityError, match="signature"):
        AgentUserTokenValidator(
            requirements(),
            key_client_factory=FakeKeyClient,
        ).validate(invalid_token)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("tid", "55555555-5555-5555-5555-555555555555"),
        ("aud", "wrong"),
        ("idtyp", "app"),
        ("oid", "55555555-5555-5555-5555-555555555555"),
        ("azp", "55555555-5555-5555-5555-555555555555"),
        ("xms_sub_fct", "1 11"),
        ("xms_act_fct", "13"),
        ("xms_par_app_azp", "55555555-5555-5555-5555-555555555555"),
    ],
)
def test_agent_user_claim_mismatch_fails(claim: str, value: str) -> None:
    now = int(time.time())
    claims = valid_claims(now)
    claims[claim] = value
    with pytest.raises(IdentityError, match=claim):
        validate_agent_user_claims(claims, requirements(), now=now)


def test_expired_and_future_tokens_fail() -> None:
    now = int(time.time())
    expired = valid_claims(now)
    expired["exp"] = now - 120
    with pytest.raises(IdentityError, match="expired"):
        validate_agent_user_claims(expired, requirements(), now=now)
    future = valid_claims(now)
    future["nbf"] = now + 120
    with pytest.raises(IdentityError, match="not yet valid"):
        validate_agent_user_claims(future, requirements(), now=now)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:5000",
        "http://sidecar.example:5000",
        "http://127.0.0.1:5000/path",
        "http://user:password@127.0.0.1:5000",
    ],
)
def test_sidecar_rejects_non_loopback_or_unsafe_url(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        SidecarTokenClient(
            base_url=url,
            service_name="Foundry",
            agent_identity_id=AGENT,
            agent_user_id=USER,
            validator=SimpleNamespace(validate=lambda token: token),
        )


@pytest.mark.asyncio
async def test_sidecar_uses_agent_identity_and_user_query_parameters() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"authorizationHeader": "Bearer opaque-token"})

    identity = ValidatedIdentity(
        token="opaque-token",
        claim_digest="digest",
        tenant_id=TENANT,
        audience=AUDIENCE,
        agent_user_id=USER,
        agent_identity_id=AGENT,
        parent_blueprint_id=PARENT,
        issued_at=1,
        expires_at=2,
    )
    client = SidecarTokenClient(
        base_url="http://127.0.0.1:5000",
        service_name="Foundry",
        agent_identity_id=AGENT,
        agent_user_id=USER,
        validator=SimpleNamespace(validate=lambda token: identity),
        transport=httpx.MockTransport(handler),
    )
    assert await client.acquire() == identity
    assert len(seen) == 1
    assert seen[0].url.path == "/AuthorizationHeaderUnauthenticated/Foundry"
    assert seen[0].url.params["AgentIdentity"] == AGENT
    assert seen[0].url.params["AgentUserId"] == USER
    assert "opaque-token" not in repr(identity)

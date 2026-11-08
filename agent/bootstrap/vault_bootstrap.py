"""Create blueprint credentials directly in a policy-compliant private vault."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import requests
from azure.identity import ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient


def require_private_resolution(hostname: str, subnet: str) -> list[str]:
    network = ipaddress.ip_network(subnet)
    addresses = sorted(
        {entry[4][0] for entry in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    )
    if not addresses or any(ipaddress.ip_address(address) not in network for address in addresses):
        raise RuntimeError(
            "Vault DNS did not resolve exclusively through the expected private subnet"
        )
    return addresses


def main() -> None:
    vault_url = os.environ["KEY_VAULT_URL"]
    blueprint_id = os.environ["BLUEPRINT_OBJECT_ID"]
    private_addresses = require_private_resolution(
        urlparse(vault_url).hostname, os.environ["PRIVATE_ENDPOINT_SUBNET"]
    )
    with (
        ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"]) as credential,
        SecretClient(vault_url=vault_url, credential=credential) as vault,
    ):
        existing = {secret.name: secret for secret in vault.list_properties_of_secrets()}
        with requests.Session() as session:
            graph_token = credential.get_token("https://graph.microsoft.com/.default").token
            graph_headers = {"Authorization": f"Bearer {graph_token}"}
            app_url = f"https://graph.microsoft.com/beta/applications/{blueprint_id}"
            response = session.get(app_url, headers=graph_headers, timeout=30)
            response.raise_for_status()
            application = response.json()
            if application["signInAudience"] != "AzureADMyOrg":
                raise RuntimeError("Blueprint must remain single-tenant")
            if "agent365-blueprint-client-secret" not in existing:
                expiry = datetime.now(UTC) + timedelta(days=365)
                response = session.post(
                    f"{app_url}/addPassword",
                    headers=graph_headers,
                    json={
                        "passwordCredential": {
                            "displayName": "private-keyvault-custody",
                            "endDateTime": expiry.isoformat(),
                        }
                    },
                    timeout=30,
                )
                response.raise_for_status()
                password = response.json()
                blueprint = vault.set_secret(
                    "agent365-blueprint-client-secret",
                    password.pop("secretText"),
                    expires_on=expiry,
                    tags={
                        "blueprintObjectId": blueprint_id,
                        "credentialKeyId": password["keyId"],
                    },
                ).properties
            else:
                blueprint = existing["agent365-blueprint-client-secret"]
                if (blueprint.tags or {}).get("blueprintObjectId") != blueprint_id:
                    raise RuntimeError("Existing vault credential belongs to a different blueprint")
            if "agent365-appinsights-connection-string" not in existing:
                arm_token = credential.get_token("https://management.azure.com/.default").token
                response = session.get(
                    f"https://management.azure.com{os.environ['APPINSIGHTS_RESOURCE_ID']}",
                    params={"api-version": "2020-02-02"},
                    headers={"Authorization": f"Bearer {arm_token}"},
                    timeout=30,
                )
                response.raise_for_status()
                telemetry = vault.set_secret(
                    "agent365-appinsights-connection-string",
                    response.json()["properties"]["ConnectionString"],
                ).properties
            else:
                telemetry = existing["agent365-appinsights-connection-string"]
            print(
                json.dumps(
                    {
                        "privateAddresses": private_addresses,
                        "blueprintSecretUri": blueprint.id,
                        "credentialKeyId": (blueprint.tags or {}).get("credentialKeyId"),
                        "appInsightsSecretUri": telemetry.id,
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()

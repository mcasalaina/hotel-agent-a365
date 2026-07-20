from __future__ import annotations

import os
from collections.abc import Mapping

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.identity.aio import (
    DefaultAzureCredential as AsyncDefaultAzureCredential,
)
from azure.identity.aio import (
    ManagedIdentityCredential as AsyncManagedIdentityCredential,
)


def managed_identity_environment(environment: Mapping[str, str] | None = None) -> bool:
    values = environment if environment is not None else os.environ
    return any(
        values.get(name)
        for name in ("IDENTITY_ENDPOINT", "MSI_ENDPOINT", "AZURE_POD_IDENTITY_AUTHORITY_HOST")
    )


def select_azure_credential(
    environment: Mapping[str, str] | None = None,
) -> DefaultAzureCredential | ManagedIdentityCredential:
    values = environment if environment is not None else os.environ
    if managed_identity_environment(values):
        return ManagedIdentityCredential(client_id=values.get("AZURE_CLIENT_ID") or None)
    return DefaultAzureCredential()


def select_async_azure_credential(
    environment: Mapping[str, str] | None = None,
) -> AsyncDefaultAzureCredential | AsyncManagedIdentityCredential:
    values = environment if environment is not None else os.environ
    if managed_identity_environment(values):
        return AsyncManagedIdentityCredential(client_id=values.get("AZURE_CLIENT_ID") or None)
    return AsyncDefaultAzureCredential()

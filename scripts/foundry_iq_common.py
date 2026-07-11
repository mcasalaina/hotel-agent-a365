from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


class SearchCredential(Protocol):
    def get_token(self, *scopes: str, **kwargs: object) -> object: ...


def managed_identity_environment(environment: Mapping[str, str] | None = None) -> bool:
    values = environment if environment is not None else os.environ
    return any(
        values.get(name)
        for name in ("IDENTITY_ENDPOINT", "MSI_ENDPOINT", "AZURE_POD_IDENTITY_AUTHORITY_HOST")
    )


def select_azure_credential(
    environment: Mapping[str, str] | None = None,
) -> TokenCredential:
    values = environment if environment is not None else os.environ
    if managed_identity_environment(values):
        return ManagedIdentityCredential(client_id=values.get("AZURE_CLIENT_ID") or None)
    return DefaultAzureCredential()


def select_search_credential(
    environment: Mapping[str, str] | None = None,
) -> AzureKeyCredential | TokenCredential:
    values = environment if environment is not None else os.environ
    admin_key = values.get("AZURE_SEARCH_ADMIN_KEY")
    if admin_key:
        return AzureKeyCredential(admin_key)
    return select_azure_credential(values)

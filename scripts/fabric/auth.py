from __future__ import annotations

from typing import Literal

from azure.core.credentials import TokenCredential
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    DefaultAzureCredential,
    DeviceCodeCredential,
)

AuthMode = Literal["default", "azure-cli", "device-code", "chained", "fab"]


def build_credential(mode: AuthMode) -> TokenCredential:
    if mode == "fab":
        raise ValueError("fab authentication uses FabCliTransport, not a token credential.")
    if mode == "default":
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)
    if mode == "azure-cli":
        return AzureCliCredential()
    if mode == "device-code":
        return DeviceCodeCredential()
    return ChainedTokenCredential(
        AzureCliCredential(),
        DeviceCodeCredential(),
        DefaultAzureCredential(exclude_interactive_browser_credential=True),
    )

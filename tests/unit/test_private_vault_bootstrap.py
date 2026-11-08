from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from bootstrap.vault_bootstrap import require_private_resolution  # noqa: E402


def test_private_vault_requires_expected_endpoint_subnet(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("10.86.8.4", 443))],
    )
    assert require_private_resolution("vault.example", "10.86.8.0/24") == ["10.86.8.4"]


@pytest.mark.parametrize("address", ["20.1.2.3", "10.87.8.4", "127.0.0.1"])
def test_private_vault_rejects_public_or_wrong_network(monkeypatch, address):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, (address, 443))],
    )
    with pytest.raises(RuntimeError, match="expected private subnet"):
        require_private_resolution("vault.example", "10.86.8.0/24")

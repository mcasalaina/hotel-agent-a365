import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from hotel_voice_proxy.app import SETTINGS_KEY, _get_config
from hotel_voice_proxy.config import ProxySettings


@pytest.mark.parametrize(
    ("environment", "offline_enabled"),
    [("production", False), ("staging", False), ("development", True)],
)
def test_offline_playback_is_development_only(environment: str, offline_enabled: bool) -> None:
    app = web.Application()
    app[SETTINGS_KEY] = ProxySettings(
        entra_tenant_id="tenant",
        entra_audience="audience",
        entra_required_scope="HotelAgent.Access",
        foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/hotel",
        foundry_agent_name="hotel-servicing-agent",
        environment=environment,
    )

    response = asyncio.run(_get_config(SimpleNamespace(app=app)))
    config = json.loads(response.text)

    assert config["features"]["offlinePlaybackEnabled"] is offline_enabled
    assert config["hotelBrandName"] == "Lyrenza Hotels"
    assert config["dataNotice"] == (
        "Guest and reservation information is restricted to authorized hotel staff."
    )
    assert "demo" not in response.text.lower()
    assert "synthetic" not in response.text.lower()

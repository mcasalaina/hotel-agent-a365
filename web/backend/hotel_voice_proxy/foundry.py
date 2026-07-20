from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlparse, urlunparse

from aiohttp import ClientSession, ClientWebSocketResponse
from azure.core.credentials_async import AsyncTokenCredential

_FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def build_foundry_websocket_url(
    project_endpoint: str,
    agent_name: str,
    agent_session_id: str,
) -> str:
    parsed = urlparse(project_endpoint.rstrip("/"))
    marker = "/api/projects/"
    if marker not in parsed.path:
        raise ValueError("The Foundry project endpoint must contain '/api/projects/'")
    prefix, project_name = parsed.path.split(marker, maxsplit=1)
    if prefix or not project_name or "/" in project_name:
        raise ValueError("The Foundry project endpoint has an invalid project path")
    query = urlencode(
        {
            "api-version": "v1",
            "agent_session_id": agent_session_id,
        }
    )
    return urlunparse(
        (
            "wss",
            parsed.netloc,
            (
                f"/api/projects/{quote(project_name, safe='')}"
                f"/agents/{quote(agent_name, safe='')}"
                "/endpoint/protocols/invocations_ws"
            ),
            "",
            query,
            "",
        )
    )


@dataclass(slots=True)
class FoundrySocket:
    client: ClientSession
    websocket: ClientWebSocketResponse

    async def close(self) -> None:
        await self.websocket.close()
        await self.client.close()


class FoundryWebSocketConnector:
    def __init__(
        self,
        *,
        credential: AsyncTokenCredential,
        project_endpoint: str,
        agent_name: str,
    ) -> None:
        self._credential = credential
        self._project_endpoint = project_endpoint
        self._agent_name = agent_name

    async def open(self, agent_session_id: str) -> FoundrySocket:
        token = await self._credential.get_token(_FOUNDRY_SCOPE)
        client = ClientSession()
        try:
            websocket = await client.ws_connect(
                build_foundry_websocket_url(
                    self._project_endpoint,
                    self._agent_name,
                    agent_session_id,
                ),
                headers={"Authorization": f"Bearer {token.token}"},
                heartbeat=30,
                max_msg_size=16 * 1024 * 1024,
            )
        except BaseException:
            await client.close()
            raise
        return FoundrySocket(client=client, websocket=websocket)

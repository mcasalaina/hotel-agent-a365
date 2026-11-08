from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fabric.client import FabricOperationFailed, HttpResponse


class FabCliTransport:
    """Use fab's own authentication without exporting or passing bearer tokens."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = str(UUID(tenant_id))

    def _verify_tenant(self) -> None:
        response = subprocess.run(
            ["fab", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            encoding="utf-8",
        )
        matches = re.findall(r"Tenant ID:\s*([0-9a-fA-F-]{36})", response.stdout)
        if response.returncode or matches != [self._tenant_id]:
            raise FabricOperationFailed(
                "fab is not authenticated to the requested tenant. "
                f"Run fab auth login --tenant {self._tenant_id}."
            )

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.startswith("wabi-")
            and parsed.hostname.endswith(".analysis.windows.net")
            and re.fullmatch(r"/v1/operations/[0-9a-fA-F-]{36}(?:/result)?", parsed.path)
            and not parsed.query
            and not parsed.fragment
            and parsed.port is None
        ):
            # Fabric's regional LRO locations have equivalent public API routes.
            parsed = urlparse(f"https://api.fabric.microsoft.com{parsed.path}")
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.fabric.microsoft.com"
            or not parsed.path.startswith("/v1/")
            or parsed.fragment
        ):
            raise FabricOperationFailed("fab transport only accepts Fabric v1 API URLs.")
        self._verify_tenant()
        endpoint = parsed.path.removeprefix("/v1/")
        if parsed.query:
            endpoint += f"?{parsed.query}"
        command = ["fab", "api", endpoint, "-X", method.lower(), "--show_headers"]
        if headers:
            command.extend(["-H", ",".join(f"{key}={value}" for key, value in headers.items())])
        with tempfile.TemporaryDirectory(prefix="hotel-fabric-") as folder:
            if body is not None:
                request_path = Path(folder) / "request.json"
                request_path.write_bytes(body)
                command.extend(["-i", str(request_path)])
            response = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                encoding="utf-8",
            )
        try:
            payload = json.loads(response.stdout)
        except json.JSONDecodeError as error:
            raise FabricOperationFailed(
                "fab api did not return a JSON response; no operation success is assumed."
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("status_code"), int):
            raise FabricOperationFailed("fab api returned an invalid response envelope.")
        status = payload["status_code"]
        if response.returncode and status < 400:
            raise FabricOperationFailed("fab api failed despite a success-shaped response.")
        raw_headers = payload.get("headers", {})
        if not isinstance(raw_headers, dict):
            raise FabricOperationFailed("fab api returned invalid response headers.")
        text = payload.get("text")
        return HttpResponse(
            status_code=status,
            headers={str(key).lower(): str(value) for key, value in raw_headers.items()},
            text="" if text in (None, "(Empty)") else json.dumps(text),
        )

"""Upload deterministic hotel source files to a Fabric lakehouse Files area.

Authentication uses the caller's Azure CLI session and a storage-audience token.
IDs and credentials are never embedded in the generated data or repository.
Use --workspace-id and --lakehouse-id together to address exact target artifacts,
or retain name-based addressing with --workspace-name and --lakehouse-name.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import UUID

ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
API_VERSION = "2021-06-08"
CHUNK_SIZE = 4 * 1024 * 1024


def storage_token() -> str:
    result = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://storage.azure.com",
            "--query",
            "accessToken",
            "--output",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("Azure CLI returned an empty OneLake access token")
    return token


class OneLakeUploader:
    def __init__(
        self,
        workspace_name: str,
        lakehouse_name: str,
        token: str,
        *,
        use_ids: bool = False,
    ) -> None:
        if use_ids:
            workspace = str(UUID(workspace_name))
            lakehouse = str(UUID(lakehouse_name))
        else:
            workspace = urllib.parse.quote(workspace_name, safe="")
            lakehouse = urllib.parse.quote(f"{lakehouse_name}.Lakehouse", safe="")
        self._base_url = f"{ONELAKE}/{workspace}/{lakehouse}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "x-ms-version": API_VERSION,
        }

    def create_directory(self, path: str) -> None:
        self._request("PUT", path, query={"resource": "directory"}, allowed={201, 409})

    def upload(self, local_path: Path, remote_path: str) -> None:
        self._request("DELETE", remote_path, allowed={200, 202, 404})
        self._request(
            "PUT",
            remote_path,
            query={"resource": "file"},
            body=b"",
            allowed={201},
        )
        position = 0
        with local_path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                self._request(
                    "PATCH",
                    remote_path,
                    query={"action": "append", "position": str(position)},
                    body=chunk,
                    allowed={202},
                )
                position += len(chunk)
        self._request(
            "PATCH",
            remote_path,
            query={"action": "flush", "position": str(position)},
            body=b"",
            allowed={200},
        )
        print(f"Uploaded {local_path.name}: {position:,} bytes")

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: bytes | None = None,
        allowed: set[int],
    ) -> None:
        encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
        url = f"{self._base_url}/{encoded_path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = dict(self._headers)
        if body is not None:
            headers["Content-Length"] = str(len(body))
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                if response.status not in allowed:
                    raise RuntimeError(f"Unexpected OneLake status {response.status} for {method}")
        except urllib.error.HTTPError as error:
            if error.code not in allowed:
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"OneLake {method} failed for {path}: HTTP {error.code}: {detail}"
                ) from error


def upload_source(
    source: Path,
    fixtures: Path,
    workspace_name: str,
    lakehouse_name: str,
    *,
    use_ids: bool = False,
) -> None:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    expected_files = {
        "manifest.json",
        *(f"{table_name}.csv" for table_name in manifest["counts"]),
    }
    actual_files = {path.name for path in source.iterdir() if path.is_file()}
    missing = expected_files - actual_files
    if missing:
        raise ValueError(f"Generated source is incomplete: {sorted(missing)}")

    uploader = OneLakeUploader(workspace_name, lakehouse_name, storage_token(), use_ids=use_ids)
    for directory in ("Files/data", "Files/data/generated", "Files/data/fixtures"):
        uploader.create_directory(directory)
    for name in sorted(expected_files):
        uploader.upload(source / name, f"Files/data/generated/{name}")
    uploader.upload(fixtures, f"Files/data/fixtures/{fixtures.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/generated"))
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("data/fixtures/business_scenarios.json"),
    )
    workspace = parser.add_mutually_exclusive_group(required=True)
    workspace.add_argument("--workspace-name")
    workspace.add_argument("--workspace-id", type=UUID)
    lakehouse = parser.add_mutually_exclusive_group(required=True)
    lakehouse.add_argument("--lakehouse-name")
    lakehouse.add_argument("--lakehouse-id", type=UUID)
    args = parser.parse_args()
    args.use_ids = args.workspace_id is not None
    if args.use_ids != (args.lakehouse_id is not None):
        parser.error("Use both --workspace-id and --lakehouse-id, or both name arguments")
    if args.use_ids:
        args.workspace_name = str(args.workspace_id)
        args.lakehouse_name = str(args.lakehouse_id)
    return args


def main() -> int:
    args = parse_args()
    upload_source(
        args.source,
        args.fixtures,
        args.workspace_name,
        args.lakehouse_name,
        use_ids=args.use_ids,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

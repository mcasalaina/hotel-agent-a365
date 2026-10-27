"""Create a Hotel model and deploy its report using the current Azure CLI identity.

Existing semantic models cannot be replaced by this template deployer: a definition
export does not prove preservation of all user-owned Prep for AI state. Use supported
field-level TOM edits with preservation verification for existing-model changes.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

FABRIC_API = "https://api.fabric.microsoft.com/v1"
POWER_BI_API = "https://api.powerbi.com/v1.0/myorg"
POWER_BI_RESOURCE = "https://analysis.windows.net/powerbi/api"
TEMPLATE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
ROOT = Path(__file__).resolve().parents[1]


class AzRest:
    """Keep authentication in az and preserve HTTP metadata needed for Fabric LROs."""

    def __init__(
        self,
        workspace_id: str,
        timeout: int = 900,
        *,
        skill: str = "semantic-model-authoring",
    ) -> None:
        self.workspace_id = workspace_id
        self.timeout = timeout
        self.skill = skill

    def request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
        *,
        result: bool = True,
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        fabric = parsed.netloc == "api.fabric.microsoft.com"
        prefix = (
            f"/v1/workspaces/{self.workspace_id}"
            if fabric
            else f"/v1.0/myorg/groups/{self.workspace_id}"
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc not in {"api.fabric.microsoft.com", "api.powerbi.com"}
            or not (
                parsed.path == prefix
                or parsed.path.startswith(prefix + "/")
                or (fabric and parsed.path.startswith("/v1/operations/"))
            )
        ):
            raise ValueError(f"Refusing request outside the selected workspace: {url}")
        resource = "https://api.fabric.microsoft.com" if fabric else POWER_BI_RESOURCE
        command = [
            "az",
            "rest",
            "--method",
            method,
            "--url",
            url,
            "--resource",
            resource,
            "--output",
            "json",
            "--verbose",
            "--headers",
            "Content-Type=application/json",
        ]
        if fabric:
            command.append(f"x-ms-fabric-skill={self.skill}")
        if body is not None:
            command.extend(["--body", json.dumps(body)])
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=180
        )
        if completed.returncode:
            errors = "\n".join(
                line for line in completed.stderr.splitlines() if line.startswith("ERROR:")
            )
            raise RuntimeError(f"{method} {url}: {errors or 'Azure CLI request failed'}")
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
        status = re.findall(r"Response status:\s*(\d+)", completed.stderr)
        if not status or status[-1] != "202" or not fabric:
            return payload
        locations = re.findall(r"'[Ll]ocation': '([^']+)'", completed.stderr)
        if not locations:
            raise RuntimeError("Fabric accepted the operation without an LRO Location.")
        location = locations[-1]
        operation_path = urlparse(location).path
        if re.fullmatch(r"/v1/operations/[0-9a-fA-F-]{36}", operation_path):
            location = "https://api.fabric.microsoft.com" + operation_path
        retry = re.findall(r"'[Rr]etry-[Aa]fter': '(\d+)'", completed.stderr)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(int(retry[-1]) if retry else 5)
            operation = self.request("GET", location)
            state = operation.get("status")
            if state in {"Failed", "Cancelled"}:
                raise RuntimeError(f"Fabric operation {state}: {json.dumps(operation)}")
            if state in {"Succeeded", "Completed"}:
                if result:
                    return self.request("GET", location.rstrip("/") + "/result")
                return operation
        raise TimeoutError(f"Fabric operation did not complete within {self.timeout}s: {location}")

    def items(self, item_type: str) -> list[dict[str, Any]]:
        url: str | None = f"{FABRIC_API}/workspaces/{self.workspace_id}/items?type={item_type}"
        items = []
        while url:
            page = self.request("GET", url)
            items.extend(page.get("value", []))
            url = page.get("continuationUri")
        return items


def build_definition(folder: Path, values: dict[str, str]) -> dict[str, Any]:
    blueprint = json.loads((folder / "blueprint.json").read_text(encoding="utf-8"))
    paths = sorted(
        {
            path
            for pattern in blueprint["includePaths"]
            for path in folder.glob(pattern)
            if path.is_file() and path.name != ".platform"
        }
    )
    if not paths:
        raise ValueError(f"No definition parts found in {folder}")
    parts = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        missing = set(TEMPLATE.findall(text)) - values.keys()
        if missing:
            raise ValueError(f"Missing template values for {path.name}: {sorted(missing)}")
        text = TEMPLATE.sub(lambda match: values[match.group(1)], text)
        parts.append(
            {
                "path": path.relative_to(folder).as_posix(),
                "payload": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "payloadType": "InlineBase64",
            }
        )
    return {"format": blueprint["definitionFormat"], "parts": parts}


def deploy_item(client: AzRest, folder: Path, values: dict[str, str]) -> dict[str, Any]:
    blueprint = json.loads((folder / "blueprint.json").read_text(encoding="utf-8"))
    name, item_type = blueprint["displayName"], blueprint["itemType"]
    matches = [item for item in client.items(item_type) if item["displayName"] == name]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple {item_type} items named {name}; refusing ambiguous deployment."
        )
    if matches and item_type == "SemanticModel":
        # Do not merge/normalize opaque parts or annotations. Even copying every
        # exported part cannot prove that unexported user-owned AI state survives
        # replacement, so getDefinition is not a preservation guarantee.
        raise RuntimeError(
            f"Refusing updateDefinition for existing SemanticModel {name} "
            f"({matches[0]['id']}) in workspace {client.workspace_id}: this template "
            "deployer cannot guarantee preservation of opaque/unknown parts, embedded "
            "metadata, and user-owned Prep for AI state. No model write was attempted. "
            "Use supported field-level TOM edits with before/after preservation "
            "verification or supported Power BI tooling. Configure AI instructions, "
            "AI Data Schema/synonyms, and Verified Answers only in Power BI Prep for AI. "
            "Do not delete/recreate the model to bypass this safeguard."
        )
    definition = build_definition(folder, values)
    workspace_url = f"{FABRIC_API}/workspaces/{client.workspace_id}"
    if matches:
        item = matches[0]
        item_url = f"{workspace_url}/items/{item['id']}"
        client.request("POST", item_url + "/getDefinition", {})
        client.request(
            "POST", item_url + "/updateDefinition", {"definition": definition}, result=False
        )
        client.request("PATCH", item_url, {"description": blueprint["description"]})
    else:
        item = client.request(
            "POST",
            workspace_url + "/items",
            {
                "displayName": name,
                "description": blueprint["description"],
                "type": item_type,
                "definition": definition,
            },
        )
    matches = [found for found in client.items(item_type) if found["displayName"] == name]
    if len(matches) != 1 or matches[0]["id"] != item.get("id"):
        raise RuntimeError(f"Could not uniquely verify the deployed {name}. Do not retry creation.")
    return matches[0]


def verify_definitions(
    client: AzRest, model_id: str, report_id: str, values: dict[str, str]
) -> dict[str, Any]:
    definitions = {}
    for label, item_id in (("model", model_id), ("report", report_id)):
        payload = client.request(
            "POST",
            f"{FABRIC_API}/workspaces/{client.workspace_id}/items/{item_id}/getDefinition",
            {},
        )
        definitions[label] = {
            part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
            for part in payload["definition"]["parts"]
            if part["payloadType"] == "InlineBase64"
        }
    model = definitions["model"]
    model_text = "\n".join(model.values())
    if TEMPLATE.search(model_text) or values["HOTEL_GUEST_SERVICES_LAKEHOUSE_ID"] not in model_text:
        raise RuntimeError(
            "The live semantic model has an unresolved or incorrect lakehouse binding."
        )
    expected_tables = {
        "Date",
        "Property",
        "Outlet",
        "Property KPI Daily",
        "Booking Pace Daily",
        "Restaurant Daily",
        "Disputes Daily",
        "Requests Daily",
        "Maintenance Response Daily",
    }
    tables = sorted(Path(path).stem for path in model if path.startswith("definition/tables/"))
    if set(tables) != expected_tables:
        raise RuntimeError(f"Unexpected live model tables: {tables}")
    direct_lake_count = sum(text.count("mode: directLake") for text in model.values())
    if direct_lake_count != 8:
        raise RuntimeError(f"Expected eight Direct Lake partitions, found {direct_lake_count}.")
    report = definitions["report"]
    reference = json.loads(report["definition.pbir"])["datasetReference"]["byConnection"]
    connection = dict(
        (key.strip().lower(), value.strip())
        for segment in reference["connectionString"].split(";")
        if "=" in segment
        for key, value in [segment.split("=", 1)]
    )
    if connection.get("semanticmodelid") != model_id:
        raise RuntimeError("The live report is not bound to the deployed semantic model.")
    report_metadata = client.request(
        "GET", f"{POWER_BI_API}/groups/{client.workspace_id}/reports/{report_id}"
    )
    if (
        report_metadata.get("datasetId") != model_id
        or report_metadata.get("datasetWorkspaceId") != client.workspace_id
    ):
        raise RuntimeError("Power BI report metadata does not match the selected model/workspace.")
    pages = [
        json.loads(text)["displayName"]
        for path, text in report.items()
        if path.startswith("definition/pages/") and path.endswith("/page.json")
    ]
    return {
        "tables": tables,
        "directLakePartitions": direct_lake_count,
        "reportPages": pages,
        "reportModelBinding": reference,
        "reportDatasetId": report_metadata["datasetId"],
    }


def refresh_and_validate(client: AzRest, model_id: str) -> dict[str, Any]:
    url = f"{POWER_BI_API}/groups/{client.workspace_id}/datasets/{model_id}"
    client.request("POST", url + "/refreshes", {"notifyOption": "NoNotification"})
    deadline = time.monotonic() + client.timeout
    while time.monotonic() < deadline:
        time.sleep(5)
        history = client.request("GET", url + "/refreshes?$top=1").get("value", [])
        if not history:
            continue
        latest = history[0]
        if latest["status"] in {"Failed", "Disabled", "Cancelled"}:
            raise RuntimeError(
                "Refresh failed and was not retried. Credential failures require connection "
                f"configuration in the service: {json.dumps(latest)}"
            )
        if latest["status"] == "Completed":
            query = (
                "EVALUATE ROW(\"Properties\", COUNTROWS('Property'), "
                '"KPI Rows", COUNTROWS(\'Property KPI Daily\'), "OCC", [OCC], '
                '"Room Revenue", [Room Revenue], "RevPAR", [RevPAR], '
                '"Requests", [Requests], "Disputes", [Disputes], '
                '"Restaurant Covers", [Restaurant Covers])'
            )
            result = client.request(
                "POST",
                url + "/executeQueries",
                {
                    "queries": [{"query": query}],
                    "serializerSettings": {"includeNulls": True},
                },
            )
            errors = [
                entry.get("error") or table.get("error")
                for entry in result.get("results", [])
                for table in entry.get("tables", [{}])
            ]
            if result.get("error") or any(errors):
                raise RuntimeError(f"DAX validation failed: {json.dumps(result)}")
            return {"refresh": latest, "dax": result}
    raise TimeoutError("Semantic model refresh did not complete before the deadline.")


def source_readiness(client: AzRest, guest_lakehouse_id: str) -> dict[str, Any]:
    required = set()
    for path in (ROOT / "fabric/semantic-model/definition/tables").glob("*.tmdl"):
        required.update(re.findall(r"^\s*entityName:\s*(\S+)", path.read_text(), re.MULTILINE))
    available: set[str] = set()
    url: str | None = (
        f"{FABRIC_API}/workspaces/{client.workspace_id}/lakehouses/{guest_lakehouse_id}/tables"
    )
    while url:
        page = client.request("GET", url)
        available.update(table["name"] for table in page.get("data", []))
        url = page.get("continuationUri")
    missing = sorted(required - available)
    return {"ready": not missing, "requiredTables": sorted(required), "missingTables": missing}


def guid(value: str) -> str:
    return str(UUID(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", type=guid, required=True)
    parser.add_argument("--guest-lakehouse-id", type=guid, required=True)
    parser.add_argument("--ops-lakehouse-id", type=guid, required=True)
    parser.add_argument("--tenant-id", type=guid)
    parser.add_argument("--subscription-id", type=guid)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create model and deploy report; existing model replacement is blocked. "
        "Otherwise only print the plan.",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh and run DAX after deployment."
    )
    parser.add_argument(
        "--output", type=Path, help="Write non-secret verification evidence as JSON."
    )
    args = parser.parse_args(argv)
    if args.refresh and not args.apply:
        parser.error("--refresh requires --apply")
    account = json.loads(
        subprocess.run(
            ["az", "account", "show", "--output", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    for key, expected in (("tenantId", args.tenant_id), ("id", args.subscription_id)):
        if expected and account[key] != expected:
            raise RuntimeError(f"Current Azure CLI {key} does not match the requested environment.")
    client = AzRest(args.workspace_id)
    workspace = client.request("GET", f"{FABRIC_API}/workspaces/{args.workspace_id}")
    if not workspace.get("capacityId"):
        raise RuntimeError("The selected Fabric workspace does not have a capacity.")
    for lakehouse_id in (args.guest_lakehouse_id, args.ops_lakehouse_id):
        client.request(
            "GET", f"{FABRIC_API}/workspaces/{args.workspace_id}/lakehouses/{lakehouse_id}"
        )
    values = {
        "WORKSPACE_ID": args.workspace_id,
        "HOTEL_GUEST_SERVICES_LAKEHOUSE_ID": args.guest_lakehouse_id,
        "HOTEL_OPERATIONS_LAKEHOUSE_ID": args.ops_lakehouse_id,
    }
    evidence: dict[str, Any] = {
        "workspaceId": args.workspace_id,
        "capacityId": workspace["capacityId"],
        "tenantId": account["tenantId"],
        "identity": account["user"]["name"],
        "applied": args.apply,
    }
    if args.apply:
        model = deploy_item(client, ROOT / "fabric/semantic-model", values)
        values["SEMANTICMODEL_ID"] = model["id"]
        report = deploy_item(client, ROOT / "fabric/report", values)
        evidence.update({"semanticModelId": model["id"], "reportId": report["id"]})
        evidence["definitionVerification"] = verify_definitions(
            client, model["id"], report["id"], values
        )
        evidence["sourceReadiness"] = source_readiness(client, args.guest_lakehouse_id)
        if args.refresh:
            if evidence["sourceReadiness"]["ready"]:
                evidence["dataVerification"] = refresh_and_validate(client, model["id"])
            else:
                evidence["dataVerification"] = {
                    "status": "blocked",
                    "reason": "Load missing Delta tables before model refresh and DAX.",
                }
    else:
        values["SEMANTICMODEL_ID"] = "<resolved-after-model-deployment>"
        evidence["plan"] = [
            {"type": item_type, "parts": len(build_definition(ROOT / folder, values)["parts"])}
            for item_type, folder in (
                ("SemanticModel", "fabric/semantic-model"),
                ("Report", "fabric/report"),
            )
        ]
    output = json.dumps(evidence, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 2 if evidence.get("dataVerification", {}).get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

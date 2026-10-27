#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    EvaluatorGenerationInputs,
    EvaluatorGenerationJob,
    JobStatus,
    PromptEvaluatorGenerationJobSource,
)
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobClient
from run_foundry_agent_quality import (
    AGENT_ROOT,
    _evaluation_item_schema,
    _get_or_create_evaluation,
    _suite_config,
    _write_metadata,
)
from run_multilingual_evaluator_quality import EVAL_NAME, _get_or_create_eval

ROOT = Path(__file__).resolve().parents[1]
# Preserve the 0.5 threshold recorded by historical source core evaluator results.
CORE_PASS_THRESHOLD = 0.5


@dataclass(frozen=True)
class EvaluatorAsset:
    name: str
    version: str
    display_name: str
    description: str
    source_path: Path
    dimensions: list[dict[str, Any]]
    pass_threshold: float | None = None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _hotel_rubric_dimensions() -> list[dict[str, Any]]:
    config = yaml.safe_load(
        (ROOT / "evaluation/assert/config/baseline-quality.yaml").read_text(encoding="utf-8")
    )
    policies = _load_json(ROOT / "evaluation/assert/policies/rubric-policy.json")
    policy_by_name = {item["name"]: item for item in policies["dimensions"]}
    dimensions = config["pipeline"]["judge"]["dimensions"]
    result: list[dict[str, Any]] = []
    for name, rubric in dimensions.items():
        policy = policy_by_name[name]
        description = f"{rubric['description']} {rubric['rubric']}"
        if policy["hard_gate"]:
            description += " This is a hard gate when applicable."
        result.append(
            {
                "id": name,
                "description": description,
                "weight": policy["weight"],
                "always_applicable": not rubric["allow_not_applicable"],
            }
        )
    return result


def _assets() -> list[EvaluatorAsset]:
    return [
        EvaluatorAsset(
            name="hotel-agent-rubric",
            version="8",
            display_name="Hotel Servicing Rubric",
            description="Domain rubric for hotel guest servicing quality.",
            source_path=ROOT / "agent-instructions.md",
            dimensions=_hotel_rubric_dimensions(),
            pass_threshold=0.68,
        ),
        EvaluatorAsset(
            name="hotel-core-quality",
            version="4",
            display_name="Hotel Core Quality",
            description="Core rubric for Hotel Guest Services quality.",
            source_path=ROOT / "src/hotel-servicing-agent/agent-instructions.md",
            dimensions=_load_json(
                ROOT / "src/hotel-servicing-agent/evaluators/hotel-core-quality/"
                "rubric_dimensions.json"
            ),
            pass_threshold=CORE_PASS_THRESHOLD,
        ),
        EvaluatorAsset(
            name="language-continuity",
            version="2",
            display_name="Language Continuity",
            description=(
                "Checks that Hotel Guest Services responses preserve the user's established "
                "language."
            ),
            source_path=(ROOT / "evaluation/assert/config/specs/hotel-agent-behaviors.md"),
            dimensions=_load_json(
                ROOT / "src/hotel-servicing-agent/evaluators/language-continuity/"
                "rubric_dimensions.json"
            ),
            pass_threshold=0.8,
        ),
        EvaluatorAsset(
            name="temporal-boundary",
            version="2",
            display_name="Temporal Boundary",
            description=(
                "Checks the fixed Hotel reservation boundary and Maria Garcia email workflow."
            ),
            source_path=(ROOT / "evaluation/assert/config/specs/hotel-agent-behaviors.md"),
            dimensions=_load_json(
                ROOT / "src/hotel-servicing-agent/evaluators/temporal-boundary/"
                "rubric_dimensions.json"
            ),
            pass_threshold=0.8,
        ),
        EvaluatorAsset(
            name="mail-recipient-integrity",
            version="3",
            display_name="Mail Recipient Integrity",
            description=(
                "Checks recipient-field preservation for Hotel reservation messages and replies."
            ),
            source_path=(ROOT / "evaluation/assert/config/specs/hotel-agent-behaviors.md"),
            dimensions=_load_json(
                ROOT / "src/hotel-servicing-agent/evaluators/mail-recipient-integrity/"
                "rubric_dimensions.json"
            ),
            pass_threshold=0.8,
        ),
    ]


def _get_evaluator(client: AIProjectClient, name: str, version: str) -> Any | None:
    try:
        return client.beta.evaluators.get_version(name, version)
    except ResourceNotFoundError:
        return None


def _dimension_signature(dimensions: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            item.get("id"),
            item.get("description"),
            item.get("weight"),
            bool(item.get("always_applicable", False)),
        )
        for item in dimensions
    ]


def _verify_evaluator(asset: EvaluatorAsset, evaluator: Any) -> None:
    definition = evaluator.as_dict()["definition"]
    if _dimension_signature(definition["dimensions"]) != _dimension_signature(asset.dimensions):
        raise RuntimeError(f"{asset.name} version {asset.version} has different dimensions")
    if (
        asset.pass_threshold is not None
        and float(definition["pass_threshold"]) != asset.pass_threshold
    ):
        raise RuntimeError(f"{asset.name} version {asset.version} has a different pass threshold")


def _wait_for_generation(client: AIProjectClient, job_id: str) -> Any:
    deadline = time.monotonic() + 1800
    while True:
        job = client.beta.evaluators.get_generation_job(job_id)
        if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return job
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Evaluator generation job {job_id} did not finish within 30 minutes"
            )
        time.sleep(10)


def _ensure_evaluator(
    client: AIProjectClient,
    asset: EvaluatorAsset,
    dry_run: bool,
    state: dict[str, Any],
    save: Any,
    judge_deployment: str,
) -> dict[str, Any]:
    catalog_names = {item.name for item in client.beta.evaluators.list(type="custom")}
    existing = _get_evaluator(client, asset.name, asset.version)
    if existing is not None and asset.name in catalog_names:
        _verify_evaluator(asset, existing)
        status = "existing"
    elif dry_run:
        return {"name": asset.name, "version": asset.version, "status": "would-create"}
    else:
        status = "created"

        versions = []
        if asset.name in catalog_names:
            versions = list(client.beta.evaluators.list_versions(asset.name, type="custom"))
        if not versions:
            previous = state.setdefault("generationJobs", {}).get(asset.name)
            if previous and previous.get("status", "").lower() in {
                "failed",
                "cancelled",
                "jobstatus.failed",
                "jobstatus.cancelled",
            }:
                state.setdefault("generationHistory", []).append({"name": asset.name, **previous})
                del state["generationJobs"][asset.name]
            pending = state.setdefault("generationJobs", {}).setdefault(
                asset.name, {"operationId": str(uuid.uuid4()), "status": "pending"}
            )
            save()
            if pending.get("id"):
                job = _wait_for_generation(client, pending["id"])
            else:

                def capture(response: Any) -> None:
                    if pending.get("id") or response.http_response.status_code != 201:
                        return
                    response.http_response.read()
                    body = response.http_response.json()
                    location = response.http_response.headers.get("Operation-Location", "")
                    job_id = body.get("id") or body.get("jobId")
                    if not job_id and location:
                        job_id = location.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
                    if job_id:
                        pending["id"] = job_id
                        save()

                poller = client.beta.evaluators.begin_create_generation_job(
                    job=EvaluatorGenerationJob(
                        inputs=EvaluatorGenerationInputs(
                            model=judge_deployment,
                            evaluator_name=asset.name,
                            evaluator_display_name=asset.display_name,
                            evaluator_description=asset.description,
                            sources=[
                                PromptEvaluatorGenerationJobSource(
                                    description="Hotel instructions and behavioral contracts.",
                                    prompt=asset.source_path.read_text(encoding="utf-8"),
                                )
                            ],
                        )
                    ),
                    operation_id=pending["operationId"],
                    polling_interval=10,
                    raw_response_hook=capture,
                )
                poller.result(timeout=1800)
                job = (
                    client.beta.evaluators.get_generation_job(pending["id"])
                    if pending.get("id")
                    else None
                )
            pending["status"] = str(job.status) if job else "succeeded"
            save()
            if job and job.status != JobStatus.SUCCEEDED:
                message = job.error.message if job.error else str(job.status)
                raise RuntimeError(f"Evaluator generation failed for {asset.name}: {message}")
            versions = list(client.beta.evaluators.list_versions(asset.name, type="custom"))

        latest = max(int(item.version) for item in versions)
        if latest >= int(asset.version):
            raise RuntimeError(
                f"{asset.name}:{asset.version} conflicts with the reviewed source definition"
            )
        generated = max(versions, key=lambda item: int(item.version))
        generated_threshold = generated.as_dict()["definition"]["pass_threshold"]
        threshold = (
            asset.pass_threshold if asset.pass_threshold is not None else generated_threshold
        )
        while latest < int(asset.version):
            created = client.beta.evaluators.create_version(
                name=asset.name,
                evaluator_version={
                    "name": asset.name,
                    "categories": ["quality"],
                    "display_name": asset.display_name,
                    "description": asset.description,
                    "definition": {
                        "type": "rubric",
                        "dimensions": asset.dimensions,
                        "pass_threshold": threshold,
                    },
                },
            )
            latest = int(created.version)

    evaluator = client.beta.evaluators.get_version(asset.name, asset.version)
    _verify_evaluator(asset, evaluator)
    for attempt in range(13):
        catalog_names = {item.name for item in client.beta.evaluators.list(type="custom")}
        versions = list(client.beta.evaluators.list_versions(asset.name, type="custom"))
        if asset.name in catalog_names and asset.version in {v.version for v in versions}:
            break
        if attempt == 12:
            raise RuntimeError(f"{asset.name}:{asset.version} is not visible in the custom catalog")
        time.sleep(5)
    return {
        "name": asset.name,
        "version": asset.version,
        "id": evaluator.id,
        "status": status,
        "catalogVerified": True,
        "catalogVersions": [item.version for item in versions],
        "definition": evaluator.as_dict()["definition"],
        "sourcePath": str(asset.source_path.relative_to(ROOT)),
        "sourceSha256": hashlib.sha256(asset.source_path.read_bytes()).hexdigest(),
    }


def _ensure_datasets(
    client: AIProjectClient,
    dry_run: bool,
    connection_name: str | None,
    credential: AzureCliCredential,
    replace_content: bool = False,
) -> list[dict[str, Any]]:
    datasets = [
        (
            "hotel-servicing-quality",
            "4.0",
            ROOT / "tests/fixtures/evaluation/hotel_servicing_quality.jsonl",
            False,
        ),
        (
            "hotel-core-quality",
            "4.0",
            ROOT / "src/hotel-servicing-agent/datasets/hotel-core-quality",
            True,
        ),
        (
            "hotel-temporal-quality",
            "1.0",
            ROOT / "src/hotel-servicing-agent/datasets/hotel-temporal-quality",
            True,
        ),
    ]
    results: list[dict[str, Any]] = []
    for name, version, path, is_folder in datasets:
        status = "existing"
        try:
            dataset = client.datasets.get(name, version)
        except ResourceNotFoundError:
            if dry_run:
                results.append({"name": name, "version": version, "status": "would-create"})
                continue
            if is_folder:
                dataset = client.datasets.upload_folder(
                    name=name, version=version, folder=str(path), connection_name=connection_name
                )
            else:
                dataset = client.datasets.upload_file(
                    name=name, version=version, file_path=str(path), connection_name=connection_name
                )
            status = "created"
        files = sorted(path.glob("*.jsonl")) if is_folder else [path]
        source_files = [
            {
                "path": str(file.relative_to(ROOT)),
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                "rows": len(file.read_text(encoding="utf-8").splitlines()),
            }
            for file in files
        ]
        if not dry_run:
            for file, source in zip(files, source_files, strict=True):
                blob_uri = (
                    f"{dataset.data_uri.rstrip('/')}/{file.name}" if is_folder else dataset.data_uri
                )
                with BlobClient.from_blob_url(blob_uri, credential=credential) as blob:
                    remote = blob.download_blob().readall()
                    remote_hash = hashlib.sha256(remote).hexdigest()
                    if remote_hash != source["sha256"]:
                        if not replace_content:
                            raise RuntimeError(
                                f"{name}:{version} differs from source; "
                                "content replacement requires --replace-dataset-content"
                            )
                        source["replacedSha256"] = remote_hash
                        blob.upload_blob(file.read_bytes(), overwrite=True)
                        remote_hash = hashlib.sha256(blob.download_blob().readall()).hexdigest()
                        status = "corrected"
                    if remote_hash != source["sha256"]:
                        raise RuntimeError(f"{name}:{version} failed remote content verification")
                    source["remoteSha256"] = remote_hash
            dataset.tags = {
                **(dataset.tags or {}),
                "agent": "hotel-servicing-agent",
                "stage": "curated",
                "version": version,
                "source_sha256": hashlib.sha256(
                    b"".join(file.read_bytes() for file in files)
                ).hexdigest(),
            }
            dataset = client.datasets.create_or_update(name, version, dataset_version=dataset)
            listed = {item.version for item in client.datasets.list_versions(name)}
            if version not in listed:
                raise RuntimeError(f"{name}:{version} is not listed in the dataset catalog")
        results.append(
            {
                **dataset.as_dict(),
                "status": status,
                "contentVerified": not dry_run,
                "sourceFiles": source_files,
            }
        )
    return results


def _ensure_definitions(client: AIProjectClient, environment: str | None) -> list[dict[str, Any]]:
    definitions = []
    for asset in _assets():
        evaluator = client.beta.evaluators.get_version(asset.name, asset.version)
        _verify_evaluator(asset, evaluator)
        if environment:
            path = (
                AGENT_ROOT
                / ".foundry/evaluators"
                / environment
                / f"{asset.name}-v{asset.version}.json"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evaluator.as_dict(), indent=2, ensure_ascii=False) + "\n")
    with client.get_openai_client() as openai_client:
        for selected in ("quality", "full", "temporal"):
            suite = _suite_config(selected)
            dataset = client.datasets.get(suite["dataset_name"], suite["dataset_version"])
            for name, version in suite["evaluators"]:
                client.beta.evaluators.get_version(name, version)
            definition = _get_or_create_evaluation(
                openai_client,
                suite["evaluation_name"],
                suite["evaluators"],
                suite["query_field"],
                suite["judge_deployment"],
                AGENT_ROOT / ".foundry/suites" / environment / f"{suite['evaluation_name']}.json"
                if environment
                else None,
            )
            definition = openai_client.evals.retrieve(definition.id)
            schema = _evaluation_item_schema(definition)
            if suite["query_field"] not in schema.get("properties", {}) or suite[
                "query_field"
            ] not in schema.get("required", []):
                raise RuntimeError(f"{definition.name} readback has an incomplete item_schema")
            definitions.append(
                {
                    "id": definition.id,
                    "name": definition.name,
                    "definition": definition.model_dump(mode="json", by_alias=True, warnings=False),
                    "itemSchema": schema,
                    "itemSchemaVerified": True,
                    "readbackSchemaField": "data_source_config.schema.item",
                    "source": suite["source"],
                    "dataset": dataset.name,
                    "datasetVersion": dataset.version,
                    "datasetUri": dataset.id,
                    "datasetStorageUri": dataset.data_uri,
                    "repositoryDatasetPath": str(suite["dataset_path"].relative_to(ROOT)),
                    "evaluators": [
                        {"name": name, "version": version} for name, version in suite["evaluators"]
                    ],
                    "queryField": suite["query_field"],
                    "status": "registered",
                }
            )
        definition = _get_or_create_eval(
            openai_client,
            AGENT_ROOT / ".foundry/suites" / environment / f"{EVAL_NAME}.json"
            if environment
            else None,
        )
        definition = openai_client.evals.retrieve(definition.id)
        schema = _evaluation_item_schema(definition)
        required = {"query", "response"}
        if not required.issubset(schema.get("properties", {})) or not required.issubset(
            schema.get("required", [])
        ):
            raise RuntimeError(f"{definition.name} readback has an incomplete item_schema")
        dataset = client.datasets.get("hotel-core-quality", "4.0")
        definitions.append(
            {
                "id": definition.id,
                "name": definition.name,
                "definition": definition.model_dump(mode="json", by_alias=True, warnings=False),
                "itemSchema": schema,
                "itemSchemaVerified": True,
                "readbackSchemaField": "data_source_config.schema.item",
                "source": "scripts/run_multilingual_evaluator_quality.py",
                "evaluators": [{"name": "language-continuity", "version": "2"}],
                "dataset": "hotel-core-quality",
                "datasetVersion": "4.0",
                "datasetUri": dataset.id,
                "datasetStorageUri": dataset.data_uri,
                "selectedCaseIds": [16, 17, 18],
                "agentInvoked": False,
                "status": "registered",
            }
        )
    if environment:
        entries = []
        for definition in definitions:
            path = AGENT_ROOT / ".foundry/suites" / environment / f"{definition['name']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(definition, indent=2, ensure_ascii=False) + "\n")
            entries.append(
                {
                    "id": definition["name"],
                    "evalId": definition["id"],
                    "definitionName": definition["name"],
                    "generationSource": "source-controlled",
                    "tags": {"tier": "quality", "purpose": "baseline"},
                    "suiteFile": str(path.relative_to(AGENT_ROOT)),
                    "dataset": definition["dataset"],
                    "datasetVersion": definition["datasetVersion"],
                    **(
                        {"datasetUri": definition["datasetUri"]}
                        if definition.get("datasetUri")
                        else {}
                    ),
                    "evaluators": definition["evaluators"],
                }
            )
        _write_metadata(
            {
                "environment": environment,
                "metadata_path": AGENT_ROOT / ".foundry" / f"agent-metadata.{environment}.yaml",
            },
            "evaluationSuites",
            entries,
        )
    return definitions


def _result_summaries(environment: str) -> list[dict[str, Any]]:
    summaries = []
    for path in sorted(
        (AGENT_ROOT / ".foundry/results" / environment).glob("eval_*/evalrun_*.json")
    ):
        payload = _load_json(path)
        summaries.append(
            {key: value for key, value in payload.items() if key != "outputItems"}
            | {
                "outputItemCount": len(payload.get("outputItems", [])),
                "resultFile": str(path.relative_to(AGENT_ROOT)),
            }
        )
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create the source-controlled Foundry evaluation assets without invoking an agent."
        )
    )
    parser.add_argument("--project-endpoint", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--connection-name")
    parser.add_argument("--replace-dataset-content", action="store_true")
    parser.add_argument("--judge-deployment", default="gpt-5.4-mini")
    parser.add_argument(
        "--only", choices=("all", "evaluators", "datasets", "definitions"), default="all"
    )
    parser.add_argument("--evaluator-name", choices=tuple(asset.name for asset in _assets()))
    parser.add_argument("--environment")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-output", type=Path)
    args = parser.parse_args()
    if args.only in {"all", "definitions"} and not args.environment and not args.dry_run:
        parser.error("--environment is required to persist resumable definition IDs")
    results = _load_json(args.output) if args.output and args.output.exists() else {}
    if results.get("projectEndpoint", args.project_endpoint) != args.project_endpoint:
        raise RuntimeError("The output file belongs to a different Foundry project")
    results["projectEndpoint"] = args.project_endpoint
    results["tenantId"] = args.tenant_id
    results.setdefault("runs", [])
    results["optionalInfrastructure"] = {
        "assertControlledJob": {
            "source": "infra/evaluation/assert-job.bicep",
            "status": "source-only",
            "provisionedByThisOperation": False,
        },
        "assertGitHubEnvironment": {"status": "source-only", "provisionedByThisOperation": False},
    }

    def save() -> None:
        results["updatedAt"] = datetime.now(UTC).isoformat()
        if args.environment:
            results["runs"] = _result_summaries(args.environment)
            results["runtimeVerification"] = (
                "results-recorded"
                if any(run.get("agentInvoked") for run in results["runs"])
                else "awaiting-deployed-version-and-integration-readiness"
            )
        if not args.dry_run:
            for output in (args.output, args.report_output):
                if output:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")

    with (
        AzureCliCredential(tenant_id=args.tenant_id) as credential,
        AIProjectClient(endpoint=args.project_endpoint, credential=credential) as client,
    ):
        deployments = {item.name for item in client.deployments.list()}
        if args.judge_deployment not in deployments:
            raise RuntimeError(
                f"Required judge deployment {args.judge_deployment} is not available"
            )
        if args.only in {"all", "evaluators"}:
            results["evaluators"] = []
            for asset in _assets():
                if args.evaluator_name and args.evaluator_name != asset.name:
                    continue
                try:
                    results["evaluators"].append(
                        _ensure_evaluator(
                            client, asset, args.dry_run, results, save, args.judge_deployment
                        )
                    )
                    results.setdefault("blockers", {}).pop(asset.name, None)
                except Exception as error:
                    results.setdefault("blockers", {})[asset.name] = str(error)
                save()
        if args.only in {"all", "datasets"}:
            results["datasets"] = _ensure_datasets(
                client, args.dry_run, args.connection_name, credential, args.replace_dataset_content
            )
            save()
        if args.only in {"all", "definitions"} and not args.dry_run:
            if results.get("blockers"):
                raise RuntimeError(
                    "Resolve evaluator publication blockers before binding definitions"
                )
            results["evaluationDefinitions"] = _ensure_definitions(client, args.environment)
            save()
    print(json.dumps(results, indent=2))
    if results.get("blockers"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobClient
from openai.types.evals import RunCreateResponse, RunListResponse, RunRetrieveResponse
from run_foundry_agent_quality import (
    _evaluation_item_schema,
    _failure_clusters,
    _lookup_definition_id,
    _remember_definition,
    _resolve_context,
    _write_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
EVAL_NAME = "hotel-language-continuity-quality-v2-r3"
EVALUATOR_NAME = "language-continuity"
EVALUATOR_VERSION = "2"
VALIDATION_DATASET_VERSION = "2.3"


def _multilingual_rows() -> list[dict[str, Any]]:
    path = ROOT / "src/hotel-servicing-agent/datasets/hotel-core-quality/hotel-core-quality.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    result = [row for row in rows if 16 <= int(row["id"]) <= 18]
    if len(result) != 3:
        raise RuntimeError("Expected exactly three multilingual evaluator quality rows")
    return result


def _get_or_create_eval(openai_client: Any, registry_path: Path | None = None) -> Any:
    known_id = _lookup_definition_id(registry_path, EVAL_NAME)
    if known_id:
        definition = openai_client.evals.retrieve(known_id)
        if definition.name != EVAL_NAME:
            raise RuntimeError("The cached evaluation ID belongs to a different definition")
        else:
            if len(definition.testing_criteria) != 1:
                raise RuntimeError(f"{EVAL_NAME} has a different evaluator set")
            criterion = definition.testing_criteria[0]
            data_mapping = getattr(criterion, "data_mapping", None)
            if (
                getattr(criterion, "evaluator_name", None) != EVALUATOR_NAME
                or getattr(criterion, "evaluator_version", None) != EVALUATOR_VERSION
                or data_mapping
                != {
                    "query": "{{item.query}}",
                    "response": "{{item.response}}",
                }
                or getattr(criterion, "initialization_parameters", None)
                != {"model": "gpt-5.4-mini"}
            ):
                raise RuntimeError(f"{EVAL_NAME} exists with a different evaluator binding")
            item_schema = _evaluation_item_schema(definition)
            required = {"query", "response"}
            if not required.issubset(item_schema.get("properties", {})) or not required.issubset(
                item_schema.get("required", [])
            ):
                raise RuntimeError(
                    f"{EVAL_NAME} has an incomplete item_schema; "
                    "publish an approved corrected definition before running"
                )
            return definition
    definition = openai_client.evals.create(
        name=EVAL_NAME,
        data_source_config={
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "response": {"type": "string"},
                },
                "required": ["query", "response"],
            },
            "include_sample_schema": False,
        },
        testing_criteria=[
            {
                "type": "azure_ai_evaluator",
                "name": EVALUATOR_NAME,
                "evaluator_name": EVALUATOR_NAME,
                "evaluator_version": EVALUATOR_VERSION,
                "initialization_parameters": {"model": "gpt-5.4-mini"},
                "data_mapping": {
                    "query": "{{item.query}}",
                    "response": "{{item.response}}",
                },
            }
        ],
    )
    _remember_definition(registry_path, definition)
    return definition


def _validation_content(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_case_id": row["id"],
            "query": row["query"],
            "response": row["candidate_response"],
        }
        for row in rows
    ]


def _input_provenance_matches(
    output_items: list[dict[str, Any]], expected_rows: list[dict[str, Any]]
) -> bool:
    actual_rows = []
    for output in output_items:
        source = output.get("datasource_item")
        if not isinstance(source, dict):
            return False
        item = source.get("item", source)
        if not isinstance(item, dict):
            return False
        actual_rows.append(item)
    return sorted(json.dumps(row, sort_keys=True) for row in actual_rows) == sorted(
        json.dumps(row, sort_keys=True) for row in expected_rows
    )


def _validation_dataset(
    client: AIProjectClient,
    credential: AzureCliCredential,
    rows: list[dict[str, Any]],
    environment: str,
    connection_name: str | None,
) -> Any:
    path = (
        ROOT
        / "src/hotel-servicing-agent/.foundry/datasets"
        / environment
        / f"hotel-servicing-agent-language-continuity-quality-v{VALIDATION_DATASET_VERSION}.jsonl"
    )
    content = "".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in _validation_content(rows)
    ).encode()
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError("The reviewed language-validation cache differs; publish a new version")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    name, version = "hotel-language-continuity-quality", VALIDATION_DATASET_VERSION
    try:
        dataset = client.datasets.get(name, version)
    except ResourceNotFoundError as error:
        if not connection_name:
            raise ValueError(
                "Pass --connection-name for the reviewed language-validation upload"
            ) from error
        dataset = client.datasets.upload_file(
            name=name, version=version, file_path=str(path), connection_name=connection_name
        )
    with BlobClient.from_blob_url(dataset.data_uri, credential=credential) as blob:
        remote_hash = hashlib.sha256(blob.download_blob().readall()).hexdigest()
    content_hash = hashlib.sha256(content).hexdigest()
    if remote_hash != content_hash:
        raise RuntimeError("The registered language-validation data differs from reviewed source")
    dataset.tags = {
        **(dataset.tags or {}),
        "agent": "hotel-servicing-agent",
        "stage": "curated",
        "version": version,
        "source_dataset": "hotel-core-quality:4.0",
        "source_case_ids": "16,17,18",
        "source_sha256": content_hash,
    }
    return client.datasets.create_or_update(name, version, dataset_version=dataset)


def _wait_for_run(openai_client: Any, eval_id: str, run_id: str) -> Any:
    deadline = time.monotonic() + 1800
    while True:
        run = openai_client.evals.runs.retrieve(run_id, eval_id=eval_id)
        if run.status in {"completed", "failed", "canceled", "cancelled"}:
            return run
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Evaluation run {run_id} did not finish within 30 minutes")
        time.sleep(10)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run static multilingual responses through the hotel Foundry evaluator."
    )
    parser.add_argument("--project-endpoint")
    parser.add_argument("--tenant-id")
    parser.add_argument("--environment")
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--connection-name")
    parser.add_argument("--register-only", action="store_true")
    parser.add_argument("--new-run", action="store_true")
    parser.add_argument("--resume-eval-id")
    parser.add_argument("--resume-run-id")
    args = parser.parse_args()
    if bool(args.resume_eval_id) != bool(args.resume_run_id):
        parser.error("--resume-eval-id and --resume-run-id must be provided together")
    context = _resolve_context(args, require_agent=False)

    with (
        AzureCliCredential(tenant_id=context["tenant_id"]) as credential,
        AIProjectClient(
            endpoint=context["project_endpoint"], credential=credential
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        project_client.beta.evaluators.get_version(EVALUATOR_NAME, EVALUATOR_VERSION)
        definition = _get_or_create_eval(
            openai_client,
            ROOT
            / "src/hotel-servicing-agent/.foundry/suites"
            / context["environment"]
            / f"{EVAL_NAME}.json",
        )
        if args.register_only:
            print(
                json.dumps(
                    {"evalId": definition.id, "name": definition.name, "status": "registered"}
                )
            )
            return
        rows = _multilingual_rows()
        dataset = _validation_dataset(
            project_client, credential, rows, context["environment"], args.connection_name
        )
        source_hash = hashlib.sha256(
            json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        file_hash = dataset.tags["source_sha256"]
        run_name = (
            f"{EVAL_NAME}-{context['environment']}-d{dataset.version}-{file_hash[:12]}-inline"
        )
        if args.new_run:
            run_name += f"-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        run: RunCreateResponse | RunRetrieveResponse | RunListResponse | None = None
        if args.resume_eval_id:
            if definition.id != args.resume_eval_id:
                raise RuntimeError(
                    "Resume evaluation does not match the multilingual evaluator suite"
                )
            run = openai_client.evals.runs.retrieve(args.resume_run_id, eval_id=definition.id)
            run_name = run.name
        elif not args.new_run:
            run = next(
                (
                    r
                    for r in openai_client.evals.runs.list(definition.id, limit=100)
                    if r.name == run_name
                ),
                None,
            )
        if run is None:
            run = openai_client.evals.runs.create(
                definition.id,
                name=run_name,
                data_source={
                    "type": "jsonl",
                    "source": {
                        "type": "file_content",
                        "content": [{"item": row} for row in _validation_content(rows)],
                    },
                },
            )
        last_eval = {
            "evalId": definition.id,
            "evalRunId": run.id,
            "runName": run_name,
            "status": run.status,
            "startedAt": datetime.fromtimestamp(run.created_at, tz=UTC).isoformat(),
            "sourceSha256": source_hash,
            "registeredFileSha256": file_hash,
            "datasetUri": dataset.id,
            "datasetVersion": dataset.version,
            "runSourceType": "file_content",
            "sourceCaseIds": [row["id"] for row in rows],
            "agentInvoked": False,
        }
        output_path = (
            ROOT
            / "src/hotel-servicing-agent/.foundry/results"
            / context["environment"]
            / definition.id
            / f"{run.id}.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(last_eval, indent=2) + "\n", encoding="utf-8")
        _write_metadata(context, "lastEvaluatorValidation", last_eval)
        print(json.dumps(last_eval), flush=True)
        run = _wait_for_run(openai_client, definition.id, run.id)
        output_items = [
            item.model_dump(mode="json")
            for item in openai_client.evals.runs.output_items.list(
                run.id, eval_id=definition.id, limit=100
            )
        ]

    payload = {
        **last_eval,
        "status": run.status,
        "completedAt": datetime.now(UTC).isoformat(),
        "resultCounts": run.result_counts.model_dump(mode="json"),
        "error": run.error.model_dump(mode="json") if run.error else None,
        "failureClusters": _failure_clusters(output_items),
        "inputProvenanceMatches": _input_provenance_matches(
            output_items, _validation_content(rows)
        ),
        "outputItems": output_items,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_metadata(
        context,
        "lastEvaluatorValidation",
        {
            **{key: value for key, value in payload.items() if key != "outputItems"},
            "resultFile": str(output_path.relative_to(ROOT / "src/hotel-servicing-agent")),
        },
    )
    print(json.dumps({**payload, "outputItems": len(output_items), "outputPath": str(output_path)}))
    if not payload["inputProvenanceMatches"]:
        raise RuntimeError("The evaluator's actual inputs differ from the approved static cases")
    if (
        run.status != "completed"
        or run.result_counts.failed
        or run.result_counts.errored
        or run.result_counts.total != len(rows)
        or run.result_counts.passed != len(rows)
        or len(output_items) != len(rows)
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

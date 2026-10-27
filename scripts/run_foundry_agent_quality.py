#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from openai.types.evals import RunCreateResponse, RunListResponse, RunRetrieveResponse

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "src/hotel-servicing-agent"
QUALITY_SUITES = {
    "quality": ROOT / "eval.yaml",
    "full": AGENT_ROOT / "eval.yaml",
    "temporal": None,
}


def _suite_config(suite: str) -> dict[str, Any]:
    path = QUALITY_SUITES[suite]
    if path:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        dataset_path = path.parent / config["dataset"]["local_uri"]
        return {
            "evaluation_name": f"{config['name']}-r2",
            "dataset_name": config["dataset"]["name"],
            "dataset_version": str(config["dataset"]["version"]),
            "dataset_path": dataset_path,
            "evaluators": tuple(
                (item["name"], str(item["version"])) for item in config["evaluators"]
            ),
            "query_field": "input" if suite == "quality" else "query",
            "source": str(path.relative_to(ROOT)),
            "judge_deployment": config["options"]["eval_model"],
        }
    return {
        "evaluation_name": "hotel-temporal-quality-r2",
        "dataset_name": "hotel-temporal-quality",
        "dataset_version": "1.0",
        "dataset_path": AGENT_ROOT / "datasets/hotel-temporal-quality",
        "evaluators": (("temporal-boundary", "2"),),
        "query_field": "query",
        "source": "src/hotel-servicing-agent/datasets/hotel-temporal-quality",
        "judge_deployment": "gpt-5.4-mini",
    }


def _read_azd_environment(environment: str | None) -> dict[str, str]:
    if not environment:
        return {}
    path = ROOT / ".azure" / environment / ".env"
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, raw = line.partition("=")
        if separator and not key.lstrip().startswith("#"):
            parts = shlex.split(raw, comments=True)
            values[key.strip()] = " ".join(parts)
    return values


def _resolve_context(args: argparse.Namespace, *, require_agent: bool = True) -> dict[str, Any]:
    environment = args.environment or os.environ.get("AZURE_ENV_NAME")
    values = {**os.environ, **_read_azd_environment(environment)}
    environment = environment or values.get("AZURE_ENV_NAME")
    if not environment:
        raise ValueError("Select --environment or export AZURE_ENV_NAME")
    context = {
        "environment": environment,
        "project_endpoint": args.project_endpoint
        or values.get("AZURE_AI_PROJECT_ENDPOINT")
        or values.get("AZURE_AIPROJECT_ENDPOINT"),
        "tenant_id": args.tenant_id or values.get("AZURE_TENANT_ID"),
        "agent_name": getattr(args, "agent_name", None)
        or values.get("AGENT_HOTEL_SERVICING_AGENT_NAME")
        or "hotel-servicing-agent",
        "agent_version": getattr(args, "agent_version", None)
        or values.get("AGENT_HOTEL_SERVICING_AGENT_VERSION"),
        "metadata_path": args.metadata_file
        or AGENT_ROOT / ".foundry" / f"agent-metadata.{environment}.yaml",
    }
    required = ["project_endpoint", "tenant_id"]
    if require_agent:
        required.append("agent_version")
    missing = [key for key in required if not context[key]]
    if missing:
        raise ValueError(
            f"Missing target values: {', '.join(missing)}; pass flags or use azd env values"
        )
    return context


def _criterion(
    name: str, version: str, query_field: str = "query", judge_deployment: str = "gpt-5.4-mini"
) -> dict[str, Any]:
    response_mapping = (
        "{{sample.output_items}}"
        if name in {"hotel-agent-rubric", "hotel-core-quality"}
        else "{{sample.output_text}}"
    )
    data_mapping = {"query": "{{item." + query_field + "}}", "response": response_mapping}
    if name in {"hotel-agent-rubric", "hotel-core-quality"}:
        data_mapping["tool_definitions"] = "{{sample.tool_definitions}}"
    return {
        "type": "azure_ai_evaluator",
        "name": name,
        "evaluator_name": name,
        "evaluator_version": version,
        "initialization_parameters": {"model": judge_deployment},
        "data_mapping": data_mapping,
    }


def _get_or_create_evaluation(
    openai_client: Any,
    evaluation_name: str,
    evaluators: tuple[tuple[str, str], ...],
    query_field: str = "query",
    judge_deployment: str = "gpt-5.4-mini",
    registry_path: Path | None = None,
) -> Any:
    criteria = [
        _criterion(name, version, query_field, judge_deployment) for name, version in evaluators
    ]
    known_id = _lookup_definition_id(registry_path, evaluation_name)
    if known_id:
        definition = openai_client.evals.retrieve(known_id)
        if definition.name != evaluation_name:
            raise RuntimeError("The cached evaluation ID belongs to a different definition")
        actual = [
            item.model_dump(mode="json", exclude_none=True, warnings=False)
            for item in definition.testing_criteria
        ]
        for expected in criteria:
            matches = [item for item in actual if item.get("name") == expected["name"]]
            if len(matches) != 1 or any(
                matches[0].get(key) != value for key, value in expected.items()
            ):
                raise RuntimeError(
                    f"{evaluation_name} has different evaluator bindings or mappings"
                )
        if len(actual) != len(criteria):
            raise RuntimeError(f"{evaluation_name} has a different evaluator set")
        item_schema = _evaluation_item_schema(definition)
        if query_field not in item_schema.get(
            "properties", {}
        ) or query_field not in item_schema.get("required", []):
            raise RuntimeError(
                f"{evaluation_name} has an incomplete item_schema; "
                "publish an approved corrected definition before running"
            )
        return definition
    fields = {
        query_field: {"type": "string"},
        "expected_output": {"type": "string"},
        "description": {"type": "string"},
        "id": {"type": "integer"},
        "candidate_response": {"type": "string"},
    }
    definition = openai_client.evals.create(
        name=evaluation_name,
        data_source_config={
            "type": "custom",
            "item_schema": {
                "type": "object",
                "properties": fields,
                "required": [query_field],
            },
            "include_sample_schema": True,
        },
        testing_criteria=criteria,
    )
    _remember_definition(registry_path, definition)
    return definition


def _evaluation_item_schema(definition: Any) -> dict[str, Any]:
    config = definition.data_source_config
    requested_schema = getattr(config, "item_schema", None)
    if requested_schema:
        return dict(requested_schema)
    # OpenAI returns the request's item_schema under schema.item (SDK alias schema_).
    response_schema = getattr(config, "schema_", {}) or {}
    return dict(response_schema.get("item", {}) or {})


def _lookup_definition_id(path: Path | None, name: str) -> str | None:
    if path is None or not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("name") != name or not record.get("id"):
        raise RuntimeError("The evaluation registry does not match the selected definition")
    return str(record["id"])


def _remember_definition(path: Path | None, definition: Any) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"id": definition.id, "name": definition.name}, indent=2) + "\n",
            encoding="utf-8",
        )


def _write_metadata(context: dict[str, Any], key: str, values: Any) -> None:
    path = context["metadata_path"]
    metadata = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    metadata = metadata or {}
    metadata["defaultEnvironment"] = context["environment"]
    selected = metadata.setdefault("environments", {}).setdefault(context["environment"], {})
    selected["azd"] = {
        "environmentName": context["environment"],
        "service": "hotel-servicing-agent",
    }
    selected[key] = values
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _wait_for_run(openai_client: Any, eval_id: str, run_id: str) -> Any:
    deadline = time.monotonic() + 3600
    while True:
        run = openai_client.evals.runs.retrieve(run_id, eval_id=eval_id)
        if run.status in {"completed", "failed", "canceled", "cancelled"}:
            return run
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Evaluation run {run_id} did not finish within 60 minutes; resume it"
            )
        time.sleep(15)


def _failure_clusters(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[tuple[str, str]] = []
    for item in items:
        results = item.get("results", [])
        detail_names = {r.get("name") for r in results if r.get("metric") != "custom_score"}
        for result in results:
            if result.get("metric") == "custom_score" and result.get("name") in detail_names:
                continue
            if result.get("passed") is True:
                continue
            evaluator = str(result.get("name", "unknown"))
            error = result.get("error") or (result.get("sample") or {}).get("error")
            if isinstance(error, dict):
                error = error.get("message") or error
            reason = str(result.get("reason") or error or "No verdict/reason returned")
            failures.append((evaluator, reason))
        if item.get("status") in {"failed", "error", "errored"} and not results:
            failures.append(("runtime", str(item.get("error") or "No evaluator results returned")))
    counts = Counter(evaluator for evaluator, _ in failures)
    return [
        {
            "evaluator": evaluator,
            "count": count,
            "reasons": [reason for name, reason in failures if name == evaluator],
        }
        for evaluator, count in sorted(counts.items())
    ]


def _dataset_signature(path: Path) -> str:
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish or run selected Hotel Foundry evaluations."
    )
    parser.add_argument("--project-endpoint")
    parser.add_argument("--tenant-id")
    parser.add_argument("--environment")
    parser.add_argument("--agent-name")
    parser.add_argument("--agent-version")
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--suite", choices=tuple(QUALITY_SUITES), default="quality")
    parser.add_argument("--register-only", action="store_true")
    parser.add_argument("--new-run", action="store_true")
    parser.add_argument("--resume-eval-id")
    parser.add_argument("--resume-run-id")
    args = parser.parse_args()
    if bool(args.resume_eval_id) != bool(args.resume_run_id):
        parser.error("--resume-eval-id and --resume-run-id must be provided together")
    context = _resolve_context(args, require_agent=not args.register_only)
    suite = _suite_config(args.suite)
    started_at = datetime.now(UTC)

    with (
        AzureCliCredential(tenant_id=context["tenant_id"]) as credential,
        AIProjectClient(endpoint=context["project_endpoint"], credential=credential) as client,
        client.get_openai_client() as openai_client,
    ):
        dataset = client.datasets.get(suite["dataset_name"], suite["dataset_version"])
        if (dataset.tags or {}).get("source_sha256") != _dataset_signature(suite["dataset_path"]):
            raise RuntimeError(
                "The registered dataset has not been verified against current source"
            )
        for name, version in suite["evaluators"]:
            client.beta.evaluators.get_version(name, version)
        definition = _get_or_create_evaluation(
            openai_client,
            suite["evaluation_name"],
            suite["evaluators"],
            suite["query_field"],
            suite["judge_deployment"],
            AGENT_ROOT
            / ".foundry/suites"
            / context["environment"]
            / f"{suite['evaluation_name']}.json",
        )
        if args.register_only:
            print(
                json.dumps(
                    {"evalId": definition.id, "name": definition.name, "status": "registered"}
                )
            )
            return
        agent = client.agents.get_version(context["agent_name"], context["agent_version"])
        if agent.status != "active":
            raise RuntimeError(f"{context['agent_name']}:{context['agent_version']} is not active")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "dataset": _dataset_signature(suite["dataset_path"]),
                    "evaluators": suite["evaluators"],
                    "agentVersion": context["agent_version"],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12]
        run_name = (
            f"{definition.name}-{context['environment']}-v{context['agent_version']}-{fingerprint}"
        )
        if args.new_run:
            run_name += f"-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
        run: RunCreateResponse | RunRetrieveResponse | RunListResponse | None = None
        if args.resume_eval_id:
            if definition.id != args.resume_eval_id:
                raise RuntimeError("Resume evaluation does not match the selected suite")
            run = openai_client.evals.runs.retrieve(args.resume_run_id, eval_id=definition.id)
            target = run.model_dump(mode="json").get("data_source", {}).get("target", {})
            if target and (
                target.get("name") != context["agent_name"]
                or target.get("version") != context["agent_version"]
            ):
                raise RuntimeError("Resume run targets a different agent/version")
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
            # The preview SDK's request TypedDict omits template messages and concurrency controls.
            run = openai_client.post(
                f"/evals/{definition.id}/runs",
                cast_to=RunCreateResponse,
                body={
                    "name": run_name,
                    "data_source": {
                        "type": "azure_ai_target_completions",
                        "source": {"type": "file_id", "id": dataset.id},
                        "input_messages": {
                            "type": "template",
                            "template": [
                                {
                                    "role": "user",
                                    "content": "{{item." + suite["query_field"] + "}}",
                                    "type": "message",
                                }
                            ],
                        },
                        "target": {
                            "type": "azure_ai_agent",
                            "name": context["agent_name"],
                            "version": context["agent_version"],
                            "tool_descriptions": [],
                        },
                        "item_generation_params": {
                            "type": "target_completions",
                            "max_concurrency": 1,
                        },
                    },
                },
            )
        last_eval = {
            "evalId": definition.id,
            "evalRunId": run.id,
            "runName": run_name,
            "suiteName": suite["evaluation_name"],
            "suiteVersion": suite["dataset_version"],
            "agentVersion": context["agent_version"],
            "agentInvoked": True,
            "datasetSha256": _dataset_signature(suite["dataset_path"]),
            "startedAt": datetime.fromtimestamp(run.created_at, tz=UTC).isoformat(),
            "status": run.status,
        }
        result_path = (
            AGENT_ROOT
            / ".foundry/results"
            / context["environment"]
            / definition.id
            / f"{run.id}.json"
        )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(last_eval, indent=2) + "\n", encoding="utf-8")
        _write_metadata(context, "lastEval", last_eval)
        print(json.dumps(last_eval), flush=True)
        run = _wait_for_run(openai_client, definition.id, run.id)
        items = [
            item.model_dump(mode="json")
            for item in openai_client.evals.runs.output_items.list(
                run.id, eval_id=definition.id, limit=100
            )
        ]

    counts = run.result_counts.model_dump(mode="json")
    payload = {
        **last_eval,
        "status": run.status,
        "completedAt": datetime.now(UTC).isoformat(),
        "resultCounts": counts,
        "error": run.error.model_dump(mode="json") if run.error else None,
        "failureClusters": _failure_clusters(items),
        "outputItems": items,
    }
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_metadata(
        context,
        "lastEval",
        {
            **{
                key: value
                for key, value in payload.items()
                if key not in {"outputItems", "failureClusters"}
            },
            "resultFile": str(result_path.relative_to(AGENT_ROOT)),
        },
    )
    print(
        json.dumps(
            {
                **{key: value for key, value in payload.items() if key != "outputItems"},
                "outputItems": len(items),
                "resultPath": str(result_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if run.status != "completed" or counts.get("errored") or counts.get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

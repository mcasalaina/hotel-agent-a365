#!/usr/bin/env python3
"""Capture live hotel interactions and run the bank's unchanged native quality metrics."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NAME = "hotel-servicing-classic-evals"
REFERENCE_EVAL = "eval_f801b4c226ef4db5a3cffd872a263e4c"
ENDPOINT = (
    "https://mcasalaina-4iqs-2701-resource.services.ai.azure.com"
    "/api/projects/mcasalaina-4iqs-2701"
)
AGENT = "hotel-servicing-agent"
VERSION = "8"
API_VERSION = "2025-11-15-preview"
CASES = ROOT / "evaluation/hotel-servicing-classic-interactions.jsonl"
OUTPUT = ROOT / f"src/hotel-servicing-agent/.foundry/results/dev/{NAME}"
TOOL_ROOT = ROOT / "src/hotel-servicing-agent/hotel_servicing_agent/tools"
METRICS = (
    "groundedness",
    "coherence",
    "relevance",
    "fluency",
    "tool_call_accuracy",
    "tool_selection",
    "tool_input_accuracy",
    "tool_output_utilization",
    "tool_call_success",
    "tool_use_quality",
    "intent_resolution",
    "task_completion",
    "task_adherence",
)
TERMINAL = {"completed", "failed", "canceled", "cancelled"}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def az_rest(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    command = [
        "az", "rest", "--method", method, "--url", url,
        "--resource", "https://ai.azure.com", "--output", "json",
    ]
    if body is not None:
        # File-backed bodies also avoid macOS's command-line argument size limit.
        request = OUTPUT / "requests" / f"{time.time_ns()}.json"
        write_json(request, body)
        command.extend(["--body", f"@{request}"])
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=600)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object from Azure CLI")
    return payload


def load_cases() -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    if len(cases) != 20 or len({case["case_id"] for case in cases}) != 20:
        raise ValueError("Exactly 20 uniquely identified customer interactions are required")
    if any(not isinstance(case.get("query"), str) or not case["query"].strip() for case in cases):
        raise ValueError("Every interaction needs a nonempty query")
    return cases


def source_tool_definitions() -> list[dict[str, Any]]:
    """Extract registered FunctionTool metadata without importing optional hosting dependencies."""
    definitions: list[dict[str, Any]] = []
    for path in sorted(TOOL_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "FunctionTool":
                continue
            keywords = {kw.arg: kw.value for kw in node.keywords}
            name = ast.literal_eval(keywords["name"])
            description = ast.literal_eval(keywords["description"])
            handler = keywords["func"]
            if not isinstance(handler, ast.Attribute):
                raise ValueError(f"Unexpected function registration in {path}")
            function = next(
                item for item in ast.walk(tree)
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                and item.name == handler.attr
            )
            arguments = function.args.args[1:]
            optional = (
                {argument.arg for argument in arguments[-len(function.args.defaults):]}
                if function.args.defaults else set()
            )
            properties = {}
            for argument in arguments:
                annotation = ast.unparse(argument.annotation) if argument.annotation else ""
                properties[argument.arg] = annotation_schema(annotation)
            definitions.append({
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [argument.arg for argument in arguments
                                 if argument.arg not in optional],
                },
            })
    if len({tool["name"] for tool in definitions}) != 7:
        raise ValueError("Expected all seven registered hotel tools")
    return definitions


def annotation_schema(annotation: str) -> dict[str, Any]:
    if " | " in annotation:
        return {"anyOf": [annotation_schema(part) for part in annotation.split(" | ")]}
    if annotation == "PropertyId":
        catalog = TOOL_ROOT.parent / "property_catalog.py"
        tree = ast.parse(catalog.read_text(encoding="utf-8"))
        alias = next(node for node in tree.body if isinstance(node, ast.TypeAlias))
        if not isinstance(alias.value, ast.Subscript):
            raise ValueError("Unexpected PropertyId alias")
        return {"type": "string", "enum": list(ast.literal_eval(alias.value.slice))}
    types = {
        "str": "string", "bool": "boolean", "int": "integer", "float": "number", "None": "null",
    }
    if annotation in types:
        return {"type": types[annotation]}
    raise ValueError(f"Unsupported registered tool annotation: {annotation}")


def response_text(response: dict[str, Any]) -> str:
    return "\n".join(
        part["text"]
        for item in response.get("output", [])
        if item.get("type") == "message" and item.get("role", "assistant") == "assistant"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ).strip()


def build_item(
    case: dict[str, Any], response: dict[str, Any], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    if response.get("status") != "completed" or not response_text(response):
        raise ValueError(f"Hosted response is not complete: {case['case_id']}")
    output = response["output"]
    tool_outputs = [item["output"] for item in output if item.get("type") == "function_call_output"]
    return {
        "case_id": case["case_id"],
        "quality_query": case["query"],
        "quality_response": response_text(response),
        "evidence_response": json.dumps({"observed_response_output": output}, ensure_ascii=False),
        "grounding_context": json.dumps(
            {"observed_user_query": case["query"], "observed_tool_outputs": tool_outputs},
            ensure_ascii=False,
        ),
        "tool_definitions": tools,
    }


def capture(endpoint: str, version: str) -> list[dict[str, Any]]:
    cases = load_cases()
    tools = source_tool_definitions()
    manifest = {
        "endpoint": endpoint, "agent_name": AGENT, "agent_version": version, "cases": cases,
    }
    manifest_path = OUTPUT / "capture-target.json"
    if manifest_path.exists():
        cached = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(cached.get(key) != value for key, value in manifest.items()):
            raise ValueError("Cached captures target a different agent, version, or dataset")
    write_json(manifest_path, manifest)
    write_json(OUTPUT / "tool-definitions.json", tools)

    def verify_agent() -> None:
        agent = az_rest("get", f"{endpoint}/agents/{AGENT}?api-version={API_VERSION}")
        if agent["versions"]["latest"]["version"] != version:
            raise ValueError("The live hosted endpoint is not the requested version")
        write_json(OUTPUT / "agent.json", agent)

    def invoke(case: dict[str, Any]) -> dict[str, Any]:
        path = OUTPUT / "responses" / f"{case['case_id']}.json"
        if path.exists():
            response = json.loads(path.read_text(encoding="utf-8"))
        else:
            response = az_rest(
                "post",
                f"{endpoint}/agents/{AGENT}/endpoint/protocols/openai/responses"
                f"?api-version={API_VERSION}",
                {"input": case["query"], "store": False},
            )
            write_json(path, response)
        reference = response.get("agent_reference") or {}
        if reference.get("name") != AGENT or reference.get("version") != version:
            raise ValueError(f"Wrong deployed agent in actual response: {case['case_id']}")
        mutating_tools = {
            "manage_reservation", "send_email", "reply_to_email", "query_work_context",
        }
        if any(
            event.get("type") == "function_call" and event.get("name") in mutating_tools
            for event in response.get("output", [])
        ):
            raise ValueError(f"Unexpected potentially mutating tool invocation: {case['case_id']}")
        item = build_item(case, response, tools)
        print(f"Captured {case['case_id']}: {len(response['output'])} output events", flush=True)
        return item

    verify_agent()
    with ThreadPoolExecutor(max_workers=3) as executor:
        items = list(executor.map(invoke, cases))
    verify_agent()
    write_json(OUTPUT / "items.json", items)
    (OUTPUT / "captured.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8"
    )
    return items


def evaluation_body(reference: dict[str, Any], version: str) -> dict[str, Any]:
    criteria = copy.deepcopy(reference["testing_criteria"])
    if tuple(criterion["name"] for criterion in criteria) != METRICS:
        raise ValueError("The reference metric list has changed")
    for criterion in criteria:
        criterion.pop("id", None)
    return {
        "name": NAME,
        "data_source_config": {
            "type": "custom",
            "item_schema": copy.deepcopy(reference["data_source_config"]["schema"]["item"]),
            "include_sample_schema": False,
        },
        "testing_criteria": criteria,
        "metadata": {
            "agent_name": AGENT, "agent_version": version, "reference_eval": REFERENCE_EVAL,
        },
    }


def prepare_evaluation(endpoint: str, version: str) -> str:
    reference = az_rest("get", f"{endpoint}/openai/v1/evals/{REFERENCE_EVAL}")
    write_json(OUTPUT / "reference-evaluation.json", reference)
    body = evaluation_body(reference, version)
    write_json(OUTPUT / "evaluation-request.json", body)
    existing = OUTPUT / "evaluation.json"
    if existing.exists():
        evaluation = json.loads(existing.read_text(encoding="utf-8"))
        live = az_rest("get", f"{endpoint}/openai/v1/evals/{evaluation['id']}")
        actual = [{k: v for k, v in criterion.items() if k != "id"}
                  for criterion in live["testing_criteria"]]
        if live["name"] != NAME or actual != body["testing_criteria"]:
            raise ValueError("Existing native evaluation metrics differ from the reference")
        return str(evaluation["id"])
    evaluation = az_rest("post", f"{endpoint}/openai/v1/evals", body)
    write_json(existing, evaluation)
    return str(evaluation["id"])


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    metrics: dict[str, dict[str, int]] = {}
    for item in items:
        results = item.get("results") or []
        present = {result.get("name") for result in results}
        incomplete = (
            not set(METRICS).issubset(present) or bool(item.get("error"))
            or item.get("status", "completed") != "completed"
        )
        for result in results:
            name = str(result.get("name"))
            metric = result.get("metric", name)
            key = name if metric == name else f"{name}/{metric}"
            counts = metrics.setdefault(key, {"passed": 0, "failed": 0, "incomplete": 0})
            score = result.get("score")
            valid = (
                name in METRICS
                and isinstance(score, int | float) and not isinstance(score, bool)
                and math.isfinite(score)
                and isinstance(result.get("passed"), bool)
                and bool(result.get("reason"))
                and not result.get("error")
            )
            incomplete |= not valid
            key = "incomplete" if not valid else "passed" if result["passed"] else "failed"
            counts[key] += 1
        rows.append({
            "case_id": (item.get("datasource_item") or {}).get("case_id"),
            "incomplete": incomplete,
            "failed_metrics": sorted({
                r["name"] for r in results if r.get("passed") is False and r.get("name")
            }),
        })
    return {
        "total": len(rows),
        "incomplete": sum(row["incomplete"] for row in rows),
        "passed": sum(not row["incomplete"] and not row["failed_metrics"] for row in rows),
        "quality_failed": sum(
            not row["incomplete"] and bool(row["failed_metrics"]) for row in rows
        ),
        "metrics": metrics,
        "rows": rows,
    }


def download(endpoint: str, eval_id: str, run_id: str) -> list[dict[str, Any]]:
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
        project.get_openai_client() as client,
    ):
        items = [
            item.model_dump()
            for item in client.evals.runs.output_items.list(eval_id=eval_id, run_id=run_id)
        ]
    write_json(OUTPUT / f"{run_id}-output-items.json", items)
    write_json(OUTPUT / "output-items.json", items)
    return items


def run(
    endpoint: str, eval_id: str, data_source: dict[str, Any], version: str
) -> str:
    body = {
        "name": NAME, "data_source": data_source,
        "metadata": {"agent_name": AGENT, "agent_version": version, "trigger_type": "oneoff"},
    }
    write_json(OUTPUT / "run-request.json", body)
    result = az_rest("post", f"{endpoint}/openai/v1/evals/{eval_id}/runs", body)
    run_id = str(result["id"])
    write_json(OUTPUT / f"{run_id}-created.json", result)
    write_json(OUTPUT / "run.json", {
        "eval_id": eval_id, "run_id": run_id, "name": NAME, "agent_version": version,
    })
    return run_id


def poll(endpoint: str, eval_id: str, run_id: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while True:
        status = az_rest("get", f"{endpoint}/openai/v1/evals/{eval_id}/runs/{run_id}")
        write_json(OUTPUT / f"{run_id}-status.json", status)
        write_json(OUTPUT / "status.json", status)
        print(f"{run_id}: {status['status']} {status.get('result_counts')}", flush=True)
        if status["status"] in TERMINAL:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Native evaluation remains active; IDs saved in run.json")
        time.sleep(30)
    summary = summarize(download(endpoint, eval_id, run_id))
    summary.update({
        "eval_id": eval_id, "run_id": run_id, "status": status["status"],
        "report_url": status.get("report_url"), "result_counts": status.get("result_counts"),
        "agent_name": AGENT, "agent_version": VERSION,
    })
    summary["execution_complete"] = (
        status["status"] == "completed" and summary["total"] == 20
        and summary["incomplete"] == 0 and not (status.get("result_counts") or {}).get("errored")
        and {row["case_id"] for row in summary["rows"]}
        == {case["case_id"] for case in load_cases()}
    )
    write_json(OUTPUT / f"{run_id}-summary.json", summary)
    write_json(OUTPUT / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"rows", "metrics"}}, indent=2))
    if not summary["execution_complete"]:
        raise RuntimeError("Native evaluation did not produce 20 fully scored, error-free rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "prepare", "run", "poll"])
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument(
        "--source", type=Path, help="Native data_source JSON, e.g. registered file_id"
    )
    parser.add_argument("--timeout", type=int, default=5400)
    args = parser.parse_args()
    if args.action == "capture":
        capture(args.endpoint, args.version)
    elif args.action == "prepare":
        print(prepare_evaluation(args.endpoint, args.version))
    elif args.action == "run":
        eval_id = prepare_evaluation(args.endpoint, args.version)
        if args.source:
            source = json.loads(args.source.read_text(encoding="utf-8"))
        else:
            items = json.loads((OUTPUT / "items.json").read_text(encoding="utf-8"))
            source = {
                "type": "jsonl",
                "source": {"type": "file_content", "content": [{"item": item} for item in items]},
            }
        run_id = run(args.endpoint, eval_id, source, args.version)
        poll(args.endpoint, eval_id, run_id, args.timeout)
    else:
        manifest = json.loads((OUTPUT / "run.json").read_text(encoding="utf-8"))
        poll(args.endpoint, manifest["eval_id"], manifest["run_id"], args.timeout)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Capture real Hotel responses and evaluate knowledge-only language continuity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import unicodedata
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from azure.identity import AzureCliCredential

ROOT = Path(__file__).resolve().parents[2]
PROJECT = (
    "https://mcasalaina-4iqs-2701-resource.services.ai.azure.com/api/projects/mcasalaina-4iqs-2701"
)
TENANT = "e1cffe86-c44d-4b35-8157-2d32636babb5"
AGENT = "hotel-servicing-agent"
VERSION = "2"
ARTIFACTS = ROOT / (
    f"src/hotel-servicing-agent/.foundry/results/hotel-2701/agent-v{VERSION}-knowledge-language"
)
DEFINITIONS = {
    "knowledge": "eval_f0a00591c04b4007a663cdf8f0bed3ae",
    "core": "eval_98cc1e167a2b45db937ce1109fe4b659",
    "temporal": "eval_6a2a77830ee5416d87fd37a55e9be215",
    "language": "eval_10e69778f68a47c3820b43de8c42ff33",
    "previous-static-language": "eval_5acdf9f4062a4c79a71dfbf8aacd6e31",
    "previous-pipeline-control": "eval_2566b4876bde4979beef7b2d5286a7a6",
}
CASES: list[dict[str, Any]] = [
    {
        "id": "switch-01-en",
        "conversation": "language-switch",
        "language": "en",
        "facts": ["pool"],
        "input": (
            "At Lyrenza Scottsdale Sonoran Resort, what are the pool's daily opening "
            "and closing times? Give the approved knowledge source."
        ),
    },
    {
        "id": "switch-02-es",
        "conversation": "language-switch",
        "language": "es",
        "facts": ["valet"],
        "input": (
            "Ahora responde en español: ¿cuánto cuesta el valet por noche en ese mismo "
            "hotel? Cita la fuente."
        ),
    },
    {
        "id": "switch-03-zh",
        "conversation": "language-switch",
        "language": "zh",
        "facts": ["pool"],
        "input": "请改用中文回答：刚才那家酒店的游泳池每天什么时间开放和关闭？请注明来源。",
    },
    {
        "id": "switch-04-ar",
        "conversation": "language-switch",
        "language": "ar",
        "facts": ["valet"],
        "input": "أجب الآن بالعربية: ما سعر خدمة صف السيارات لكل ليلة في الفندق نفسه؟ اذكر المصدر.",
    },
    {
        "id": "switch-05-en",
        "conversation": "language-switch",
        "language": "en",
        "facts": ["valet", "pool"],
        "input": (
            "Switch back to English. Confirm the nightly valet rate and the pool's "
            "opening hours for that same property, with the source."
        ),
    },
    {
        "id": "names-06-en",
        "conversation": "names",
        "language": "en",
        "facts": ["valet"],
        "input": (
            "María and Chen are visiting Lyrenza Scottsdale Sonoran Resort. What is "
            "the nightly valet parking fee? Cite the hotel policy."
        ),
    },
    {
        "id": "knowledge-07-es",
        "conversation": "spanish",
        "language": "es",
        "facts": ["pool"],
        "input": (
            "Para Lyrenza Scottsdale Sonoran Resort, ¿cuál es el horario diario de "
            "la piscina? Incluye la fuente aprobada."
        ),
    },
    {
        "id": "knowledge-08-zh",
        "conversation": "chinese",
        "language": "zh",
        "facts": ["valet"],
        "input": "Lyrenza Scottsdale Sonoran Resort 的代客泊车每晚收费多少美元？请引用酒店资料。",
    },
]


def save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(str(unicodedata.digit(c)) if c.isdecimal() else c for c in normalized)


def duplicate_text_assertion(text: str) -> dict[str, Any]:
    """Detect adjacent repeated answers, paragraphs, or sentences without rewriting output."""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
    matches: list[dict[str, Any]] = []
    for midpoint in {len(normalized) // 2, (len(normalized) + 1) // 2}:
        first, second = normalized[:midpoint].strip(), normalized[midpoint:].strip()
        if first and first == second:
            matches.append({"unit": "answer", "text": first, "repeatCount": 2})
            break
    for unit, fragments in (
        ("paragraph", re.split(r"\n\s*\n", text)),
        ("sentence", re.split(r"(?<=[.!?。！？])\s*", text)),
    ):
        parts = [
            re.sub(r"\s+", " ", unicodedata.normalize("NFKC", part)).strip()
            for part in fragments
            if part.strip()
        ]
        for width in range(1, len(parts) // 2 + 1):
            for start in range(len(parts) - width * 2 + 1):
                block = parts[start : start + width]
                if block == parts[start + width : start + width * 2]:
                    match = {"unit": unit, "text": " ".join(block), "repeatCount": 2}
                    if match not in matches:
                        matches.append(match)
    return {"passed": not matches, "score": int(not matches), "matches": matches}


def detected_language(text: str) -> str:
    if len(re.findall(r"[\u0600-\u06ff]", text)) >= 8:
        return "ar"
    if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 4:
        return "zh"
    spanish = {"el", "la", "de", "por", "noche", "piscina", "horario", "fuente", "del"}
    words = set(re.findall(r"\w+", text.lower()))
    return "es" if len(words & spanish) >= 3 else "en"


def knowledge_scores(text: str, facts: list[str]) -> dict[str, Any]:
    value = normalize(text).lower()
    scores = {}
    if "valet" in facts:
        amount = bool(re.search(r"(?<!\d)25(?!\d)", value)) or "二十五" in value
        nightly = any(word in value for word in ("night", "noche", "晚", "ليل"))
        scores["valet_usd_25_per_night"] = {"score": int(amount and nightly)}
    if "pool" in facts:
        opens = bool(re.search(r"(?<!\d)0?7[:.]00|7\s*(?:a\.?m|点|點|時|时)", value))
        closes = bool(re.search(r"(?<!\d)21[:.]00|9(?::00)?\s*p\.?m|(?:晚|下午).*?9", value))
        scores["pool_0700_to_2100"] = {"score": int(opens and closes)}
    return scores


def parse_invocation(raw: str) -> dict[str, Any]:
    value = raw.replace("\r\n", "\n")
    start = re.search(r"(?m)^HTTP/\S+\s+\d+", value)
    if not start:
        raise ValueError(f"No HTTP response in CLI raw output: {value[:500]}")
    head, body = value[start.start() :].split("\n\n", 1)
    headers = {}
    for line in head.splitlines()[1:]:
        if ":" not in line:
            continue
        name, content = line.split(":", 1)
        name = name.lower().strip()
        if any(
            part in name
            for part in ("session", "conversation", "trace", "request-id", "agent-version")
        ):
            headers[name] = content.strip()
    events = []
    try:
        response = json.loads(body)
    except json.JSONDecodeError:
        for line in body.splitlines():
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                events.append(json.loads(line[5:].strip()))
        candidates = [event["response"] for event in events if "response" in event]
        if not candidates:
            raise ValueError(f"No response object in event stream: {body[:500]}") from None
        response = candidates[-1]
    if "response" in response:
        response = response["response"]
    text = response.get("output_text") or "\n".join(
        str(content.get("text", ""))
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") in {"output_text", "text"}
    )
    if not text:
        raise ValueError(f"The hosted response has no generated text: {response}")
    conversation = response.get("conversation") or {}
    return {
        "actualResponse": text,
        "responseId": response.get("id"),
        "sessionId": next((v for k, v in headers.items() if "session" in k), None),
        "conversationId": (
            conversation.get("id") if isinstance(conversation, dict) else conversation
        ),
        "traceIds": {k: v for k, v in headers.items() if "trace" in k or "request-id" in k},
        "responseHeaders": headers,
        "rawResponse": response,
    }


def capture(limit: int | None) -> None:
    if not os.environ.get("AZURE_DEV_USER_AGENT"):
        raise RuntimeError("Set the skill's user agent inline before running hosted CLI calls")
    groups: dict[str, list[dict[str, Any]]] = {}
    new_count = 0
    for case in CASES:
        path = ARTIFACTS / "cases" / f"{case['id']}.json"
        previous = groups.setdefault(case["conversation"], [])
        if path.exists():
            record = read(path)
            if (
                record["input"] != case["input"]
                or record["agentName"] != AGENT
                or record["agentVersion"] != VERSION
                or record["agentInvoked"] is not True
            ):
                raise RuntimeError("An existing capture has a different input or agent/version")
            previous.append(record)
            continue
        if limit is not None and new_count >= limit:
            break
        command = [
            "azd",
            "ai",
            "agent",
            "invoke",
            AGENT,
            case["input"],
            "--protocol",
            "responses",
            "-e",
            "hotel-2701",
            "--output",
            "raw",
            "--timeout",
            "150",
            "--version",
            VERSION,
        ]
        if previous:
            if not previous[-1].get("sessionId") or not previous[-1].get("conversationId"):
                raise RuntimeError("Cannot continue without actual session and conversation IDs")
            command += [
                "--conversation-id",
                previous[-1]["conversationId"],
            ]
        else:
            command += ["--new-session", "--new-conversation"]
        invocation = subprocess.run(
            command, capture_output=True, text=True, timeout=210, check=False
        )
        raw_path = ARTIFACTS / "raw" / f"{case['id']}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(invocation.stdout, encoding="utf-8")
        if invocation.returncode:
            save(
                path.with_suffix(".failure.json"),
                {
                    "case": case,
                    "agentInvoked": False,
                    "returncode": invocation.returncode,
                    "error": invocation.stderr,
                    "output": invocation.stdout,
                },
            )
            raise RuntimeError(invocation.stderr or invocation.stdout)
        result = parse_invocation(invocation.stdout)
        reference = result["rawResponse"].get("agent_reference", {})
        if reference.get("name") != AGENT or str(reference.get("version")) != VERSION:
            raise RuntimeError("The actual response came from a different agent/version")
        if previous and any(
            result[key] != previous[-1][key] for key in ("sessionId", "conversationId")
        ):
            raise RuntimeError("The actual continuation changed its session or conversation")
        history = [
            {"role": role, "content": value}
            for record in previous
            for role, value in (("user", record["input"]), ("assistant", record["actualResponse"]))
        ]
        record = {
            **case,
            **result,
            "history": history,
            "agentName": AGENT,
            "agentVersion": VERSION,
            "agentInvoked": True,
            "capturedAt": datetime.now(UTC).isoformat(),
            "executionMode": "direct-hosted-invoke-then-evaluate-captured-responses",
            "invocationCommand": command,
            "languageDetected": detected_language(result["actualResponse"]),
            "knowledgeScores": knowledge_scores(result["actualResponse"], case["facts"]),
            "duplicateTextAssertion": duplicate_text_assertion(result["actualResponse"]),
            "invokedTools": [
                item["name"]
                for item in result["rawResponse"].get("output", [])
                if item.get("type") == "function_call"
            ],
        }
        save(path, record)
        previous.append(record)
        new_count += 1
        print(
            json.dumps(
                {
                    key: record[key]
                    for key in (
                        "id",
                        "responseId",
                        "sessionId",
                        "conversationId",
                        "languageDetected",
                        "duplicateTextAssertion",
                    )
                }
            ),
            flush=True,
        )


def api(client: httpx.Client, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    response = client.request(method, path, json=payload)
    if response.is_error:
        raise RuntimeError(f"{response.status_code} {response.text}")
    return response.json()


def transcript_messages(output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in output:
        if item.get("type") == "function_call":
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": item["call_id"],
                            "type": "function",
                            "function": {"name": item["name"], "arguments": item["arguments"]},
                        }
                    ],
                }
            )
        elif item.get("type") == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["call_id"],
                    "content": item["output"],
                }
            )
        elif item.get("type") == "message":
            messages.append(
                {
                    "role": item["role"],
                    "content": "\n".join(
                        part["text"]
                        for part in item.get("content", [])
                        if part.get("type") in {"output_text", "text"}
                    ),
                }
            )
    return messages


def evaluation_rows(records: list[dict[str, Any]], purpose: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        messages = [*record["history"], {"role": "user", "content": record["input"]}]
        query = "\n\n".join(f"{message['role']}: {message['content']}" for message in messages)
        if purpose == "language":
            item = {
                "case_id": record["id"],
                "evaluation_query": query,
                "evaluation_response": record["actualResponse"],
            }
        else:
            item = {
                "id": len(rows) + 1,
                "case_id": record["id"],
                "input": query,
                "expected_output": "Scottsdale valet USD 25/night; pool 07:00–21:00.",
            }
        rows.append(
            {
                "item": item,
                "sample": {
                    "output_text": record["actualResponse"],
                    "output_items": (
                        transcript_messages(record["rawResponse"].get("output", []))
                        if purpose == "knowledge"
                        else record["rawResponse"].get("output", [])
                    ),
                    "tool_definitions": [],
                },
            }
        )
    return rows


def inventory(client: httpx.Client) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for purpose, eval_id in DEFINITIONS.items():
        runs: list[dict[str, Any]] = []
        path = f"evals/{eval_id}/runs?limit=100"
        while True:
            page = api(client, "GET", path)
            runs.extend(page["data"])
            if not page.get("has_more"):
                break
            path = f"evals/{eval_id}/runs?limit=100&after={runs[-1]['id']}"
        results[purpose] = {"data": runs, "has_more": False}
    return results


def existing_version_runs(before: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"purpose": purpose, **run}
        for purpose, result in before.items()
        for run in result["data"]
        if run.get("name", "").startswith(f"hotel-2701-agent-v{VERSION}-")
        or (
            run.get("metadata", {}).get("agent_name") == AGENT
            and run.get("metadata", {}).get("agent_version") == VERSION
        )
    ]


def verify_definitions(client: httpx.Client) -> None:
    verified = {}
    for purpose in ("language", "knowledge"):
        definition = api(client, "GET", f"evals/{DEFINITIONS[purpose]}")
        cache = read(
            ROOT
            / "src/hotel-servicing-agent/.foundry/suites/hotel-2701"
            / f"{definition['name']}.json"
        )["definition"]
        config = definition["data_source_config"]
        schema = (config.get("schema") or {}).get("item") or config.get("item_schema") or {}
        if not schema.get("required") or schema != cache["data_source_config"]["schema"]["item"]:
            raise RuntimeError(f"The {purpose} definition's persisted item schema has changed")
        for field in ("evaluator_name", "evaluator_version", "data_mapping"):
            actual = [criterion.get(field) for criterion in definition["testing_criteria"]]
            expected = [criterion.get(field) for criterion in cache["testing_criteria"]]
            if actual != expected:
                raise RuntimeError(f"The {purpose} definition's {field} has changed")
        verified[purpose] = definition
    save(ARTIFACTS / "definitions-readback.json", verified)


def validate_captures(records: list[dict[str, Any]]) -> None:
    if len(records) != len(CASES):
        raise RuntimeError("The actual capture set is incomplete")
    if len({record["responseId"] for record in records}) != len(records):
        raise RuntimeError("An actual response ID has been reused across cases")
    comparison: list[dict[str, Any]] = []
    baseline = (
        ROOT / "src/hotel-servicing-agent/.foundry/results/hotel-2701/agent-v1-knowledge-language"
    )
    for selected, record in zip(CASES, records, strict=True):
        if (
            record["input"] != selected["input"]
            or record["id"] != selected["id"]
            or record["agentName"] != AGENT
            or record["agentVersion"] != VERSION
            or record["agentInvoked"] is not True
            or not all(record.get(key) for key in ("responseId", "sessionId", "conversationId"))
        ):
            raise RuntimeError("A capture does not match the selected actual-agent case/version")
        if VERSION == "1" or not (baseline / "cases" / f"{record['id']}.json").exists():
            continue
        previous = read(baseline / "cases" / f"{record['id']}.json")
        if previous["input"] != record["input"]:
            raise RuntimeError("The evaluated input differs from the original version-1 case")
        if any(
            previous[key] == record[key] for key in ("responseId", "sessionId", "conversationId")
        ):
            raise RuntimeError("A version-1 actual response/session/conversation was reused")
        comparison.append(
            {
                "caseId": record["id"],
                "evaluatedInputUnchanged": True,
                "newResponseSessionConversationIds": True,
                "version1ResponseId": previous["responseId"],
                "version1DuplicateTextAssertion": duplicate_text_assertion(
                    previous["actualResponse"]
                ),
                "currentDuplicateTextAssertion": duplicate_text_assertion(record["actualResponse"]),
                "version1ArtifactSha256": hashlib.sha256(
                    (baseline / "cases" / f"{record['id']}.json").read_bytes()
                ).hexdigest(),
            }
        )
    save(
        ARTIFACTS / "capture-validation.json",
        {
            "agentVersion": VERSION,
            "agentInvoked": True,
            "actualCaseCount": len(records),
            "uniqueResponseIds": True,
            "staticCandidateResponsesReused": False,
            "version1Comparison": comparison,
        },
    )


def canonical_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for message in messages:
        if message.get("type") in {"function_call", "function_call_output"}:
            message = transcript_messages([message])[0]
        content = message.get("content", "")
        calls = list(message.get("tool_calls", []))
        if isinstance(content, list):
            calls += [part["tool_call"] for part in content if part.get("type") == "tool_call"]
            parts = [
                part.get("text", part.get("tool_result", ""))
                for part in content
                if part.get("type") != "tool_call"
            ]
            content = "\n".join(str(part) for part in parts)
        normalized_calls: list[dict[str, Any]] = []
        for call in calls:
            function = call.get("function", {})
            arguments = function.get("arguments")
            # The service wraps unparseable argument strings in {"input": raw}.
            if isinstance(arguments, dict) and set(arguments) == {"input"}:
                arguments = arguments["input"]
            if isinstance(arguments, str):
                with suppress(json.JSONDecodeError):
                    arguments = json.loads(arguments)
            normalized_calls.append(
                {
                    "id": call.get("id"),
                    "type": call.get("type"),
                    "function": {"name": function.get("name"), "arguments": arguments},
                }
            )
        canonical.append(
            {
                "role": message.get("role"),
                "content": content,
                "tool_calls": normalized_calls,
                "tool_call_id": message.get("tool_call_id"),
            }
        )
    return canonical


def matched_source_row(output: dict[str, Any], expected: dict[str, dict[str, Any]]) -> str | None:
    source = output.get("datasource_item") or {}
    candidates = [source.get("item", source), *(output.get("sample") or {}).get("input", [])]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if case_id not in expected:
            continue
        row = expected[case_id]
        if any(item.get(key) != value for key, value in row["item"].items()):
            continue
        actual_sample = item.get("sample") or source.get("sample")
        if actual_sample:
            mismatches = []
            for key, value in row["sample"].items():
                actual = actual_sample.get(key)
                if key == "output_items" and actual != value:
                    mismatches.append(canonical_messages(actual or []) != canonical_messages(value))
                else:
                    mismatches.append(actual != value)
            if any(mismatches):
                continue
        return str(case_id)
    return None


def evaluate(client: httpx.Client) -> None:
    records = [read(ARTIFACTS / "cases" / f"{case['id']}.json") for case in CASES]
    validate_captures(records)
    verify_definitions(client)
    pending = []
    for purpose in ("language", "knowledge"):
        rows = evaluation_rows(records, purpose)
        signature = hashlib.sha256(
            json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        eval_id = DEFINITIONS[purpose]
        run_name = f"hotel-2701-agent-v{VERSION}-{purpose}-{signature[:12]}"
        existing = api(client, "GET", f"evals/{eval_id}/runs?limit=100")["data"]
        matches = [run for run in existing if run["name"] == run_name]
        if len(matches) > 1:
            raise RuntimeError("Duplicate run names exist; refusing another submission")
        if matches:
            run = matches[0]
        else:
            run = api(
                client,
                "POST",
                f"evals/{eval_id}/runs",
                {
                    "name": run_name,
                    "metadata": {
                        "agent_name": AGENT,
                        "agent_version": VERSION,
                        "agentInvoked": "true",
                        "scope": "knowledge-only",
                    },
                    "data_source": {
                        "type": "jsonl",
                        "source": {
                            "type": "file_content",
                            "content": rows,
                        },
                    },
                },
            )
        result_path = ARTIFACTS / f"{purpose}-evaluation.json"
        if result_path.exists():
            earlier = read(result_path)
            if earlier["runId"] != run["id"]:
                save(ARTIFACTS / "run-history" / f"{earlier['runId']}.json", earlier)
        save(
            result_path,
            {
                "evalId": eval_id,
                "runId": run["id"],
                "runName": run_name,
                "agentName": AGENT,
                "agentVersion": VERSION,
                "agentInvoked": True,
                "executionMode": "direct-hosted-invoke-then-evaluate-captured-responses",
                "inputSha256": signature,
                "inputRows": rows,
                "run": run,
            },
        )
        print(json.dumps({"purpose": purpose, "evalId": eval_id, "runId": run["id"]}), flush=True)
        pending.append((purpose, eval_id, run, result_path, rows))
    for purpose, eval_id, run, result_path, rows in pending:
        deadline = time.monotonic() + 1800
        while run["status"] not in {"completed", "failed", "canceled", "cancelled"}:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Resume existing run {run['id']}")
            time.sleep(10)
            run = api(client, "GET", f"evals/{eval_id}/runs/{run['id']}")
        items = api(client, "GET", f"evals/{eval_id}/runs/{run['id']}/output_items?limit=100")
        result = read(result_path)
        result.update({"run": run, "outputItems": items["data"]})
        expected = {row["item"]["case_id"]: row for row in rows}
        provenance_matches = len(items["data"]) == len(rows)
        for output in items["data"]:
            case_id = matched_source_row(output, expected)
            if case_id is None:
                provenance_matches = False
                continue
            case_path = ARTIFACTS / "cases" / f"{case_id}.json"
            captured = read(case_path)
            captured.setdefault("evaluations", {})[purpose] = {
                "evalId": eval_id,
                "runId": run["id"],
                "outputItemId": output["id"],
                "results": output.get("results", []),
            }
            save(case_path, captured)
        result["inputProvenanceMatches"] = provenance_matches
        save(result_path, result)
        print(
            json.dumps(
                {"purpose": purpose, "status": run["status"], "counts": run.get("result_counts")}
            ),
            flush=True,
        )


def failure_analysis(record: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for purpose, evaluation in record.get("evaluations", {}).items():
        for result in evaluation.get("results", []):
            if result.get("passed") is not False:
                continue
            applicable = result.get("name") not in {
                "temporal-boundary",
                "mail-recipient-integrity",
            }
            unrelated_protocol = any(
                dimension.get("id") == "work_iq_delegated_protocol"
                and dimension.get("applicable") is True
                for dimension in result.get("properties", {}).get("dimension_scores", [])
            ) and not any("work_iq" in name for name in record["observations"]["invokedTools"])
            findings.append(
                {
                    "source": purpose,
                    "evaluator": result.get("name"),
                    "classification": (
                        "rubric/evaluator"
                        if not applicable
                        else "agent behavior and rubric/evaluator"
                        if unrelated_protocol
                        else "agent behavior"
                    ),
                    "applicable": applicable,
                    "reason": result.get("reason"),
                    "applicabilityCaveat": (
                        "Work IQ protocol was marked applicable without any Work IQ operation"
                        if unrelated_protocol
                        else "Mail/temporal behavior is outside these knowledge-only inputs"
                        if not applicable
                        else None
                    ),
                    "actualOutput": record["actualResponse"],
                }
            )
    for assertion, reason, classification in (
        (
            "duplicateTextPassed",
            "Adjacent duplicate text in actual captured output, possible stream/harness defect",
            "harness",
        ),
        (
            "languageDetectedPassed",
            "Detected language differs from the requested language",
            "agent behavior",
        ),
        ("knowledgeFactsPassed", "Local factual assertion failed", "agent behavior"),
        (
            "knowledgeOnlyRoutePassed",
            "Knowledge-only input unnecessarily invoked an operations tool",
            "agent behavior",
        ),
        (
            "propertyIdentityPassed",
            "Knowledge lookup supplied a property ID other than Scottsdale HTL-004",
            "agent behavior",
        ),
    ):
        if record["verdicts"][assertion] is False:
            findings.append(
                {
                    "source": assertion,
                    "classification": classification,
                    "applicable": True,
                    "reason": reason,
                    "actualOutput": record["actualResponse"],
                    "evidence": record["observations"],
                }
            )
    return findings


def summarize() -> None:
    cases: list[dict[str, Any]] = []
    trace_rows: dict[str, dict[str, Any]] = {}
    trace_path = ARTIFACTS / "trace-query-result.json"
    if trace_path.exists():
        for table in read(trace_path).get("tables", []):
            columns = [column["name"] for column in table["columns"]]
            for values in table.get("rows", []):
                row = dict(zip(columns, values, strict=True))
                trace_rows[row["responseId"]] = row
    for selected in CASES:
        path = ARTIFACTS / "cases" / f"{selected['id']}.json"
        record = read(path)
        outputs = record["rawResponse"].get("output", [])
        tool_names = [item["name"] for item in outputs if item.get("type") == "function_call"]
        tool_errors = [
            item["output"]
            for item in outputs
            if item.get("type") == "function_call_output"
            and str(item.get("output", "")).startswith("Error")
        ]
        text = record["actualResponse"]
        duplicate = duplicate_text_assertion(text)
        record["duplicateTextAssertion"] = duplicate
        property_ids = [
            {
                "tool": item["name"],
                "propertyIds": re.findall(r"HTL-\d{3}", item.get("arguments", "")),
                "actualArguments": item.get("arguments", ""),
            }
            for item in outputs
            if item.get("type") == "function_call"
        ]
        record["observations"] = {
            "knowledgeOnlyRoutePassed": set(tool_names).issubset({"search_hotel_knowledge"}),
            "invokedTools": tool_names,
            "toolFailures": tool_errors,
            "duplicatedResponseText": not duplicate["passed"],
            "propertyIdCalls": property_ids,
            "unexpectedPropertyIds": sorted(
                {
                    property_id
                    for call in property_ids
                    for property_id in call["propertyIds"]
                    if property_id != "HTL-004"
                }
            ),
        }
        record["verdicts"] = {
            "duplicateTextPassed": duplicate["passed"],
            "languageDetectedPassed": record["languageDetected"] == record["language"],
            "knowledgeFactsPassed": all(
                score["score"] == 1 for score in record["knowledgeScores"].values()
            ),
            "knowledgeOnlyRoutePassed": record["observations"]["knowledgeOnlyRoutePassed"],
            "propertyIdentityPassed": not record["observations"]["unexpectedPropertyIds"],
            **{
                f"{purpose}Passed": next(
                    (
                        result["passed"]
                        for result in record.get("evaluations", {})
                        .get(purpose, {})
                        .get("results", [])
                        if result.get("metric") == evaluator
                    ),
                    None,
                )
                for purpose, evaluator in (
                    ("language", "language-continuity"),
                    ("knowledge", "hotel-agent-rubric"),
                )
            },
        }
        record["verdicts"]["casePassed"] = all(
            verdict is True for verdict in record["verdicts"].values()
        )
        record["failureAnalysis"] = failure_analysis(record)
        trace = trace_rows.get(record["responseId"])
        record["traceId"] = trace["operation_Id"] if trace else None
        record["spanId"] = trace["id"] if trace else None
        record["traceIdAvailability"] = (
            "Verified against Hotel Application Insights requests by exact response ID"
            if trace
            else "No matching telemetry row; request correlation IDs retained"
        )
        record["correlationIds"] = record.pop("traceIds", record.get("correlationIds", {}))
        save(path, record)
        cases.append(
            {
                key: value
                for key, value in record.items()
                if key not in {"rawResponse", "history", "responseHeaders"}
            }
        )
    summary: dict[str, Any] = {
        "agentName": AGENT,
        "agentVersion": VERSION,
        "agentInvoked": True,
        "executionMode": "direct-hosted-invoke-then-evaluate-captured-responses",
        "actualAgentTurns": len(cases),
        "staticCandidateResponsesReused": False,
        "fabricDependentQuestionsSubmitted": False,
        "runs": {
            purpose: {
                key: value
                for key, value in read(ARTIFACTS / f"{purpose}-evaluation.json").items()
                if key not in {"inputRows", "outputItems"}
            }
            for purpose in ("language", "knowledge")
        },
        "cases": cases,
    }
    primary = [
        result
        for case in cases
        for result in case.get("evaluations", {}).get("knowledge", {}).get("results", [])
        if result.get("metric") == "hotel-agent-rubric"
    ]
    summary["primaryKnowledgeRubricCounts"] = {
        "passed": sum(result.get("passed") is True for result in primary),
        "failed": sum(result.get("passed") is False for result in primary),
        "total": len(primary),
    }
    summary["knowledgeFactsPassed"] = sum(
        all(score["score"] == 1 for score in case["knowledgeScores"].values()) for case in cases
    )
    summary["knowledgeOnlyRoutePassed"] = sum(
        case["observations"]["knowledgeOnlyRoutePassed"] for case in cases
    )
    summary["traceIdsRecovered"] = sum(case["traceId"] is not None for case in cases)
    summary["duplicateTextPassed"] = sum(case["duplicateTextAssertion"]["passed"] for case in cases)
    summary["caseVerdictCounts"] = {
        "passed": sum(case["verdicts"]["casePassed"] for case in cases),
        "failed": sum(not case["verdicts"]["casePassed"] for case in cases),
        "total": len(cases),
    }
    save(ARTIFACTS / "summary.json", summary)
    metadata_path = ROOT / "src/hotel-servicing-agent/.foundry/agent-metadata.hotel-2701.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    selected = metadata.setdefault("environments", {}).setdefault("hotel-2701", {})
    history = selected.setdefault("hostedKnowledgeLanguageEvals", {})
    previous_eval = selected.get("lastHostedKnowledgeLanguageEval")
    if previous_eval:
        history[str(previous_eval["agentVersion"])] = previous_eval
    latest = {
        "agentVersion": VERSION,
        "agentInvoked": True,
        "executionMode": summary["executionMode"],
        "caseCount": len(cases),
        "resultFile": (
            f".foundry/results/hotel-2701/agent-v{VERSION}-knowledge-language/summary.json"
        ),
        "runs": {
            purpose: {
                "evalId": result["evalId"],
                "evalRunId": result["runId"],
                "runName": result["runName"],
                "status": result["run"]["status"],
                "resultCounts": result["run"]["result_counts"],
                "inputProvenanceMatches": result["inputProvenanceMatches"],
            }
            for purpose, result in summary["runs"].items()
        },
        "primaryKnowledgeRubricCounts": summary["primaryKnowledgeRubricCounts"],
        "knowledgeFactsPassed": summary["knowledgeFactsPassed"],
        "knowledgeOnlyRoutePassed": summary["knowledgeOnlyRoutePassed"],
        "traceIdsRecovered": summary["traceIdsRecovered"],
        "duplicateTextPassed": summary["duplicateTextPassed"],
        "caseVerdictCounts": summary["caseVerdictCounts"],
    }
    selected["lastHostedKnowledgeLanguageEval"] = latest
    history[VERSION] = latest
    metadata_path.write_text(
        yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(json.dumps({"summaryPath": str(ARTIFACTS / "summary.json"), "cases": len(cases)}))


def main() -> None:
    global VERSION, ARTIFACTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-version", required=True, type=int)
    parser.add_argument(
        "--stage", choices=("inventory", "capture", "evaluate", "summarize", "all"), default="all"
    )
    parser.add_argument("--capture-limit", type=int)
    args = parser.parse_args()
    if args.agent_version < 1:
        parser.error("--agent-version must be a positive deployed version")
    VERSION = str(args.agent_version)
    ARTIFACTS = ROOT / (
        f"src/hotel-servicing-agent/.foundry/results/hotel-2701/agent-v{VERSION}-knowledge-language"
    )
    if args.stage == "summarize":
        summarize()
        return
    with (
        AzureCliCredential(tenant_id=TENANT) as credential,
        httpx.Client(
            base_url=f"{PROJECT}/openai/",
            params={"api-version": "2025-11-15-preview"},
            headers={
                "Authorization": f"Bearer {credential.get_token('https://ai.azure.com/.default').token}"
            },
            timeout=120,
        ) as client,
    ):
        before = inventory(client)
        inventory_path = ARTIFACTS / "inventory-before.json"
        if not inventory_path.exists():
            save(inventory_path, before)
        save(ARTIFACTS / "inventory-latest.json", before)
        version_runs = existing_version_runs(before)
        print(
            json.dumps(
                {
                    "agentVersion": VERSION,
                    "existingVersionRuns": [
                        {key: run.get(key) for key in ("purpose", "id", "name", "status")}
                        for run in version_runs
                    ],
                }
            ),
            flush=True,
        )
        if (
            version_runs
            and args.stage in {"capture", "all"}
            and not all((ARTIFACTS / "cases" / f"{case['id']}.json").exists() for case in CASES)
        ):
            raise RuntimeError("Existing version runs found; refusing new agent captures")
        if args.stage in {"capture", "all"}:
            capture(args.capture_limit)
        if args.stage in {"evaluate", "all"}:
            evaluate(client)
        if args.stage == "all":
            summarize()


if __name__ == "__main__":
    main()

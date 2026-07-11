from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

FORBIDDEN_NAME = re.compile(r"lyrenza", re.IGNORECASE)
STRUCTURED_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
TEXT_TECHNICAL_SUFFIXES = {".bicep", ".env"}
TECHNICAL_DIRECTORIES = {
    ".github",
    "a365",
    "agent",
    "config",
    "fabric",
    "infra",
    "manifest",
}
CONTENT_FIELDS = {
    "content",
    "description",
    "example",
    "examples",
    "instructions",
    "label",
    "prompt",
    "summary",
    "text",
    "title",
}
TECHNICAL_FIELDS = {
    "agent",
    "agentname",
    "app",
    "appid",
    "application",
    "audience",
    "blueprint",
    "category",
    "clientappid",
    "connection",
    "container",
    "domain",
    "endpoint",
    "environment",
    "host",
    "id",
    "identity",
    "image",
    "index",
    "item",
    "kind",
    "lakehouse",
    "location",
    "manifestversion",
    "model",
    "module",
    "name",
    "namespace",
    "package",
    "path",
    "project",
    "protocol",
    "resource",
    "resourcegroup",
    "scope",
    "semanticmodel",
    "service",
    "sku",
    "subscriptionid",
    "target",
    "tenantid",
    "toolbox",
    "type",
    "upn",
    "url",
    "uri",
    "version",
    "workspace",
}
TECHNICAL_CONTAINERS = {
    "credentials",
    "deployments",
    "env",
    "environments",
    "environmentvariables",
    "parameters",
    "protocols",
    "resources",
    "services",
    "template",
    "toolboxes",
    "tools",
}
TECHNICAL_SUFFIXES = (
    "appid",
    "blueprint",
    "connection",
    "container",
    "domain",
    "endpoint",
    "environment",
    "host",
    "id",
    "identity",
    "index",
    "item",
    "lakehouse",
    "model",
    "name",
    "package",
    "path",
    "project",
    "resource",
    "service",
    "upn",
    "url",
    "uri",
    "workspace",
)


@dataclass(frozen=True, slots=True)
class NamingViolation:
    file: Path
    field: str
    value: str

    def format(self, root: Path) -> str:
        try:
            relative = self.file.relative_to(root)
        except ValueError:
            relative = self.file
        location = f"{relative}:{self.field}"
        return f"{location}: forbidden customer brand in technical value {self.value!r}"


def default_technical_files(root: Path) -> list[Path]:
    candidates: set[Path] = {
        root / "azure.yaml",
        root / "eval.yaml",
        root / "pyproject.toml",
    }
    for pattern in (
        ".env*",
        "src/**/.env*",
        "src/**/.foundry/**/*.yaml",
        "src/**/agent.manifest.yaml",
        "src/**/pyproject.toml",
    ):
        candidates.update(root.glob(pattern))
    for directory in TECHNICAL_DIRECTORIES:
        base = root / directory
        if base.exists():
            candidates.update(path for path in base.rglob("*") if path.is_file())
    return sorted(path for path in candidates if _is_supported(path))


def find_naming_violations(paths: Iterable[Path]) -> list[NamingViolation]:
    violations: list[NamingViolation] = []
    for path in paths:
        if not path.is_file():
            continue
        if FORBIDDEN_NAME.search(path.name):
            violations.append(NamingViolation(path, "<filename>", path.name))
        if path.suffix.lower() in STRUCTURED_SUFFIXES:
            violations.extend(_scan_structured_file(path))
        else:
            violations.extend(_scan_technical_text(path))
    return violations


def _is_supported(path: Path) -> bool:
    return (
        path.suffix.lower() in STRUCTURED_SUFFIXES | TEXT_TECHNICAL_SUFFIXES
        or path.name.startswith(".env")
        or ".env." in path.name
    )


def _scan_structured_file(path: Path) -> list[NamingViolation]:
    data = _load_structured_file(path)
    return list(_walk_structured(path, data))


def _load_structured_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        return tomllib.loads(text)
    return yaml.safe_load(text)


def _walk_structured(
    path: Path,
    value: Any,
    field_path: tuple[str, ...] = (),
    technical_context: bool = False,
) -> Iterable[NamingViolation]:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = _normalize(key)
            child_path = (*field_path, key)
            is_content = normalized in CONTENT_FIELDS
            child_technical = (
                False
                if is_content
                else technical_context
                or _is_technical_field(normalized)
                or normalized in TECHNICAL_CONTAINERS
            )
            if technical_context and FORBIDDEN_NAME.search(key):
                yield NamingViolation(path, ".".join(child_path), key)
            yield from _walk_structured(path, child, child_path, child_technical)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_structured(
                path,
                child,
                (*field_path, str(index)),
                technical_context,
            )
        return
    if technical_context and value is not None:
        text = str(value)
        if FORBIDDEN_NAME.search(text):
            yield NamingViolation(path, ".".join(field_path), text)


def _is_technical_field(normalized: str) -> bool:
    return normalized in TECHNICAL_FIELDS or normalized.endswith(TECHNICAL_SUFFIXES)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _scan_technical_text(path: Path) -> list[NamingViolation]:
    violations: list[NamingViolation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FORBIDDEN_NAME.search(line):
            violations.append(NamingViolation(path, f"line {line_number}", line.strip()))
    return violations

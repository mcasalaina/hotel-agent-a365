from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SOURCE_EXTENSIONS = (
    ".parquet",
    ".csv",
    ".json",
)


@dataclass(frozen=True, slots=True)
class SourceDiscoveryResult:
    root: Path
    matches: dict[str, tuple[Path, ...]]
    missing_tables: tuple[str, ...]


def discover_source_files(root: Path, expected_tables: tuple[str, ...]) -> SourceDiscoveryResult:
    if not root.exists():
        raise FileNotFoundError(f"Source root does not exist: {root}")
    indexed: dict[str, list[Path]] = {}
    for candidate in root.rglob("*"):
        if not candidate.is_file() or not _is_supported_source_file(candidate):
            continue
        normalized = normalize_identifier(_table_like_stem(candidate))
        indexed.setdefault(normalized, []).append(candidate)
    matches: dict[str, tuple[Path, ...]] = {}
    missing: list[str] = []
    for table in expected_tables:
        normalized = normalize_identifier(table)
        found = tuple(sorted(indexed.get(normalized, [])))
        if found:
            matches[table] = found
        else:
            missing.append(table)
    return SourceDiscoveryResult(root=root, matches=matches, missing_tables=tuple(sorted(missing)))


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _table_like_stem(path: Path) -> str:
    name = path.name
    for suffix in (".snappy.parquet", ".parquet", ".csv", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _is_supported_source_file(path: Path) -> bool:
    return any(path.name.endswith(suffix) for suffix in SUPPORTED_SOURCE_EXTENSIONS) or (
        path.name.endswith(".snappy.parquet")
    )

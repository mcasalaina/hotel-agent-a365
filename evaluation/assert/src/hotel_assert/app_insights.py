from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

from hotel_assert.correlation import CorrelationLedger
from hotel_assert.trace_import import TraceImportResult, build_kql, import_rows


def query_and_import(
    *,
    workspace_id: str,
    ledger_path: Path,
    output_directory: Path,
    include_content: bool = False,
) -> TraceImportResult:
    records = CorrelationLedger(ledger_path).read()
    query, start, end = build_kql(records)
    credential = DefaultAzureCredential()
    try:
        response = LogsQueryClient(credential).query_workspace(
            workspace_id,
            query,
            timespan=(start, end),
        )
        if response.status == LogsQueryStatus.PARTIAL:
            raise RuntimeError(f"Application Insights query was partial: {response.partial_error}")
        rows: list[Mapping[str, Any]] = []
        for table in response.tables:
            columns = [str(column) for column in table.columns]
            rows.extend(dict(zip(columns, row, strict=True)) for row in table.rows)
        return import_rows(
            rows=rows,
            records=records,
            output_directory=output_directory,
            include_content=include_content,
        )
    finally:
        credential.close()

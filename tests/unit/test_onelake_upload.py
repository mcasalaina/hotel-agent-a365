from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from upload_onelake_files import OneLakeUploader, main, parse_args

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
LAKEHOUSE_ID = "22222222-2222-2222-2222-222222222222"


@pytest.mark.parametrize(
    ("workspace", "lakehouse", "use_ids", "path"),
    [
        (
            "Hotel Workspace",
            "HotelOperations",
            False,
            "Hotel%20Workspace/HotelOperations.Lakehouse",
        ),
        (WORKSPACE_ID, LAKEHOUSE_ID, True, f"{WORKSPACE_ID}/{LAKEHOUSE_ID}"),
    ],
)
def test_directory_uses_matching_reference_format(
    workspace: str, lakehouse: str, use_ids: bool, path: str
) -> None:
    uploader = OneLakeUploader(workspace, lakehouse, "test-token", use_ids=use_ids)
    with patch("upload_onelake_files.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.status = 201
        uploader.create_directory("Files/data")
    request = urlopen.call_args.args[0]
    assert request.full_url == (
        f"https://onelake.dfs.fabric.microsoft.com/{path}/Files/data?resource=directory"
    )


@pytest.mark.parametrize(
    ("workspace", "lakehouse"),
    [("Hotel Workspace", LAKEHOUSE_ID), (WORKSPACE_ID, "HotelOperations")],
)
def test_id_mode_rejects_non_guid_references(workspace: str, lakehouse: str) -> None:
    with pytest.raises(ValueError):
        OneLakeUploader(workspace, lakehouse, "test-token", use_ids=True)


@pytest.mark.parametrize(
    "references",
    [
        ["--workspace-id", WORKSPACE_ID, "--lakehouse-name", "HotelOperations"],
        ["--workspace-name", "Hotel Workspace", "--lakehouse-id", LAKEHOUSE_ID],
    ],
)
def test_cli_rejects_mixed_reference_formats(
    monkeypatch: pytest.MonkeyPatch, references: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["upload_onelake_files.py", *references])
    with pytest.raises(SystemExit) as error:
        parse_args()
    assert error.value.code == 2
    assert "Use both --workspace-id and --lakehouse-id" in capsys.readouterr().err


def test_cli_preserves_name_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "upload_onelake_files.py",
            "--workspace-name",
            "Hotel Workspace",
            "--lakehouse-name",
            "HotelOperations",
        ],
    )
    args = parse_args()
    assert args.workspace_name == "Hotel Workspace"
    assert args.lakehouse_name == "HotelOperations"
    assert args.use_ids is False


def test_cli_passes_id_mode_to_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "upload_onelake_files.py",
            "--workspace-id",
            WORKSPACE_ID,
            "--lakehouse-id",
            LAKEHOUSE_ID,
        ],
    )
    with patch("upload_onelake_files.upload_source") as upload:
        assert main() == 0
    upload.assert_called_once_with(
        Path("data/generated"),
        Path("data/fixtures/business_scenarios.json"),
        WORKSPACE_ID,
        LAKEHOUSE_ID,
        use_ids=True,
    )

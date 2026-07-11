from __future__ import annotations

from pathlib import Path

from repo_validation.naming import default_technical_files, find_naming_violations


def test_rejects_forbidden_brand_in_technical_name(tmp_path: Path) -> None:
    azure = tmp_path / "azure.yaml"
    azure.write_text(
        "services:\n  agent:\n    name: lyrenza-servicing-agent\n",
        encoding="utf-8",
    )

    violations = find_naming_violations([azure])

    assert [violation.field for violation in violations] == ["services.agent.name"]


def test_allows_forbidden_brand_in_customer_facing_description(tmp_path: Path) -> None:
    manifest = tmp_path / "agent.manifest.yaml"
    manifest.write_text(
        "template:\n"
        "  name: hotel-servicing-agent\n"
        "  description: Customer support for Lyrenza Hotels\n",
        encoding="utf-8",
    )

    assert find_naming_violations([manifest]) == []


def test_default_scan_excludes_customer_docs_and_data(tmp_path: Path) -> None:
    docs = tmp_path / "foundryiq-docs" / "properties"
    data = tmp_path / "data" / "fixtures"
    docs.mkdir(parents=True)
    data.mkdir(parents=True)
    (docs / "property.md").write_text("Lyrenza property profile", encoding="utf-8")
    (data / "guest.json").write_text('{"brand": "Lyrenza"}', encoding="utf-8")
    (tmp_path / "azure.yaml").write_text("name: hotel-agent-a365\n", encoding="utf-8")

    files = default_technical_files(tmp_path)

    assert docs / "property.md" not in files
    assert data / "guest.json" not in files
    assert find_naming_violations(files) == []


def test_rejects_forbidden_brand_in_environment_value(tmp_path: Path) -> None:
    env = tmp_path / ".env.example"
    env.write_text("AZURE_RESOURCE_GROUP=rg-lyrenza-agent\n", encoding="utf-8")

    violations = find_naming_violations([env])

    assert len(violations) == 1
    assert violations[0].field == "line 1"


def test_rejects_forbidden_brand_in_service_mapping_key(tmp_path: Path) -> None:
    azure = tmp_path / "azure.yaml"
    azure.write_text(
        "services:\n  lyrenza-agent:\n    host: azure.ai.agent\n",
        encoding="utf-8",
    )

    violations = find_naming_violations([azure])

    assert any(violation.field == "services.lyrenza-agent" for violation in violations)


def test_rejects_forbidden_brand_in_identity_display_name(tmp_path: Path) -> None:
    config = tmp_path / "a365.config.example.json"
    config.write_text(
        '{"agentIdentityDisplayName": "Lyrenza Guest Services Identity"}',
        encoding="utf-8",
    )

    violations = find_naming_violations([config])

    assert [violation.field for violation in violations] == ["agentIdentityDisplayName"]

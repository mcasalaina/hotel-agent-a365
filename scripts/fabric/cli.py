from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fabric.artifacts import FabricTopology, load_notebook_contracts
from fabric.auth import AuthMode, build_credential
from fabric.client import FabricRestClient
from fabric.deployer import FabricDeployer
from fabric.validation import validate_topology

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOPOLOGY = REPOSITORY_ROOT / "fabric" / "topology.json"
DEFAULT_STATE = REPOSITORY_ROOT / "scripts" / "fabric" / "deployment-state" / "fabric-state.json"


@dataclass(frozen=True, slots=True)
class CliOptions:
    command: str
    topology_path: Path
    state_path: Path
    source_root: Path | None
    auth_mode: AuthMode
    discover_remote: bool
    workspace_id: str | None
    dry_run: bool


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    options = _load_options(args)
    topology = FabricTopology.from_file(options.topology_path, REPOSITORY_ROOT)
    contracts = load_notebook_contracts(topology.contract_file)
    problems = validate_topology(topology, contracts)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1

    client = None
    if options.command == "apply" or options.discover_remote:
        client = FabricRestClient(build_credential(options.auth_mode))

    deployer = FabricDeployer(
        topology=topology,
        contracts=contracts,
        state_path=options.state_path,
        client=client,
        source_root=options.source_root,
        workspace_id_override=options.workspace_id,
    )

    if options.command == "validate":
        print("Fabric topology and notebook contracts are valid.")
        return 0
    if options.command == "plan":
        operations, state = deployer.build_plan(discover_remote=options.discover_remote)
        for operation in operations:
            print(
                f"{operation.action:>6} {operation.item_type:<10} "
                f"{operation.display_name} :: {operation.detail}"
            )
        print(f"State written to {options.state_path}")
        if state.get("sourceDiscovery"):
            print(json.dumps(state["sourceDiscovery"], indent=2, sort_keys=True))
        return 0

    state = deployer.apply(dry_run=options.dry_run)
    print(f"Deployment state written to {options.state_path}")
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or apply Microsoft Fabric foundational artifacts."
    )
    parser.add_argument("command", choices=("validate", "plan", "apply"))
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional JSON file that prepopulates CLI options.",
    )
    parser.add_argument("--topology", type=Path, default=DEFAULT_TOPOLOGY)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument(
        "--auth-mode",
        choices=("default", "azure-cli", "device-code", "chained"),
        default="azure-cli",
    )
    parser.add_argument("--discover-remote", action="store_true")
    parser.add_argument("--workspace-id")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute Fabric mutations. Without this flag, apply is a dry run.",
    )
    return parser


def _load_options(args: argparse.Namespace) -> CliOptions:
    values: dict[str, Any] = {}
    if isinstance(args.config, Path):
        values = json.loads(args.config.read_text(encoding="utf-8"))

    def configured_path(name: str, default: Path) -> Path:
        raw = getattr(args, name)
        if isinstance(raw, Path) and raw != default:
            return raw
        configured = values.get(name)
        if isinstance(configured, str):
            return (REPOSITORY_ROOT / configured).resolve()
        return default

    raw_source_root = args.source_root
    if raw_source_root is None and isinstance(values.get("sourceRoot"), str):
        raw_source_root = (REPOSITORY_ROOT / values["sourceRoot"]).resolve()

    discover_remote = args.discover_remote or bool(values.get("discoverRemote"))
    workspace_id = args.workspace_id or _string_or_none(values.get("workspaceId"))
    auth_mode = args.auth_mode
    configured_auth_mode = _string_or_none(values.get("authMode"))
    if configured_auth_mode and args.auth_mode == "azure-cli":
        auth_mode = configured_auth_mode

    return CliOptions(
        command=args.command,
        topology_path=configured_path("topology", DEFAULT_TOPOLOGY),
        state_path=configured_path("state", DEFAULT_STATE),
        source_root=raw_source_root,
        auth_mode=auth_mode,
        discover_remote=discover_remote,
        workspace_id=workspace_id,
        dry_run=not args.execute,
    )


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())

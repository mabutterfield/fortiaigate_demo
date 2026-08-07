#!/usr/bin/env python3
"""Print the deterministic Phase 11 matrix for installed local scenarios."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import scenario_local
    import scenario_matrix
    import scenario_profiles
except ModuleNotFoundError:
    from scripts import scenario_local, scenario_matrix, scenario_profiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic LiteLLM/chatbot/MCP/FAIG objects from installed scenarios."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path. Without this option, print to stdout.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output file.",
    )
    parser.add_argument(
        "--debug-all-server-tools",
        action="store_true",
        help="Include the explicit troubleshooting profile exposing all MCP server tools.",
    )
    parser.add_argument(
        "--fortiweb-mcp-desired",
        dest="fortiweb_mcp_desired",
        action="store_true",
        default=True,
        help="Request FortiWeb MCP generation when installed and configured (default).",
    )
    parser.add_argument(
        "--no-fortiweb-mcp",
        dest="fortiweb_mcp_desired",
        action="store_false",
        help="Explicitly disable FortiWeb MCP generation and use Direct MCP.",
    )
    parser.add_argument(
        "--fortiweb-installed",
        action="store_true",
        help="Declare FortiWeb available for this dry-run matrix.",
    )
    parser.add_argument(
        "--fortiweb-mcp-base-url",
        default="",
        help="FortiWeb MCP endpoint used only when installed and desired.",
    )
    parser.add_argument(
        "--fortigate-routes-desired",
        action="store_true",
        help="Request FortiGate routes; the current baseline emits a deferred warning and no routes.",
    )
    parser.add_argument(
        "--disable-faig-chain",
        dest="faig_chain_available",
        action="store_false",
        default=True,
        help="Disable the globally available FAIG re-entry capability.",
    )
    parser.add_argument(
        "--faig-chain-reentry-uri",
        default="/v1/passthrough",
        help="Global FAIG re-entry URI. Enabled chains require /v1/passthrough.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = scenario_local.LocalScenarioStore()
    try:
        scenario_profiles.validate_local_matrix(store)
        matrix = scenario_matrix.build_scenario_matrix(
            store.matrix_summary(),
            capabilities={
                "fortiweb_mcp_desired": args.fortiweb_mcp_desired,
                "fortiweb_installed": args.fortiweb_installed,
                "fortiweb_mcp_base_url": args.fortiweb_mcp_base_url,
                "fortigate_routes_desired": args.fortigate_routes_desired,
                "faig_chain_available": args.faig_chain_available,
                "faig_chain_reentry_uri": args.faig_chain_reentry_uri,
            },
            include_debug_all_server_tools=args.debug_all_server_tools,
        )
        rendered = scenario_matrix.canonical_json(matrix)
        if args.output:
            output_path = args.output.resolve()
            if output_path.exists() and not args.force:
                raise scenario_matrix.ScenarioMatrixError(
                    f"Output already exists: {output_path}. Use --force to replace it."
                )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
            print(f"wrote: {scenario_local.relative_to_repo(output_path)}")
        else:
            print(rendered, end="")
    except (
        OSError,
        scenario_local.LocalScenarioError,
        scenario_matrix.ScenarioMatrixError,
    ) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

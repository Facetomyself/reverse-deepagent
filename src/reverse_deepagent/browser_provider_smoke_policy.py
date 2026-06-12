from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from reverse_deepagent.browser_provider_smoke import review_browser_provider_smoke_json
from reverse_deepagent.browser_provider_smoke_acceptance import SUPPORTED_MINIMUM_EVIDENCE_LEVELS

BROWSER_PROVIDER_SMOKE_POLICY_GATE_SCHEMA = "reverse-deepagent.browser-provider-smoke-policy-gate.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Review an existing BrowserProvider smoke JSON as a side-effect-free CI/PR policy gate. "
            "The gate never generates smoke, resolves providers, invokes factories, checks availability, "
            "launches browsers, probes CDP endpoints, writes artifacts, calls MCP, or touches mobile runtimes."
        )
    )
    parser.add_argument("--smoke-json", required=True, help="Existing UTF-8 workspace/browser-provider-smoke.json object to review.")
    parser.add_argument("--expected-provider", default=None, help="Expected BrowserProvider id for provider-match checks.")
    parser.add_argument(
        "--minimum-evidence-level",
        default="launch-smoke",
        choices=SUPPORTED_MINIMUM_EVIDENCE_LEVELS,
        help="Minimum smoke evidence level required by this CI/PR gate. Defaults to launch-smoke.",
    )
    parser.add_argument(
        "--block-on-warnings",
        action="store_true",
        help="Treat acceptance warnings as blocking policy failures.",
    )
    return parser


def browser_provider_smoke_policy_gate(
    *,
    smoke_json_path: str | Path,
    expected_provider_id: str | None = None,
    minimum_evidence_level: str = "launch-smoke",
    block_on_warnings: bool = False,
) -> dict[str, Any]:
    """Run the BrowserProvider smoke policy gate against an existing evidence JSON."""

    review = review_browser_provider_smoke_json(
        smoke_json_path=smoke_json_path,
        expected_provider_id=expected_provider_id,
        minimum_evidence_level=minimum_evidence_level,
        block_on_warnings=block_on_warnings,
    )
    policy_decision = review.get("policy_decision") if isinstance(review.get("policy_decision"), dict) else {}
    acceptance = review.get("attachment_acceptance") if isinstance(review.get("attachment_acceptance"), dict) else {}
    ok = bool(review.get("ok")) and bool(policy_decision.get("policy_passed"))
    return {
        "schema_version": BROWSER_PROVIDER_SMOKE_POLICY_GATE_SCHEMA,
        "ok": ok,
        "mode": "browser-provider-smoke-policy-gate",
        "smoke_json_path": str(Path(smoke_json_path).expanduser()),
        "expected_provider_id": expected_provider_id or None,
        "minimum_evidence_level": minimum_evidence_level,
        "block_on_warnings": bool(block_on_warnings),
        "policy_decision": policy_decision,
        "attachment_acceptance": acceptance,
        "acceptance_report": review.get("acceptance_report"),
        "review": review,
        "ci_gate": {
            "policy_passed": bool(policy_decision.get("policy_passed")),
            "decision": policy_decision.get("decision"),
            "observed_evidence_level": policy_decision.get("observed_evidence_level"),
            "minimum_evidence_level": policy_decision.get("minimum_evidence_level"),
            "runtime_launch_smoke_accepted": bool(acceptance.get("runtime_launch_smoke_accepted")),
        },
        "side_effect_policy": {
            "metadata_only": True,
            "reads_existing_smoke_json": True,
            "evaluates_policy": True,
            "writes_artifact": False,
            "provider_registry_resolved": False,
            "provider_factories_invoked": False,
            "availability_check_requested": False,
            "launch_smoke_requested": False,
            "cdp_endpoint_probed": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
        "next_action": review.get("next_action"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = browser_provider_smoke_policy_gate(
        smoke_json_path=args.smoke_json,
        expected_provider_id=args.expected_provider,
        minimum_evidence_level=args.minimum_evidence_level,
        block_on_warnings=args.block_on_warnings,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

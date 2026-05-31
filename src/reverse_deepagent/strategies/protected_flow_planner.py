from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class ProtectedFlowTriagePlan:
    """Plan-only hook/debugger guidance for protected Web signing flows."""

    status: str
    categories: list[str]
    findings: list[dict[str, Any]]
    hook_plans: list[dict[str, Any]] = field(default_factory=list)
    runtime_artifacts: list[dict[str, Any]] = field(default_factory=list)
    review_hints: list[dict[str, Any]] = field(default_factory=list)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "categories": self.categories,
            "findings": self.findings,
            "hook_plans": self.hook_plans,
            "runtime_artifacts": self.runtime_artifacts,
            "review_hints": self.review_hints,
            "side_effect_policy": self.side_effect_policy,
            "summary": {
                "category_count": len(self.categories),
                "finding_count": len(self.findings),
                "hook_plan_count": len(self.hook_plans),
                "runtime_artifact_count": len(self.runtime_artifacts),
                "review_hint_count": len(self.review_hints),
            },
        }


def build_protected_flow_triage_plan(strategy: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a conservative plan-only hook/debugger guide from a protected-flow strategy.

    This planner does not install hooks, patch code, start browsers, inspect WASM binaries,
    or execute module-federation / VM entrypoints. It only translates detector evidence into
    stable reviewable plan records that downstream subagents can consume.
    """

    if not isinstance(strategy, Mapping):
        return _empty_plan("missing_strategy")
    triage = strategy.get("triage") if isinstance(strategy.get("triage"), Mapping) else {}
    findings = [dict(item) for item in triage.get("findings", []) if isinstance(item, Mapping)] if isinstance(triage, Mapping) else []
    categories = sorted({str(item) for item in triage.get("categories", []) if item} | {str(item.get("category")) for item in findings if item.get("category")})
    if not categories and not findings:
        return _empty_plan("no_protected_flow_markers")

    hook_plans = _hook_plans_for_categories(categories, findings)
    runtime_artifacts = _runtime_artifact_plans(categories)
    review_hints = _review_hints_for_categories(categories, findings)
    return ProtectedFlowTriagePlan(
        status="planned",
        categories=categories,
        findings=[_safe_finding(item) for item in findings],
        hook_plans=hook_plans,
        runtime_artifacts=runtime_artifacts,
        review_hints=review_hints,
        side_effect_policy={
            "plan_only": True,
            "installs_hooks": False,
            "patches_runtime": False,
            "starts_browser": False,
            "calls_mcp": False,
            "executes_target_code": False,
            "inspects_wasm_binary": False,
            "executes_module_federation_get_init": False,
            "mobile_full_runtime_chain": False,
        },
    ).to_dict()


def _empty_plan(reason: str) -> dict[str, Any]:
    return ProtectedFlowTriagePlan(
        status="not_applicable",
        categories=[],
        findings=[],
        side_effect_policy={
            "plan_only": True,
            "installs_hooks": False,
            "patches_runtime": False,
            "starts_browser": False,
            "calls_mcp": False,
            "executes_target_code": False,
            "inspects_wasm_binary": False,
            "executes_module_federation_get_init": False,
            "mobile_full_runtime_chain": False,
            "reason": reason,
        },
    ).to_dict()


def _hook_plans_for_categories(categories: Iterable[str], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    category_set = set(categories)
    plans: list[dict[str, Any]] = []
    if "wasm" in category_set:
        plans.extend(
            [
                _hook_plan(
                    plan_id="wasm-instantiation-observe",
                    category="wasm",
                    target="WebAssembly.instantiate|instantiateStreaming|compile|compileStreaming",
                    recommended_subagent="hook",
                    artifact_keys=["workspace/wasm-runtime-candidates.json", "workspace/hook-timeline.json"],
                    purpose="Record WASM instantiation site, module URL/source, imports shape, and export names before porting.",
                    blockers=["requires runtime session with JS evaluation support", "does not inspect binary bytes in this plan-only baseline"],
                ),
                _hook_plan(
                    plan_id="wasm-fetch-observe",
                    category="wasm",
                    target="fetch/xhr requests ending in .wasm",
                    recommended_subagent="web_recon",
                    artifact_keys=["workspace/network-requests.json", "workspace/source-contexts.json"],
                    purpose="Link WASM binary request metadata and initiator evidence to the signing flow.",
                    blockers=["response body capture depends on provider CDP/network capabilities"],
                ),
            ]
        )
    if "vm" in category_set or "obfuscation" in category_set:
        plans.extend(
            [
                _hook_plan(
                    plan_id="vm-dispatcher-candidate-observe",
                    category="vm",
                    target="opcode dispatcher / bytecode loop / dispatch table",
                    recommended_subagent="debugger",
                    artifact_keys=["workspace/vm-dispatcher-candidates.json", "workspace/source-logpoints.json"],
                    purpose="Collect dispatcher candidate snippets, opcode table references, and source-logpoint candidates without executing unknown bytecode.",
                    blockers=["dispatcher semantics are not proven portable", "arbitrary custom loader traversal remains follow-up work"],
                ),
                _hook_plan(
                    plan_id="runtime-code-generation-observe",
                    category="obfuscation",
                    target="eval / Function / runtime decoded payload",
                    recommended_subagent="hook",
                    artifact_keys=["workspace/protection-triage-hooks.json", "workspace/hook-timeline.json"],
                    purpose="Record runtime code-generation entrypoints and decoded payload provenance for manual review.",
                    blockers=["plan does not execute or unwrap packed code automatically"],
                ),
            ]
        )
    if "anti_debug" in category_set:
        plans.append(
            _hook_plan(
                plan_id="anti-debug-observe",
                category="anti_debug",
                target="debugger / timing / devtools / function integrity checks",
                recommended_subagent="protector",
                artifact_keys=["workspace/protection-result.json", "workspace/debugger-timeline.json"],
                purpose="Plan minimal auditable anti-debug observation or neutralization before runtime-assisted replay.",
                blockers=["patches must remain explicit and auditable", "default recon must not silently disable target checks"],
            )
        )
    if "dynamic_secret" in category_set:
        plans.append(
            _hook_plan(
                plan_id="dynamic-secret-source-observe",
                category="dynamic_secret",
                target="challenge / nonce / native bridge / fingerprint source",
                recommended_subagent="web_recon",
                artifact_keys=["workspace/runtime-context.json", "workspace/runtime-context-diff.json"],
                purpose="Separate stable runtime context from session-bound or volatile challenge inputs.",
                blockers=["server-bound or native bridge secrets cannot be hard-coded into pure rebuild output"],
            )
        )
    return _dedupe_plans(plans, findings)


def _hook_plan(
    *,
    plan_id: str,
    category: str,
    target: str,
    recommended_subagent: str,
    artifact_keys: list[str],
    purpose: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "category": category,
        "target": target,
        "recommended_subagent": recommended_subagent,
        "artifact_keys": artifact_keys,
        "purpose": purpose,
        "blockers": blockers,
        "execution_mode": "plan_only_explicit_request_required",
        "would_install_hook": False,
        "would_patch_runtime": False,
        "review_required": True,
    }


def _dedupe_plans(plans: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers_by_category: dict[str, list[str]] = {}
    for finding in findings:
        category = str(finding.get("category") or "")
        marker = str(finding.get("marker") or "")
        if category and marker:
            markers_by_category.setdefault(category, []).append(marker)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plan in plans:
        plan_id = str(plan.get("plan_id"))
        if plan_id in seen:
            continue
        seen.add(plan_id)
        category = str(plan.get("category") or "")
        markers = sorted(dict.fromkeys(markers_by_category.get(category, [])))
        output.append({**plan, "evidence_markers": markers})
    return output


def _runtime_artifact_plans(categories: Iterable[str]) -> list[dict[str, Any]]:
    category_set = set(categories)
    artifacts: list[dict[str, Any]] = [
        {
            "artifact_key": "workspace/protection-triage-hooks.json",
            "virtual_uri": "virtual://workspace/hooks/protection-triage-hooks.json",
            "producer": "strategy",
            "status": "planned",
            "description": "Plan-only protected-flow hook/debugger recommendations.",
        }
    ]
    if "wasm" in category_set:
        artifacts.append(
            {
                "artifact_key": "workspace/wasm-runtime-candidates.json",
                "virtual_uri": "virtual://workspace/runtime/wasm-runtime-candidates.json",
                "producer": "hook|web_recon",
                "status": "planned",
                "description": "WASM instantiation, imports/exports, and binary request candidate metadata.",
            }
        )
    if "vm" in category_set or "obfuscation" in category_set:
        artifacts.append(
            {
                "artifact_key": "workspace/vm-dispatcher-candidates.json",
                "virtual_uri": "virtual://workspace/runtime/vm-dispatcher-candidates.json",
                "producer": "debugger|hook",
                "status": "planned",
                "description": "VM dispatcher, opcode table, and runtime code-generation candidate metadata.",
            }
        )
    return artifacts


def _review_hints_for_categories(categories: Iterable[str], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    category_list = sorted(set(categories))
    evidence = [f"categories={','.join(category_list)}", f"finding_count={len(findings)}"]
    hints = [
        {
            "severity": "risk",
            "category": "protected_flow",
            "code": "protected_flow_runtime_triage_required",
            "message": "Protected WASM / VM / obfuscation markers require runtime-assisted triage before pure rebuild delivery.",
            "evidence": evidence,
        }
    ]
    if "wasm" in category_list:
        hints.append(
            {
                "severity": "warning",
                "category": "protected_flow",
                "code": "wasm_metadata_required",
                "message": "WASM module metadata should be captured before claiming portable semantics.",
                "evidence": [*evidence, "artifact=workspace/wasm-runtime-candidates.json"],
            }
        )
    if "vm" in category_list or "obfuscation" in category_list:
        hints.append(
            {
                "severity": "warning",
                "category": "protected_flow",
                "code": "vm_dispatcher_review_required",
                "message": "VM dispatcher or runtime code-generation candidates require manual semantic review.",
                "evidence": [*evidence, "artifact=workspace/vm-dispatcher-candidates.json"],
            }
        )
    return hints


def _safe_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    snippet = str(finding.get("snippet") or "")[:240]
    return {
        "category": str(finding.get("category") or "unknown"),
        "marker": str(finding.get("marker") or "unknown"),
        "snippet_digest": hashlib.sha256(snippet.encode("utf-8")).hexdigest()[:16] if snippet else "",
        "snippet_preview": snippet,
    }

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .source_maps import (
    SourceMapFollowthroughCompletionCheckpointManager,
    SourceMapSelectedExecutorApplyPreflightManager,
    SourceMapTypedPayloadPreflightSpec,
)


@dataclass(slots=True)
class SourceMapTerminalReviewPackageSpec:
    """Read-only terminal review package / audit handoff after a Source Map completion checkpoint."""

    source_map_followthrough_completion_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_selected_executor_result_checkpoint: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_completion_checkpoint_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewPackageSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_package",
                "sourceMapTerminalReviewPackage",
                "source_map_followthrough_terminal_review_package",
                "sourceMapFollowthroughTerminalReviewPackage",
                "source_map_terminal_review_handoff",
                "sourceMapTerminalReviewHandoff",
                "source_map_followthrough_audit_handoff",
                "sourceMapFollowthroughAuditHandoff",
            )
        )
        completion = cls._object_alias(
            context,
            "source_map_followthrough_completion_checkpoint",
            "source-map-followthrough-completion-checkpoint",
            "sourceMapFollowthroughCompletionCheckpoint",
            "source_map_followthrough_completion_review",
            "source-map-followthrough-completion-review",
            "sourceMapFollowthroughCompletionReview",
            "source_map_followthrough_next_action_checkpoint",
            "source-map-followthrough-next-action-checkpoint",
            "sourceMapFollowthroughNextActionCheckpoint",
        )
        result_checkpoint = cls._object_alias(
            context,
            "source_map_selected_executor_result_checkpoint",
            "source-map-selected-executor-result-checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "source-map-followthrough-result-checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
        if not requested and not completion:
            return None
        return cls(
            source_map_followthrough_completion_checkpoint=completion,
            source_map_selected_executor_result_checkpoint=result_checkpoint,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_completion_checkpoint_digest_sha256=str(context.get("expected_completion_checkpoint_digest_sha256", context.get("expectedCompletionCheckpointDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewPackageResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewPackageManager:
    """Package a completion checkpoint into a terminal review / audit handoff descriptor without executing next actions."""

    def review(self, spec: SourceMapTerminalReviewPackageSpec | None) -> SourceMapTerminalReviewPackageResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewPackageResult(status="unsupported", reason="missing_source_map_terminal_review_package_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewPackageResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_package_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewPackageResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_package_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewPackageSpec) -> dict[str, Any]:
        completion = spec.source_map_followthrough_completion_checkpoint
        result_checkpoint = spec.source_map_selected_executor_result_checkpoint
        completion_digest = self._stable_json_digest(completion) if completion else ""
        result_checkpoint_digest = self._stable_json_digest(result_checkpoint) if result_checkpoint else ""
        consumer = self._normalize_consumer(str(completion.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(completion.get("selected_action_id") or "")
        blockers = self._blockers(spec, completion, result_checkpoint, consumer, action_id, completion_digest)
        review_package = self._review_package(completion, result_checkpoint, consumer, completion_digest, result_checkpoint_digest, bool(blockers))
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
            "status": status,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(completion.get("selected_review_gate") or ""),
            "application_surface": str(completion.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(completion.get("reviewer") or ""),
            "source_completion_checkpoint_schema_version": str(completion.get("schema_version") or "") if completion else "",
            "source_completion_checkpoint_status": self._status(completion),
            "source_completion_checkpoint_digest_sha256": completion_digest,
            "expected_completion_checkpoint_digest_sha256": spec.expected_completion_checkpoint_digest_sha256,
            "source_result_checkpoint_schema_version": str(result_checkpoint.get("schema_version") or "") if result_checkpoint else "",
            "source_result_checkpoint_digest_sha256": result_checkpoint_digest,
            "completion_checkpoint_verified": bool(completion) and not blockers,
            "result_checkpoint_attached": bool(result_checkpoint),
            "terminal_review_candidate": bool(completion.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(completion.get("followup_required")) and not blockers,
            "completion_status": str(completion.get("completion_status") or ("blocked" if blockers else "review_required")),
            "terminal_review_package": review_package,
            "ready_for_terminal_review": not blockers,
            "ready_for_audit_handoff_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_package": False,
            "source_logpoint_install_invoked_by_package": False,
            "rebuild_invoked_by_package": False,
            "delivery_invoked_by_package": False,
            "browser_started_by_package": False,
            "cdp_command_sent_by_package": False,
            "runtime_evaluated_by_package": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(completion),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
            "status": status,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "reason": reason,
            "selected_consumer": "",
            "completion_status": status,
            "ready_for_terminal_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_followthrough_completion_checkpoint",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewPackageSpec,
        completion: dict[str, Any],
        result_checkpoint: dict[str, Any],
        consumer: str,
        action_id: str,
        completion_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not completion:
            return ["source_map_followthrough_completion_checkpoint_missing"]
        if completion.get("schema_version") != "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1":
            blockers.append("source_map_followthrough_completion_checkpoint_schema_mismatch")
        if cls._status(completion) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_followthrough_completion_checkpoint_not_ready")
        if completion.get("ready_for_completion_review") is not True or completion.get("completion_checkpoint_ready") is not True:
            blockers.append("source_map_followthrough_completion_checkpoint_not_verified")
        if not completion.get("terminal_review_candidate") and not completion.get("followup_required"):
            blockers.append("source_map_followthrough_completion_checkpoint_no_terminal_or_followup_state")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_completion_checkpoint_digest_sha256 and spec.expected_completion_checkpoint_digest_sha256 != completion_digest:
            blockers.append("source_map_followthrough_completion_checkpoint_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "debugger_continuation_invoked", "rebuild_invoked_by_completion", "delivery_invoked_by_completion"):
            if completion.get(key) is True:
                blockers.append(f"source_map_followthrough_completion_checkpoint_{key}_forbidden")
        if result_checkpoint:
            if result_checkpoint.get("schema_version") != "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1":
                blockers.append("source_map_selected_executor_result_checkpoint_schema_mismatch")
            if consumer and result_checkpoint.get("selected_consumer") and cls._normalize_consumer(str(result_checkpoint.get("selected_consumer"))) != consumer:
                blockers.append("source_map_selected_executor_result_checkpoint_consumer_mismatch")
        return blockers

    @classmethod
    def _review_package(cls, completion: dict[str, Any], result_checkpoint: dict[str, Any], consumer: str, completion_digest: str, result_checkpoint_digest: str, blocked: bool) -> dict[str, Any]:
        if not completion:
            return {}
        completion_review = completion.get("completion_review") if isinstance(completion.get("completion_review"), dict) else {}
        recommended = str(completion_review.get("recommended_review_action") or completion.get("next_action") or "review_source_map_followthrough_completion_checkpoint")
        required_artifacts = completion_review.get("required_artifacts") if isinstance(completion_review.get("required_artifacts"), list) else []
        package_kind = "blocked" if blocked else "followup-review-package" if completion.get("followup_required") else "terminal-review-package"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.payload.v1",
            "package_kind": package_kind,
            "selected_consumer": consumer,
            "selected_action_id": str(completion.get("selected_action_id") or ""),
            "application_surface": str(completion.get("application_surface") or ""),
            "completion_status": str(completion.get("completion_status") or ""),
            "terminal_review_candidate": bool(completion.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(completion.get("followup_required")) and not blocked,
            "recommended_review_action": recommended,
            "required_artifacts": required_artifacts,
            "completion_checkpoint_digest_sha256": completion_digest,
            "result_checkpoint_digest_sha256": result_checkpoint_digest,
            "result_checkpoint_attached": bool(result_checkpoint),
            "manual_review_required": True,
            "execute_recommended_action": False,
            "review_steps": cls._review_steps(completion, recommended, required_artifacts, bool(result_checkpoint)),
        }

    @staticmethod
    def _review_steps(completion: dict[str, Any], recommended: str, required_artifacts: list[Any], has_result_checkpoint: bool) -> list[dict[str, Any]]:
        steps = [
            {"order": 1, "action": "inspect_source_map_followthrough_completion_checkpoint", "artifact": "workspace/source-map-followthrough-completion-checkpoint.json", "required": True},
        ]
        if has_result_checkpoint:
            steps.append({"order": len(steps) + 1, "action": "inspect_source_map_selected_executor_result_checkpoint", "artifact": "workspace/source-map-selected-executor-result-checkpoint.json", "required": False})
        for artifact in required_artifacts:
            steps.append({"order": len(steps) + 1, "action": "inspect_required_source_map_review_artifact", "artifact": str(artifact), "required": True})
        steps.append({"order": len(steps) + 1, "action": recommended, "artifact": "", "required": bool(recommended), "execute_automatically": False})
        return steps

    @staticmethod
    def _warnings(completion: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_package_does_not_execute_recommended_action"]
        if completion:
            warnings.append("source_map_terminal_review_package_requires_manual_review")
        if completion.get("followup_required") is True:
            warnings.append("source_map_terminal_review_package_followup_required")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_followthrough_completion_checkpoint_missing" for item in blockers):
            return "provide_source_map_followthrough_completion_checkpoint"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_package_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_package_failure"
        return "review_source_map_terminal_review_package"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_handoff_only": True,
            "terminal_review_package_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewClosureCheckpointSpec:
    """Read-only observed-result / closure audit checkpoint after a Source Map terminal review package."""

    source_map_terminal_review_package: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_observed_result: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_terminal_review_package_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewClosureCheckpointSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_closure_checkpoint",
                "sourceMapTerminalReviewClosureCheckpoint",
                "source_map_terminal_review_observed_result_checkpoint",
                "sourceMapTerminalReviewObservedResultCheckpoint",
                "source_map_followthrough_closure_audit",
                "sourceMapFollowthroughClosureAudit",
                "source_map_terminal_review_closure_audit",
                "sourceMapTerminalReviewClosureAudit",
            )
        )
        package = cls._object_alias(
            context,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
            "source_map_terminal_review_handoff",
            "source-map-terminal-review-handoff",
            "sourceMapTerminalReviewHandoff",
            "source_map_followthrough_audit_handoff",
            "source-map-followthrough-audit-handoff",
            "sourceMapFollowthroughAuditHandoff",
        )
        observed = cls._object_alias(
            context,
            "source_map_terminal_review_observed_result",
            "source-map-terminal-review-observed-result",
            "sourceMapTerminalReviewObservedResult",
            "source_map_terminal_review_result",
            "source-map-terminal-review-result",
            "sourceMapTerminalReviewResult",
            "source_map_followthrough_terminal_review_observed_result",
            "source-map-followthrough-terminal-review-observed-result",
            "sourceMapFollowthroughTerminalReviewObservedResult",
        )
        if not requested and not package:
            return None
        return cls(
            source_map_terminal_review_package=package,
            source_map_terminal_review_observed_result=observed,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_terminal_review_package_digest_sha256=str(context.get("expected_terminal_review_package_digest_sha256", context.get("expectedTerminalReviewPackageDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewClosureCheckpointResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewClosureCheckpointManager:
    """Checkpoint an observed terminal-review result into closure audit evidence without executing follow-ups."""

    def review(self, spec: SourceMapTerminalReviewClosureCheckpointSpec | None) -> SourceMapTerminalReviewClosureCheckpointResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewClosureCheckpointResult(status="unsupported", reason="missing_source_map_terminal_review_closure_checkpoint_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewClosureCheckpointResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_closure_checkpoint_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewClosureCheckpointResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_closure_checkpoint_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewClosureCheckpointSpec) -> dict[str, Any]:
        package = spec.source_map_terminal_review_package
        observed = spec.source_map_terminal_review_observed_result
        review_payload = package.get("terminal_review_package") if isinstance(package.get("terminal_review_package"), dict) else {}
        package_digest = self._stable_json_digest(package) if package else ""
        observed_digest = self._stable_json_digest(observed) if observed else ""
        consumer = self._normalize_consumer(str(package.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(package.get("selected_action_id") or "")
        blockers = self._blockers(spec, package, observed, consumer, action_id, package_digest)
        status = "blocked" if blockers else "ready_for_review"
        closure_status = self._closure_status(package, observed, bool(blockers))
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "status": status,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(package.get("selected_review_gate") or ""),
            "application_surface": str(package.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(observed.get("reviewer") or package.get("reviewer") or ""),
            "source_terminal_review_package_schema_version": str(package.get("schema_version") or "") if package else "",
            "source_terminal_review_package_status": self._status(package),
            "source_terminal_review_package_digest_sha256": package_digest,
            "expected_terminal_review_package_digest_sha256": spec.expected_terminal_review_package_digest_sha256,
            "source_observed_result_schema_version": str(observed.get("schema_version") or "") if observed else "",
            "source_observed_result_status": self._observed_status(observed),
            "source_observed_result_digest_sha256": observed_digest,
            "terminal_review_package_verified": bool(package) and not blockers,
            "observed_result_attached": bool(observed),
            "observed_review_completed": not blockers,
            "terminal_review_candidate": bool(package.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(package.get("followup_required")) and not blockers,
            "completion_status": str(package.get("completion_status") or ("blocked" if blockers else "review_required")),
            "closure_status": closure_status,
            "recommended_review_action": str(review_payload.get("recommended_review_action") or package.get("next_action") or ""),
            "observed_review_action": self._observed_action(observed, review_payload),
            "required_artifacts": review_payload.get("required_artifacts") if isinstance(review_payload.get("required_artifacts"), list) else [],
            "closure_audit": self._closure_audit(package, observed, review_payload, package_digest, observed_digest, closure_status, bool(blockers)),
            "ready_for_closure_audit_review": not blockers,
            "ready_for_terminal_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed_by_checkpoint": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_checkpoint": False,
            "source_logpoint_install_invoked_by_checkpoint": False,
            "rebuild_invoked_by_checkpoint": False,
            "delivery_invoked_by_checkpoint": False,
            "browser_started_by_checkpoint": False,
            "cdp_command_sent_by_checkpoint": False,
            "runtime_evaluated_by_checkpoint": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(package),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "status": status,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "reason": reason,
            "selected_consumer": "",
            "closure_status": status,
            "ready_for_closure_audit_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_terminal_review_package",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewClosureCheckpointSpec,
        package: dict[str, Any],
        observed: dict[str, Any],
        consumer: str,
        action_id: str,
        package_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not package:
            return ["source_map_terminal_review_package_missing"]
        if package.get("schema_version") != "reverse-deepagent.source-map-terminal-review-package.v1":
            blockers.append("source_map_terminal_review_package_schema_mismatch")
        if cls._status(package) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_terminal_review_package_not_ready")
        if package.get("ready_for_terminal_review") is not True or package.get("ready_for_audit_handoff_review") is not True:
            blockers.append("source_map_terminal_review_package_not_verified")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_terminal_review_package_digest_sha256 and spec.expected_terminal_review_package_digest_sha256 != package_digest:
            blockers.append("source_map_terminal_review_package_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "recommended_action_executed", "debugger_continuation_invoked", "hook_install_invoked_by_package", "source_logpoint_install_invoked_by_package", "rebuild_invoked_by_package", "delivery_invoked_by_package", "browser_started_by_package", "cdp_command_sent_by_package", "runtime_evaluated_by_package"):
            if package.get(key) is True:
                blockers.append(f"source_map_terminal_review_package_{key}_forbidden")
        if not observed:
            blockers.append("source_map_terminal_review_observed_result_missing")
        else:
            if cls._observed_status(observed) in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("source_map_terminal_review_observed_result_failed")
            if not cls._observed_completed(observed):
                blockers.append("source_map_terminal_review_observed_result_not_completed")
            for key in ("calls_mcp", "mobile_runtime_used", "checkpoint_executed", "browser_started_by_checkpoint", "cdp_command_sent_by_checkpoint", "runtime_evaluated_by_checkpoint", "recommended_action_executed_by_checkpoint"):
                if observed.get(key) is True:
                    blockers.append(f"source_map_terminal_review_observed_result_{key}_forbidden")
        return blockers

    @classmethod
    def _closure_audit(
        cls,
        package: dict[str, Any],
        observed: dict[str, Any],
        review_payload: dict[str, Any],
        package_digest: str,
        observed_digest: str,
        closure_status: str,
        blocked: bool,
    ) -> dict[str, Any]:
        if not package:
            return {}
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-audit.v1",
            "audit_kind": "source-map-terminal-review-closure",
            "selected_consumer": str(package.get("selected_consumer") or ""),
            "selected_action_id": str(package.get("selected_action_id") or ""),
            "application_surface": str(package.get("application_surface") or ""),
            "package_kind": str(review_payload.get("package_kind") or ""),
            "closure_status": closure_status,
            "terminal_review_candidate": bool(package.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(package.get("followup_required")) and not blocked,
            "recommended_review_action": str(review_payload.get("recommended_review_action") or package.get("next_action") or ""),
            "observed_review_action": cls._observed_action(observed, review_payload),
            "observed_result_status": cls._observed_status(observed),
            "terminal_review_package_digest_sha256": package_digest,
            "observed_result_digest_sha256": observed_digest,
            "manual_review_observed": bool(observed) and not blocked,
            "closure_review_required": True,
            "execute_recommended_action": False,
            "required_artifacts": review_payload.get("required_artifacts") if isinstance(review_payload.get("required_artifacts"), list) else [],
            "review_notes_digest_sha256": cls._review_notes_digest(observed),
        }

    @staticmethod
    def _closure_status(package: dict[str, Any], observed: dict[str, Any], blocked: bool) -> str:
        if blocked:
            if not observed:
                return "observed_result_required"
            return "blocked"
        if package.get("followup_required") is True:
            return "followup_review_observed"
        return "terminal_review_observed"

    @staticmethod
    def _observed_status(observed: dict[str, Any]) -> str:
        return str(observed.get("status") or observed.get("review_status") or observed.get("result_status") or "").strip().lower()

    @classmethod
    def _observed_completed(cls, observed: dict[str, Any]) -> bool:
        if observed.get("review_completed") is True or observed.get("manual_review_completed") is True or observed.get("closure_ready") is True:
            return True
        return cls._observed_status(observed) in {"reviewed", "accepted", "approved", "completed", "success", "closed", "ready_for_review", "followup_recorded", "terminal_review_observed"}

    @staticmethod
    def _observed_action(observed: dict[str, Any], review_payload: dict[str, Any]) -> str:
        return str(observed.get("observed_review_action") or observed.get("review_action") or observed.get("action") or review_payload.get("recommended_review_action") or "")

    @staticmethod
    def _review_notes_digest(observed: dict[str, Any]) -> str:
        notes = observed.get("review_notes", observed.get("notes", ""))
        if not notes:
            return ""
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest({"review_notes": str(notes)})

    @staticmethod
    def _warnings(package: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_closure_checkpoint_does_not_execute_recommended_action"]
        if package:
            warnings.append("source_map_terminal_review_closure_checkpoint_requires_manual_review")
        if package.get("followup_required") is True:
            warnings.append("source_map_terminal_review_closure_checkpoint_followup_observed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_terminal_review_package_missing" for item in blockers):
            return "provide_source_map_terminal_review_package"
        if any(item == "source_map_terminal_review_observed_result_missing" for item in blockers):
            return "record_source_map_terminal_review_observed_result"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_closure_checkpoint_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_closure_checkpoint_failure"
        return "review_source_map_terminal_review_closure_checkpoint"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_checkpoint_only": True,
            "closure_checkpoint_only": True,
            "observed_result_checkpoint_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed_by_checkpoint": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewFinalAuditSpec:
    """Read-only final audit rollup after a Source Map terminal review closure checkpoint."""

    source_map_terminal_review_closure_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_package: dict[str, Any] = field(default_factory=dict)
    expected_consumer: str = ""
    expected_action_id: str = ""
    expected_closure_checkpoint_digest_sha256: str = ""
    reviewer: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewFinalAuditSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_final_audit",
                "sourceMapTerminalReviewFinalAudit",
                "source_map_terminal_review_final_audit_rollup",
                "sourceMapTerminalReviewFinalAuditRollup",
                "source_map_followthrough_final_audit",
                "sourceMapFollowthroughFinalAudit",
                "source_map_terminal_review_closure_summary",
                "sourceMapTerminalReviewClosureSummary",
            )
        )
        closure = cls._object_alias(
            context,
            "source_map_terminal_review_closure_checkpoint",
            "source-map-terminal-review-closure-checkpoint",
            "sourceMapTerminalReviewClosureCheckpoint",
            "source_map_terminal_review_observed_result_checkpoint",
            "source-map-terminal-review-observed-result-checkpoint",
            "sourceMapTerminalReviewObservedResultCheckpoint",
            "source_map_followthrough_closure_audit",
            "source-map-followthrough-closure-audit",
            "sourceMapFollowthroughClosureAudit",
            "source_map_terminal_review_closure_audit",
            "source-map-terminal-review-closure-audit",
            "sourceMapTerminalReviewClosureAudit",
        )
        package = cls._object_alias(
            context,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
        )
        if not requested and not closure:
            return None
        return cls(
            source_map_terminal_review_closure_checkpoint=closure,
            source_map_terminal_review_package=package,
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
            expected_closure_checkpoint_digest_sha256=str(context.get("expected_closure_checkpoint_digest_sha256", context.get("expectedClosureCheckpointDigestSha256", "")) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewFinalAuditResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewFinalAuditManager:
    """Summarize a closure checkpoint into final Source Map follow-through audit evidence without execution."""

    def review(self, spec: SourceMapTerminalReviewFinalAuditSpec | None) -> SourceMapTerminalReviewFinalAuditResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewFinalAuditResult(status="unsupported", reason="missing_source_map_terminal_review_final_audit_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewFinalAuditResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_final_audit_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewFinalAuditResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=policy,
                reason="source_map_terminal_review_final_audit_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewFinalAuditSpec) -> dict[str, Any]:
        closure = spec.source_map_terminal_review_closure_checkpoint
        package = spec.source_map_terminal_review_package
        closure_audit = closure.get("closure_audit") if isinstance(closure.get("closure_audit"), dict) else {}
        closure_digest = self._stable_json_digest(closure) if closure else ""
        package_digest = self._stable_json_digest(package) if package else ""
        consumer = self._normalize_consumer(str(closure.get("selected_consumer") or spec.expected_consumer or ""))
        action_id = str(closure.get("selected_action_id") or "")
        blockers = self._blockers(spec, closure, package, consumer, action_id, closure_digest)
        status = "blocked" if blockers else "ready_for_review"
        final_status = "blocked" if blockers else "source_map_followthrough_review_closed"
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
            "status": status,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "selected_action_id": action_id,
            "selected_consumer": consumer,
            "selected_review_gate": str(closure.get("selected_review_gate") or ""),
            "application_surface": str(closure.get("application_surface") or ""),
            "expected_action_id": spec.expected_action_id,
            "expected_consumer": spec.expected_consumer,
            "reviewer": spec.reviewer or str(closure.get("reviewer") or ""),
            "source_closure_checkpoint_schema_version": str(closure.get("schema_version") or "") if closure else "",
            "source_closure_checkpoint_status": self._status(closure),
            "source_closure_checkpoint_digest_sha256": closure_digest,
            "expected_closure_checkpoint_digest_sha256": spec.expected_closure_checkpoint_digest_sha256,
            "source_terminal_review_package_digest_sha256": str(closure.get("source_terminal_review_package_digest_sha256") or package_digest),
            "terminal_review_package_attached": bool(package),
            "closure_checkpoint_verified": bool(closure) and not blockers,
            "closure_status": str(closure.get("closure_status") or ""),
            "final_audit_status": final_status,
            "terminal_review_candidate": bool(closure.get("terminal_review_candidate")) and not blockers,
            "followup_required": bool(closure.get("followup_required")) and not blockers,
            "observed_review_action": str(closure.get("observed_review_action") or closure_audit.get("observed_review_action") or ""),
            "recommended_review_action": str(closure.get("recommended_review_action") or closure_audit.get("recommended_review_action") or ""),
            "required_artifacts": closure.get("required_artifacts") if isinstance(closure.get("required_artifacts"), list) else closure_audit.get("required_artifacts", []),
            "final_audit_rollup": self._rollup(closure, closure_audit, closure_digest, package_digest, final_status, bool(blockers)),
            "ready_for_final_audit_review": not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "recommended_action_executed_by_rollup": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked_by_rollup": False,
            "source_logpoint_install_invoked_by_rollup": False,
            "rebuild_invoked_by_rollup": False,
            "delivery_invoked_by_rollup": False,
            "browser_started_by_rollup": False,
            "cdp_command_sent_by_rollup": False,
            "runtime_evaluated_by_rollup": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(closure),
            "next_action": self._next_action(blockers),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
            "status": status,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "reason": reason,
            "selected_consumer": "",
            "final_audit_status": status,
            "ready_for_final_audit_review": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_terminal_review_closure_checkpoint",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewFinalAuditSpec,
        closure: dict[str, Any],
        package: dict[str, Any],
        consumer: str,
        action_id: str,
        closure_digest: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not closure:
            return ["source_map_terminal_review_closure_checkpoint_missing"]
        if closure.get("schema_version") != "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1":
            blockers.append("source_map_terminal_review_closure_checkpoint_schema_mismatch")
        if cls._status(closure) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_terminal_review_closure_checkpoint_not_ready")
        if closure.get("ready_for_closure_audit_review") is not True or closure.get("observed_review_completed") is not True:
            blockers.append("source_map_terminal_review_closure_checkpoint_not_verified")
        if spec.expected_consumer and consumer and cls._normalize_consumer(spec.expected_consumer) != consumer:
            blockers.append("selected_consumer_mismatch")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        if spec.expected_closure_checkpoint_digest_sha256 and spec.expected_closure_checkpoint_digest_sha256 != closure_digest:
            blockers.append("source_map_terminal_review_closure_checkpoint_digest_mismatch")
        for key in ("calls_mcp", "mobile_runtime_used", "execute_next_automatically", "ready_to_execute_now", "recommended_action_executed_by_checkpoint", "debugger_continuation_invoked", "hook_install_invoked_by_checkpoint", "source_logpoint_install_invoked_by_checkpoint", "rebuild_invoked_by_checkpoint", "delivery_invoked_by_checkpoint", "browser_started_by_checkpoint", "cdp_command_sent_by_checkpoint", "runtime_evaluated_by_checkpoint"):
            if closure.get(key) is True:
                blockers.append(f"source_map_terminal_review_closure_checkpoint_{key}_forbidden")
        if package and package.get("schema_version") != "reverse-deepagent.source-map-terminal-review-package.v1":
            blockers.append("source_map_terminal_review_package_schema_mismatch")
        return blockers

    @classmethod
    def _rollup(cls, closure: dict[str, Any], closure_audit: dict[str, Any], closure_digest: str, package_digest: str, final_status: str, blocked: bool) -> dict[str, Any]:
        if not closure:
            return {}
        required_artifacts = closure.get("required_artifacts") if isinstance(closure.get("required_artifacts"), list) else closure_audit.get("required_artifacts", [])
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit-rollup.v1",
            "rollup_kind": "source-map-terminal-review-final-audit",
            "selected_consumer": str(closure.get("selected_consumer") or ""),
            "selected_action_id": str(closure.get("selected_action_id") or ""),
            "application_surface": str(closure.get("application_surface") or ""),
            "closure_status": str(closure.get("closure_status") or ""),
            "final_audit_status": final_status,
            "terminal_review_candidate": bool(closure.get("terminal_review_candidate")) and not blocked,
            "followup_required": bool(closure.get("followup_required")) and not blocked,
            "recommended_review_action": str(closure.get("recommended_review_action") or closure_audit.get("recommended_review_action") or ""),
            "observed_review_action": str(closure.get("observed_review_action") or closure_audit.get("observed_review_action") or ""),
            "required_artifacts": required_artifacts,
            "required_artifact_count": len(required_artifacts) if isinstance(required_artifacts, list) else 0,
            "closure_checkpoint_digest_sha256": closure_digest,
            "terminal_review_package_digest_sha256": str(closure.get("source_terminal_review_package_digest_sha256") or package_digest),
            "observed_result_digest_sha256": str(closure.get("source_observed_result_digest_sha256") or closure_audit.get("observed_result_digest_sha256") or ""),
            "manual_review_observed": bool(closure.get("observed_review_completed") or closure_audit.get("manual_review_observed")) and not blocked,
            "execute_recommended_action": False,
            "final_review_required": True,
        }

    @staticmethod
    def _warnings(closure: dict[str, Any]) -> list[str]:
        warnings = ["source_map_terminal_review_final_audit_does_not_execute_recommended_action"]
        if closure:
            warnings.append("source_map_terminal_review_final_audit_requires_manual_review")
        if closure.get("followup_required") is True:
            warnings.append("source_map_terminal_review_final_audit_followup_observed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(item == "source_map_terminal_review_closure_checkpoint_missing" for item in blockers):
            return "provide_source_map_terminal_review_closure_checkpoint"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_final_audit_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_final_audit_failure"
        return "review_source_map_terminal_review_final_audit"

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "audit_rollup_only": True,
            "final_audit_only": True,
            "closure_summary_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "recommended_action_executed_by_rollup": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class SourceMapTerminalReviewActionDecisionSpec:
    """Explicit-review-only terminal review action decision / result recorder.

    This descriptor records a reviewer decision about the recommended terminal
    review action.  It never executes that recommendation and never invokes
    debugger, hook, logpoint, rebuild, source-map fetch, browser, CDP, MCP, or
    raw-source export behavior.
    """

    source_map_terminal_review_package: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_closure_checkpoint: dict[str, Any] = field(default_factory=dict)
    source_map_terminal_review_final_audit: dict[str, Any] = field(default_factory=dict)
    selected_action: str = ""
    reviewer: str = ""
    reason: str = ""
    expected_source_descriptor_digest_sha256: str = ""
    expected_consumer: str = ""
    expected_action_id: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapTerminalReviewActionDecisionSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_terminal_review_action_decision",
                "sourceMapTerminalReviewActionDecision",
                "source_map_terminal_review_action_result",
                "sourceMapTerminalReviewActionResult",
                "record_source_map_terminal_review_action",
                "recordSourceMapTerminalReviewAction",
            )
        )
        package = cls._object_alias(
            context,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
            "source_map_terminal_review_handoff",
            "source-map-terminal-review-handoff",
            "sourceMapTerminalReviewHandoff",
        )
        closure = cls._object_alias(
            context,
            "source_map_terminal_review_closure_checkpoint",
            "source-map-terminal-review-closure-checkpoint",
            "sourceMapTerminalReviewClosureCheckpoint",
            "source_map_terminal_review_observed_result_checkpoint",
            "source-map-terminal-review-observed-result-checkpoint",
            "sourceMapTerminalReviewObservedResultCheckpoint",
            "source_map_terminal_review_closure_audit",
            "source-map-terminal-review-closure-audit",
            "sourceMapTerminalReviewClosureAudit",
        )
        final_audit = cls._object_alias(
            context,
            "source_map_terminal_review_final_audit",
            "source-map-terminal-review-final-audit",
            "sourceMapTerminalReviewFinalAudit",
            "source_map_terminal_review_final_audit_rollup",
            "source-map-terminal-review-final-audit-rollup",
            "sourceMapTerminalReviewFinalAuditRollup",
            "source_map_followthrough_final_audit",
            "source-map-followthrough-final-audit",
            "sourceMapFollowthroughFinalAudit",
        )
        if not requested and not any((package, closure, final_audit)):
            return None
        return cls(
            source_map_terminal_review_package=package,
            source_map_terminal_review_closure_checkpoint=closure,
            source_map_terminal_review_final_audit=final_audit,
            selected_action=str(context.get("selected_action", context.get("selectedAction", context.get("terminal_review_action", context.get("terminalReviewAction", "")))) or ""),
            reviewer=str(context.get("reviewer", context.get("reviewer_id", context.get("reviewerId", ""))) or ""),
            reason=str(context.get("reason", context.get("review_reason", context.get("reviewReason", context.get("decision_reason", context.get("decisionReason", ""))))) or ""),
            expected_source_descriptor_digest_sha256=str(context.get("expected_source_descriptor_digest_sha256", context.get("expectedSourceDescriptorDigestSha256", "")) or ""),
            expected_consumer=str(context.get("expected_consumer", context.get("expectedConsumer", context.get("source_map_selected_consumer", context.get("sourceMapSelectedConsumer", "")))) or ""),
            expected_action_id=str(context.get("expected_action_id", context.get("expectedActionId", context.get("source_map_selected_action_id", context.get("sourceMapSelectedActionId", "")))) or ""),
        )

    _object_alias = staticmethod(SourceMapTypedPayloadPreflightSpec._object_alias)


@dataclass(slots=True)
class SourceMapTerminalReviewActionDecisionResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class SourceMapTerminalReviewActionDecisionManager:
    """Record a reviewer terminal-review action decision without executing the action."""

    _ALLOWED_ACTIONS = frozenset({"defer", "approve_followup", "reject", "request_manual_execution", "mark_complete"})

    def record(self, spec: SourceMapTerminalReviewActionDecisionSpec | None) -> SourceMapTerminalReviewActionDecisionResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapTerminalReviewActionDecisionResult(status="unsupported", reason="missing_source_map_terminal_review_action_decision_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapTerminalReviewActionDecisionResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=descriptor.get("side_effect_policy", policy))
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_terminal_review_action_decision_failed")
            descriptor["error"] = str(exc)
            return SourceMapTerminalReviewActionDecisionResult(
                status="failed",
                descriptor=descriptor,
                side_effect_policy=descriptor.get("side_effect_policy", policy),
                reason="source_map_terminal_review_action_decision_failed",
                error=str(exc),
            )

    def _descriptor(self, spec: SourceMapTerminalReviewActionDecisionSpec) -> dict[str, Any]:
        source_kind, source = self._select_source(spec)
        source_digest = self._stable_json_digest(source) if source else ""
        source_summary = self._source_summary(source_kind, source)
        selected_action = self._normalize_action(spec.selected_action)
        blockers = self._blockers(spec, source_kind, source, source_digest, selected_action)
        status = "blocked" if blockers else "recorded"
        decision_id = self._decision_id(source_kind, source_digest, selected_action)
        decision_record = self._decision_record(
            decision_id=decision_id,
            source_kind=source_kind,
            source_digest=source_digest,
            source_summary=source_summary,
            selected_action=selected_action,
            reviewer=spec.reviewer,
            reason=spec.reason,
            recorded=not blockers,
        )
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-action-decision.v1",
            "status": status,
            "explicit_review_only": True,
            "decision_record_only": True,
            "result_recorder_only": True,
            "terminal_review_action_decision_only": True,
            "review_only": True,
            "audit_only": True,
            "decision_id": decision_id,
            "idempotency_key": self._idempotency_key(decision_record),
            "decision_digest_sha256": self._stable_json_digest(decision_record),
            "selected_action": selected_action,
            "allowed_actions": sorted(self._ALLOWED_ACTIONS),
            "reviewer": spec.reviewer,
            "reason": spec.reason,
            "source_descriptor_kind": source_kind,
            "source_descriptor_schema_version": str(source.get("schema_version") or "") if source else "",
            "source_descriptor_status": self._status(source),
            "source_descriptor_digest_sha256": source_digest,
            "expected_source_descriptor_digest_sha256": spec.expected_source_descriptor_digest_sha256,
            "source_descriptor_summary": source_summary,
            "selected_consumer": source_summary.get("selected_consumer", ""),
            "selected_action_id": source_summary.get("selected_action_id", ""),
            "recommended_review_action": source_summary.get("recommended_review_action", ""),
            "expected_consumer": spec.expected_consumer,
            "expected_action_id": spec.expected_action_id,
            "terminal_review_action_recorded": not blockers,
            "recommended_action_approved_for_separate_followup": selected_action in {"approve_followup", "request_manual_execution"} and not blockers,
            "terminal_review_marked_complete": selected_action == "mark_complete" and not blockers,
            "terminal_review_rejected": selected_action == "reject" and not blockers,
            "terminal_review_deferred": selected_action == "defer" and not blockers,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "automatic_followthrough_supported": False,
            "executes_recommended_action": False,
            "installs_hook": False,
            "installs_logpoint": False,
            "continues_debugger": False,
            "generates_rebuild": False,
            "fetches_source_map": False,
            "exports_raw_source": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "source_map_fetch_invoked": False,
            "raw_source_exported": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "decision_record": decision_record,
            "blockers": list(dict.fromkeys(blockers)),
            "warnings": self._warnings(selected_action, bool(blockers)),
            "next_action": self._next_action(blockers, selected_action),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-action-decision.v1",
            "status": status,
            "explicit_review_only": True,
            "decision_record_only": True,
            "result_recorder_only": True,
            "terminal_review_action_decision_only": True,
            "review_only": True,
            "audit_only": True,
            "reason": reason,
            "decision_id": "",
            "idempotency_key": "",
            "decision_digest_sha256": "",
            "selected_action": "",
            "reviewer": "",
            "source_descriptor_kind": "",
            "source_descriptor_digest_sha256": "",
            "terminal_review_action_recorded": False,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "executes_recommended_action": False,
            "installs_hook": False,
            "installs_logpoint": False,
            "continues_debugger": False,
            "generates_rebuild": False,
            "fetches_source_map": False,
            "exports_raw_source": False,
            "decision_record": {},
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_ready_source_map_terminal_review_artifact",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _select_source(cls, spec: SourceMapTerminalReviewActionDecisionSpec) -> tuple[str, dict[str, Any]]:
        if spec.source_map_terminal_review_final_audit:
            return "source-map-terminal-review-final-audit", spec.source_map_terminal_review_final_audit
        if spec.source_map_terminal_review_closure_checkpoint:
            return "source-map-terminal-review-closure-checkpoint", spec.source_map_terminal_review_closure_checkpoint
        if spec.source_map_terminal_review_package:
            return "source-map-terminal-review-package", spec.source_map_terminal_review_package
        return "", {}

    @classmethod
    def _blockers(
        cls,
        spec: SourceMapTerminalReviewActionDecisionSpec,
        source_kind: str,
        source: dict[str, Any],
        source_digest: str,
        selected_action: str,
    ) -> list[str]:
        blockers: list[str] = []
        if not source:
            return ["source_map_terminal_review_ready_source_missing"]
        expected_schema = {
            "source-map-terminal-review-package": "reverse-deepagent.source-map-terminal-review-package.v1",
            "source-map-terminal-review-closure-checkpoint": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "source-map-terminal-review-final-audit": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
        }.get(source_kind, "")
        ready_flag = {
            "source-map-terminal-review-package": "ready_for_terminal_review",
            "source-map-terminal-review-closure-checkpoint": "ready_for_closure_audit_review",
            "source-map-terminal-review-final-audit": "ready_for_final_audit_review",
        }.get(source_kind, "")
        if source.get("schema_version") != expected_schema:
            blockers.append("source_map_terminal_review_source_schema_mismatch")
        if cls._status(source) not in {"ready_for_review", "ready"}:
            blockers.append("source_map_terminal_review_source_not_ready")
        if ready_flag and source.get(ready_flag) is not True:
            blockers.append("source_map_terminal_review_source_ready_flag_missing")
        if selected_action not in cls._ALLOWED_ACTIONS:
            blockers.append("source_map_terminal_review_action_invalid")
        if not spec.reviewer.strip():
            blockers.append("source_map_terminal_review_action_reviewer_missing")
        if not spec.reason.strip():
            blockers.append("source_map_terminal_review_action_reason_missing")
        if spec.expected_source_descriptor_digest_sha256 and spec.expected_source_descriptor_digest_sha256 != source_digest:
            blockers.append("source_map_terminal_review_source_digest_mismatch")
        consumer = cls._normalize_consumer(str(source.get("selected_consumer") or ""))
        if spec.expected_consumer and consumer and consumer != cls._normalize_consumer(spec.expected_consumer):
            blockers.append("selected_consumer_mismatch")
        action_id = str(source.get("selected_action_id") or "")
        if spec.expected_action_id and action_id and spec.expected_action_id != action_id:
            blockers.append("selected_action_id_mismatch")
        for key in (
            "calls_mcp",
            "mobile_runtime_used",
            "execute_next_automatically",
            "ready_to_execute_now",
            "recommended_action_executed",
            "recommended_action_executed_by_checkpoint",
            "recommended_action_executed_by_rollup",
            "debugger_continuation_invoked",
            "hook_install_invoked",
            "hook_install_invoked_by_package",
            "hook_install_invoked_by_checkpoint",
            "hook_install_invoked_by_rollup",
            "source_logpoint_install_invoked",
            "source_logpoint_install_invoked_by_package",
            "source_logpoint_install_invoked_by_checkpoint",
            "source_logpoint_install_invoked_by_rollup",
            "rebuild_invoked",
            "rebuild_invoked_by_package",
            "rebuild_invoked_by_checkpoint",
            "rebuild_invoked_by_rollup",
            "browser_started",
            "browser_started_by_package",
            "browser_started_by_checkpoint",
            "browser_started_by_rollup",
            "cdp_command_sent",
            "cdp_command_sent_by_package",
            "cdp_command_sent_by_checkpoint",
            "cdp_command_sent_by_rollup",
            "runtime_evaluated",
            "runtime_evaluated_by_package",
            "runtime_evaluated_by_checkpoint",
            "runtime_evaluated_by_rollup",
        ):
            if source.get(key) is True:
                blockers.append(f"source_map_terminal_review_source_{key}_forbidden")
        for key in (
            "raw_source_exported",
            "exports_raw_source",
            "raw_source_content_exported",
            "raw_source_content_included",
            "preview_exported",
        ):
            if source.get(key) is True:
                blockers.append("source_map_terminal_review_source_raw_source_material_forbidden")
        for key in ("raw_source", "raw_source_content", "sourcesContent"):
            if source.get(key):
                blockers.append("source_map_terminal_review_source_raw_source_material_forbidden")
        policy = source.get("side_effect_policy") if isinstance(source.get("side_effect_policy"), dict) else {}
        for key in ("calls_mcp", "mobile_runtime_used", "browser_started", "cdp_command_sent", "runtime_evaluated"):
            if policy.get(key) is True:
                blockers.append(f"source_map_terminal_review_source_policy_{key}_forbidden")
        for key in ("exports_raw_source", "raw_source_exported", "raw_source_content_exported", "preview_exported"):
            if policy.get(key) is True:
                blockers.append("source_map_terminal_review_source_raw_source_material_forbidden")
        return blockers

    @classmethod
    def _source_summary(cls, source_kind: str, source: dict[str, Any]) -> dict[str, Any]:
        if not source:
            return {}
        nested = {}
        if source_kind == "source-map-terminal-review-package" and isinstance(source.get("terminal_review_package"), dict):
            nested = source.get("terminal_review_package") or {}
        elif source_kind == "source-map-terminal-review-closure-checkpoint" and isinstance(source.get("closure_audit"), dict):
            nested = source.get("closure_audit") or {}
        elif source_kind == "source-map-terminal-review-final-audit" and isinstance(source.get("final_audit_rollup"), dict):
            nested = source.get("final_audit_rollup") or {}
        required = source.get("required_artifacts") if isinstance(source.get("required_artifacts"), list) else nested.get("required_artifacts", [])
        return {
            "source_descriptor_kind": source_kind,
            "schema_version": str(source.get("schema_version") or ""),
            "status": cls._status(source),
            "selected_consumer": cls._normalize_consumer(str(source.get("selected_consumer") or nested.get("selected_consumer") or "")),
            "selected_action_id": str(source.get("selected_action_id") or nested.get("selected_action_id") or ""),
            "application_surface": str(source.get("application_surface") or nested.get("application_surface") or ""),
            "completion_status": str(source.get("completion_status") or ""),
            "closure_status": str(source.get("closure_status") or nested.get("closure_status") or ""),
            "final_audit_status": str(source.get("final_audit_status") or nested.get("final_audit_status") or ""),
            "recommended_review_action": str(source.get("recommended_review_action") or nested.get("recommended_review_action") or ""),
            "observed_review_action": str(source.get("observed_review_action") or nested.get("observed_review_action") or ""),
            "terminal_review_candidate": bool(source.get("terminal_review_candidate") or nested.get("terminal_review_candidate")),
            "followup_required": bool(source.get("followup_required") or nested.get("followup_required")),
            "required_artifacts": [str(item) for item in required] if isinstance(required, list) else [],
        }

    @classmethod
    def _decision_record(
        cls,
        *,
        decision_id: str,
        source_kind: str,
        source_digest: str,
        source_summary: dict[str, Any],
        selected_action: str,
        reviewer: str,
        reason: str,
        recorded: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-terminal-review-action-result.v1",
            "decision_id": decision_id,
            "recorded": recorded,
            "selected_action": selected_action,
            "reviewer": reviewer,
            "reason": reason,
            "source_descriptor_kind": source_kind,
            "source_descriptor_digest_sha256": source_digest,
            "selected_consumer": source_summary.get("selected_consumer", ""),
            "selected_action_id": source_summary.get("selected_action_id", ""),
            "recommended_review_action": source_summary.get("recommended_review_action", ""),
            "executes_recommended_action": False,
            "installs_hook": False,
            "installs_logpoint": False,
            "continues_debugger": False,
            "generates_rebuild": False,
            "fetches_source_map": False,
            "exports_raw_source": False,
        }

    @classmethod
    def _decision_id(cls, source_kind: str, source_digest: str, selected_action: str) -> str:
        if not source_digest or not selected_action:
            return ""
        return f"source-map-terminal-review-action-decision:{source_kind}:{selected_action}:{source_digest[:16]}"

    @classmethod
    def _idempotency_key(cls, decision_record: dict[str, Any]) -> str:
        if not decision_record.get("decision_id"):
            return ""
        return cls._stable_json_digest(
            {
                "decision_id": decision_record.get("decision_id", ""),
                "selected_action": decision_record.get("selected_action", ""),
                "reviewer": decision_record.get("reviewer", ""),
                "reason": decision_record.get("reason", ""),
                "source_descriptor_digest_sha256": decision_record.get("source_descriptor_digest_sha256", ""),
            }
        )

    @classmethod
    def _warnings(cls, selected_action: str, blocked: bool) -> list[str]:
        warnings = ["source_map_terminal_review_action_decision_does_not_execute_recommended_action"]
        if blocked:
            warnings.append("source_map_terminal_review_action_decision_blocked")
        elif selected_action in {"approve_followup", "request_manual_execution"}:
            warnings.append("source_map_terminal_review_action_requires_separate_manual_followup")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], selected_action: str) -> str:
        if any(item == "source_map_terminal_review_ready_source_missing" for item in blockers):
            return "provide_ready_source_map_terminal_review_artifact"
        if any(item == "source_map_terminal_review_action_invalid" for item in blockers):
            return "choose_valid_source_map_terminal_review_action"
        if any(item.endswith("mismatch") for item in blockers):
            return "refresh_matching_source_map_terminal_review_action_decision_inputs"
        if blockers:
            return "inspect_source_map_terminal_review_action_decision_failure"
        if selected_action in {"approve_followup", "request_manual_execution"}:
            return "perform_separate_explicit_manual_followup_if_approved"
        return "review_source_map_terminal_review_action_decision"

    @staticmethod
    def _normalize_action(value: str) -> str:
        return str(value or "").strip().lower().replace("-", "_")

    @staticmethod
    def _normalize_consumer(value: str) -> str:
        return SourceMapFollowthroughCompletionCheckpointManager._normalize_consumer(value)

    @staticmethod
    def _stable_json_digest(payload: dict[str, Any]) -> str:
        return SourceMapSelectedExecutorApplyPreflightManager._stable_json_digest(payload)

    _status = staticmethod(SourceMapSelectedExecutorApplyPreflightManager._status)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "explicit_review_only": True,
            "decision_record_only": True,
            "result_recorder_only": True,
            "terminal_review_action_decision_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "selected_executor_application_invoked": False,
            "executes_recommended_action": False,
            "installs_hook": False,
            "installs_logpoint": False,
            "continues_debugger": False,
            "generates_rebuild": False,
            "fetches_source_map": False,
            "exports_raw_source": False,
            "recommended_action_executed": False,
            "debugger_continuation_invoked": False,
            "hook_install_invoked": False,
            "source_logpoint_install_invoked": False,
            "rebuild_invoked": False,
            "source_map_fetch_invoked": False,
            "raw_source_exported": False,
            "delivery_invoked": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

__all__ = [
    "SourceMapTerminalReviewPackageSpec",
    "SourceMapTerminalReviewPackageResult",
    "SourceMapTerminalReviewPackageManager",
    "SourceMapTerminalReviewClosureCheckpointSpec",
    "SourceMapTerminalReviewClosureCheckpointResult",
    "SourceMapTerminalReviewClosureCheckpointManager",
    "SourceMapTerminalReviewFinalAuditSpec",
    "SourceMapTerminalReviewFinalAuditResult",
    "SourceMapTerminalReviewFinalAuditManager",
    "SourceMapTerminalReviewActionDecisionSpec",
    "SourceMapTerminalReviewActionDecisionResult",
    "SourceMapTerminalReviewActionDecisionManager",
]

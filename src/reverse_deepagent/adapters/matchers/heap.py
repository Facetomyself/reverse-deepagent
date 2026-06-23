from __future__ import annotations

from typing import Any


def _is_heap_snapshot_automatic_followup_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        proof_plan_names = {
            "heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-retained-size-proof-planner",
            "plan-heap-snapshot-retained-size-proof",
            "review-heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }
        proof_plan_keys = (
            "heap_snapshot_retained_size_proof_plan",
            "heapSnapshotRetainedSizeProofPlan",
            "heap_snapshot_retained_size_proof_planner",
            "heapSnapshotRetainedSizeProofPlanner",
            "plan_heap_snapshot_retained_size_proof",
            "planHeapSnapshotRetainedSizeProof",
            "review_heap_snapshot_retained_size_proof_plan",
            "reviewHeapSnapshotRetainedSizeProofPlan",
            "heap_snapshot_path_to_root_proof_plan",
            "heapSnapshotPathToRootProofPlan",
            "heap_snapshot_path_to_root_proof_planner",
            "heapSnapshotPathToRootProofPlanner",
            "plan_heap_snapshot_path_to_root_proof",
            "planHeapSnapshotPathToRootProof",
            "review_heap_snapshot_path_to_root_proof_plan",
            "reviewHeapSnapshotPathToRootProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "heapSnapshotRawHeapConstructorDrilldownProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
            "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
            "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
            "planHeapSnapshotRawHeapConstructorDrilldownProof",
            "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
        )
        if normalized in proof_plan_names or any(key in context for key in proof_plan_keys):
            return False
        if normalized in {
            "heap-snapshot-automatic-followup-plan",
            "heap-snapshot-automatic-followup-planner",
            "heap-snapshot-followup-plan",
            "plan-heap-snapshot-automatic-followup",
            "review-heap-snapshot-automatic-followup-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_automatic_followup_plan",
                "heapSnapshotAutomaticFollowupPlan",
                "heap_snapshot_automatic_followup_planner",
                "heapSnapshotAutomaticFollowupPlanner",
                "heap_snapshot_followup_plan",
                "heapSnapshotFollowupPlan",
                "plan_heap_snapshot_automatic_followup",
                "planHeapSnapshotAutomaticFollowup",
                "review_heap_snapshot_automatic_followup_plan",
                "reviewHeapSnapshotAutomaticFollowupPlan",
            )
        )


def _is_heap_snapshot_retained_size_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        path_proof_names = {
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }
        path_proof_keys = (
            "heap_snapshot_path_to_root_proof_plan",
            "heapSnapshotPathToRootProofPlan",
            "heap_snapshot_path_to_root_proof_planner",
            "heapSnapshotPathToRootProofPlanner",
            "plan_heap_snapshot_path_to_root_proof",
            "planHeapSnapshotPathToRootProof",
            "review_heap_snapshot_path_to_root_proof_plan",
            "reviewHeapSnapshotPathToRootProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "heapSnapshotRawHeapConstructorDrilldownProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
            "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
            "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
            "planHeapSnapshotRawHeapConstructorDrilldownProof",
            "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
        )
        if normalized in path_proof_names or any(key in context for key in path_proof_keys):
            return False
        if normalized in {
            "heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-retained-size-proof-planner",
            "plan-heap-snapshot-retained-size-proof",
            "review-heap-snapshot-retained-size-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_proof_plan",
                "heapSnapshotRetainedSizeProofPlan",
                "heap_snapshot_retained_size_proof_planner",
                "heapSnapshotRetainedSizeProofPlanner",
                "plan_heap_snapshot_retained_size_proof",
                "planHeapSnapshotRetainedSizeProof",
                "review_heap_snapshot_retained_size_proof_plan",
                "reviewHeapSnapshotRetainedSizeProofPlan",
            )
        )


def _is_heap_snapshot_path_to_root_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_path_to_root_proof_plan",
                "heapSnapshotPathToRootProofPlan",
                "heap_snapshot_path_to_root_proof_planner",
                "heapSnapshotPathToRootProofPlanner",
                "plan_heap_snapshot_path_to_root_proof",
                "planHeapSnapshotPathToRootProof",
                "review_heap_snapshot_path_to_root_proof_plan",
                "reviewHeapSnapshotPathToRootProofPlan",
            )
        )


def _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "heapSnapshotRawHeapConstructorDrilldownProofPlan",
                "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
                "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
                "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
                "planHeapSnapshotRawHeapConstructorDrilldownProof",
                "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
            )
        )


def _is_heap_snapshot_path_to_root_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-path-to-root-analysis",
            "heap-snapshot-path-to-root-analysis",
            "heap-snapshot-path-to-root-executor-result",
            "heap-snapshot-path-to-root-executor-mvp",
            "path-to-root-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_path_to_root_analysis",
                "executeHeapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_analysis",
                "heapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_executor_result",
                "heapSnapshotPathToRootExecutorResult",
                "heap_snapshot_path_to_root_executor_mvp",
                "heapSnapshotPathToRootExecutorMvp",
                "path_to_root_heap_snapshot_executor",
                "pathToRootHeapSnapshotExecutor",
            )
        )


def _is_heap_snapshot_retained_size_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-retained-size-analysis",
            "heap-snapshot-retained-size-analysis",
            "heap-snapshot-retained-size-executor-result",
            "heap-snapshot-retained-size-executor-mvp",
            "retained-size-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_retained_size_analysis",
                "executeHeapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_analysis",
                "heapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_executor_result",
                "heapSnapshotRetainedSizeExecutorResult",
                "heap_snapshot_retained_size_executor_mvp",
                "heapSnapshotRetainedSizeExecutorMvp",
                "retained_size_heap_snapshot_executor",
                "retainedSizeHeapSnapshotExecutor",
            )
        )


def _is_heap_snapshot_retained_size_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_transaction_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-approval-plan",
            "heap-snapshot-retained-size-executor-approval-plan",
            "heap-snapshot-retained-size-transaction-plan",
            "review-heap-snapshot-retained-size-approval-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_approval_plan",
                "heapSnapshotRetainedSizeApprovalPlan",
                "heap_snapshot_retained_size_executor_approval_plan",
                "heapSnapshotRetainedSizeExecutorApprovalPlan",
                "heap_snapshot_retained_size_transaction_plan",
                "heapSnapshotRetainedSizeTransactionPlan",
                "review_heap_snapshot_retained_size_approval_plan",
                "reviewHeapSnapshotRetainedSizeApprovalPlan",
            )
        )


def _is_heap_snapshot_retained_size_bounded_gate_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-bounded-gate",
            "heap-snapshot-retained-size-bounded-executor-gate",
            "heap-snapshot-retained-size-executor-bounded-gate",
            "review-heap-snapshot-retained-size-bounded-gate",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_bounded_gate",
                "heapSnapshotRetainedSizeBoundedGate",
                "heap_snapshot_retained_size_bounded_executor_gate",
                "heapSnapshotRetainedSizeBoundedExecutorGate",
                "heap_snapshot_retained_size_executor_bounded_gate",
                "heapSnapshotRetainedSizeExecutorBoundedGate",
                "review_heap_snapshot_retained_size_bounded_gate",
                "reviewHeapSnapshotRetainedSizeBoundedGate",
            )
        )


def _is_heap_snapshot_retained_size_transaction_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_bounded_gate_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-transaction-preflight",
            "heap-snapshot-retained-size-executor-transaction-preflight",
            "review-heap-snapshot-retained-size-transaction-preflight",
            "preflight-heap-snapshot-retained-size-transaction",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_transaction_preflight",
                "heapSnapshotRetainedSizeTransactionPreflight",
                "heap_snapshot_retained_size_executor_transaction_preflight",
                "heapSnapshotRetainedSizeExecutorTransactionPreflight",
                "review_heap_snapshot_retained_size_transaction_preflight",
                "reviewHeapSnapshotRetainedSizeTransactionPreflight",
                "preflight_heap_snapshot_retained_size_transaction",
                "preflightHeapSnapshotRetainedSizeTransaction",
            )
        )


def _is_heap_snapshot_retained_size_input_review_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_retained_size_approval_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-input-review",
            "heap-snapshot-retained-size-executor-input-review",
            "heap-snapshot-retained-size-approval-gate",
            "review-heap-snapshot-retained-size-input",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_input_review",
                "heapSnapshotRetainedSizeInputReview",
                "heap_snapshot_retained_size_executor_input_review",
                "heapSnapshotRetainedSizeExecutorInputReview",
                "heap_snapshot_retained_size_approval_gate",
                "heapSnapshotRetainedSizeApprovalGate",
                "review_heap_snapshot_retained_size_input",
                "reviewHeapSnapshotRetainedSizeInput",
            )
        )


def _is_heap_snapshot_retained_path_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_retained_size_input_review_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-path-preflight",
            "heap-snapshot-constructor-growth-retained-path-preflight",
            "heap-snapshot-retained-size-path-to-root-preflight",
            "review-heap-snapshot-retained-path-preflight",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_path_preflight",
                "heapSnapshotRetainedPathPreflight",
                "heap_snapshot_constructor_growth_retained_path_preflight",
                "heapSnapshotConstructorGrowthRetainedPathPreflight",
                "heap_snapshot_retained_size_path_to_root_preflight",
                "heapSnapshotRetainedSizePathToRootPreflight",
                "review_heap_snapshot_retained_path_preflight",
                "reviewHeapSnapshotRetainedPathPreflight",
            )
        )


def _is_heap_snapshot_constructor_growth_drilldown_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-constructor-growth-drilldown",
            "execute-heap-snapshot-constructor-growth-drilldown-analysis",
            "heap-snapshot-constructor-growth-drilldown-analysis",
            "heap-snapshot-constructor-growth-drilldown-executor-result",
            "heap-snapshot-constructor-growth-drilldown-executor-mvp",
            "constructor-growth-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_constructor_growth_drilldown",
                "executeHeapSnapshotConstructorGrowthDrilldown",
                "execute_heap_snapshot_constructor_growth_drilldown_analysis",
                "executeHeapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_analysis",
                "heapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_executor_result",
                "heapSnapshotConstructorGrowthDrilldownExecutorResult",
                "heap_snapshot_constructor_growth_drilldown_executor_mvp",
                "heapSnapshotConstructorGrowthDrilldownExecutorMvp",
                "constructor_growth_heap_snapshot_executor",
                "constructorGrowthHeapSnapshotExecutor",
            )
        )


def _is_heap_snapshot_constructor_growth_drilldown_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_constructor_growth_drilldown_execution_request(protection_name, context):
            return False
        if _is_heap_snapshot_retained_path_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-constructor-growth-drilldown",
            "heap-snapshot-diff-constructor-growth-drilldown",
            "review-heap-snapshot-constructor-growth-drilldown",
            "review-heap-snapshot-diff-constructor-growth",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_constructor_growth_drilldown",
                "heapSnapshotConstructorGrowthDrilldown",
                "heap_snapshot_diff_constructor_growth_drilldown",
                "heapSnapshotDiffConstructorGrowthDrilldown",
                "review_heap_snapshot_constructor_growth_drilldown",
                "reviewHeapSnapshotConstructorGrowthDrilldown",
                "review_heap_snapshot_diff_constructor_growth",
                "reviewHeapSnapshotDiffConstructorGrowth",
            )
        )


def _is_heap_snapshot_diff_selected_analysis_input_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_constructor_growth_drilldown_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-selected-analysis-input-preflight",
            "heap-snapshot-diff-followup-selected-analysis-preflight",
            "heap-snapshot-diff-selected-followup-preflight",
            "review-heap-snapshot-diff-selected-analysis-input",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_selected_analysis_input_preflight",
                "heapSnapshotDiffSelectedAnalysisInputPreflight",
                "heap_snapshot_diff_followup_selected_analysis_preflight",
                "heapSnapshotDiffFollowupSelectedAnalysisPreflight",
                "heap_snapshot_diff_selected_followup_preflight",
                "heapSnapshotDiffSelectedFollowupPreflight",
                "review_heap_snapshot_diff_selected_analysis_input",
                "reviewHeapSnapshotDiffSelectedAnalysisInput",
            )
        )


def _is_heap_snapshot_diff_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_selected_analysis_input_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-followup-checkpoint",
            "heap-snapshot-diff-analysis-plan",
            "review-heap-snapshot-diff-followup-checkpoint",
            "review-heap-snapshot-diff-executor-result-followup",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_followup_checkpoint",
                "heapSnapshotDiffFollowupCheckpoint",
                "heap_snapshot_diff_analysis_plan",
                "heapSnapshotDiffAnalysisPlan",
                "review_heap_snapshot_diff_followup_checkpoint",
                "reviewHeapSnapshotDiffFollowupCheckpoint",
                "review_heap_snapshot_diff_executor_result_followup",
                "reviewHeapSnapshotDiffExecutorResultFollowup",
            )
        )


def _is_heap_snapshot_diff_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_followup_checkpoint_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-diff-executor",
            "heap-snapshot-diff-executor-result",
            "heap-snapshot-diff-executor-mvp",
            "raw-heap-diff-executor",
            "review-heap-snapshot-diff-executor-raw-heap-parser-or-executor-mvp",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_diff_executor",
                "executeHeapSnapshotDiffExecutor",
                "heap_snapshot_diff_executor_result",
                "heapSnapshotDiffExecutorResult",
                "heap_snapshot_diff_executor_mvp",
                "heapSnapshotDiffExecutorMvp",
                "raw_heap_diff_executor",
                "rawHeapDiffExecutor",
                "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp",
                "reviewHeapSnapshotDiffExecutorRawHeapParserOrExecutorMvp",
            )
        )


def _is_heap_snapshot_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_collect_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_readiness_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-readiness",
            "cdp-heap-snapshot-readiness",
            "heap-profiler-readiness",
            "review-heap-snapshot-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_readiness",
                "heapSnapshotReadiness",
                "cdp_heap_snapshot_readiness",
                "cdpHeapSnapshotReadiness",
                "heap_profiler_readiness",
                "heapProfilerReadiness",
                "review_heap_snapshot_readiness",
                "reviewHeapSnapshotReadiness",
            )
        )


def _is_heap_snapshot_collect_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_readiness_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-collect",
            "cdp-heap-snapshot-collect",
            "collect-heap-snapshot",
            "reviewed-heap-snapshot-collect",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_collect",
                "heapSnapshotCollect",
                "cdp_heap_snapshot_collect",
                "cdpHeapSnapshotCollect",
                "collect_heap_snapshot",
                "collectHeapSnapshot",
                "reviewed_heap_snapshot_collect",
                "reviewedHeapSnapshotCollect",
                "execute_heap_snapshot_collect",
                "executeHeapSnapshotCollect",
            )
        )


def _is_heap_snapshot_diff_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-readiness",
            "heap-snapshot-diff-review",
            "review-heap-snapshot-diff",
            "heap-diff-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_readiness",
                "heapSnapshotDiffReadiness",
                "heap_snapshot_diff_review",
                "heapSnapshotDiffReview",
                "review_heap_snapshot_diff",
                "reviewHeapSnapshotDiff",
                "heap_diff_readiness",
                "heapDiffReadiness",
            )
        )


def _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-bounded-gate",
            "heap-snapshot-diff-executor-bounded-executor-gate",
            "heap-snapshot-diff-bounded-gate",
            "heap-diff-executor-bounded-gate",
            "raw-heap-diff-bounded-gate",
            "review-heap-snapshot-diff-executor-bounded-gate",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_bounded_gate",
                "heapSnapshotDiffExecutorBoundedGate",
                "heap_snapshot_diff_executor_bounded_executor_gate",
                "heapSnapshotDiffExecutorBoundedExecutorGate",
                "heap_snapshot_diff_bounded_gate",
                "heapSnapshotDiffBoundedGate",
                "heap_diff_executor_bounded_gate",
                "heapDiffExecutorBoundedGate",
                "raw_heap_diff_bounded_gate",
                "rawHeapDiffBoundedGate",
                "review_heap_snapshot_diff_executor_bounded_gate",
                "reviewHeapSnapshotDiffExecutorBoundedGate",
            )
        )


def _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-transaction-preflight",
            "heap-snapshot-diff-transaction-preflight",
            "heap-diff-executor-transaction-preflight",
            "raw-heap-diff-transaction-preflight",
            "review-heap-snapshot-diff-executor-transaction-preflight",
            "preflight-heap-snapshot-diff-executor-transaction",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_transaction_preflight",
                "heapSnapshotDiffExecutorTransactionPreflight",
                "heap_snapshot_diff_transaction_preflight",
                "heapSnapshotDiffTransactionPreflight",
                "heap_diff_executor_transaction_preflight",
                "heapDiffExecutorTransactionPreflight",
                "raw_heap_diff_transaction_preflight",
                "rawHeapDiffTransactionPreflight",
                "review_heap_snapshot_diff_executor_transaction_preflight",
                "reviewHeapSnapshotDiffExecutorTransactionPreflight",
                "preflight_heap_snapshot_diff_executor_transaction",
                "preflightHeapSnapshotDiffExecutorTransaction",
            )
        )


def _is_heap_snapshot_diff_executor_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-approval-plan",
            "heap-snapshot-diff-approval-plan",
            "heap-diff-executor-approval-plan",
            "review-heap-snapshot-diff-executor-approval",
            "raw-heap-diff-approval-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_approval_plan",
                "heapSnapshotDiffExecutorApprovalPlan",
                "heap_snapshot_diff_approval_plan",
                "heapSnapshotDiffApprovalPlan",
                "heap_diff_executor_approval_plan",
                "heapDiffExecutorApprovalPlan",
                "review_heap_snapshot_diff_executor_approval",
                "reviewHeapSnapshotDiffExecutorApproval",
                "raw_heap_diff_approval_plan",
                "rawHeapDiffApprovalPlan",
            )
        )


def _is_heap_snapshot_diff_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-preflight",
            "heap-snapshot-diff-preflight",
            "heap-diff-executor-preflight",
            "review-heap-snapshot-diff-executor",
            "raw-heap-diff-preflight",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_preflight",
                "heapSnapshotDiffExecutorPreflight",
                "heap_snapshot_diff_preflight",
                "heapSnapshotDiffPreflight",
                "heap_diff_executor_preflight",
                "heapDiffExecutorPreflight",
                "review_heap_snapshot_diff_executor",
                "reviewHeapSnapshotDiffExecutor",
                "raw_heap_diff_preflight",
                "rawHeapDiffPreflight",
            )
        )



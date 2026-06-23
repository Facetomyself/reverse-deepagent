# Workspace Contract & Delivery Transaction System

## Workspace Contract

每次 deterministic pipeline 输出 `workspace/workspace-contract.json`，用于把 DeepAgents 子智能体、middleware checkpoint 和 workspace artifact 路由固化成机器可读契约。

### Artifact Routes

当前 contract 覆盖的虚拟协作区包括 `/workspace/recon/`、`/workspace/browser/`、`/workspace/debugger/`、`/workspace/hooks/`、`/workspace/timeline/`、`/workspace/rebuild/`、`/workspace/review/`、`/workspace/delivery/`、`/workspace/runtime/` 和 `/workspace/evidence/`。

`workspace/backend-artifact-manifest.json` 用 `RuntimeArtifactManifest` / `RuntimeArtifactManifestEntry` 描述 artifact key、路径、类别、kind、producer backend、transport 和 target platforms。

### Dual Write & Foldered Canonical Migration

`WorkspacePathResolver` 可按 artifact key、legacy path、future path 或 `virtual://workspace/...` URI 解析同一 artifact。

- pipeline 显式 `enable_workspace_dual_write=True` 时同时写 legacy path 与 foldered future path。
- `read_workspace_artifact` 作为只读工具支持多种 ref 类型解析。
- 完整的 dual-write pilot、foldered-canonical migration 从 planning → executor preflight → physical apply → post-apply validation → legacy fallback tightening → migration finalization → broader rollout → commit/rollback 的审阅工作流由一组 workspace tools 覆盖（`plan_workspace_dual_write_pilot`、`review_workspace_dual_write_pilot_workflow`、`record_workspace_dual_write_pilot_result` 等），均保持 review-only 和 plan-only 语义。

## Evidence Promotion

Web pipeline 与平台中立 pipeline 生成一组平台无关的证据晋升 artifact：

- `workspace/evidence-candidates.json`：所有规范化 `EvidenceItem` 候选索引
- `workspace/evidence-validated.json`：通过通用验证门槛的证据索引
- `workspace/evidence-promotion.json`：candidate / validated / promoted / rejected 全量记录

通用规则：低置信、工具不可用、`available=false`、unsupported 阻断晋升；高置信 source/callstack/runtime context/function validation 更容易进入 promoted。

## Review Gate

`review_hints` 自动门禁在生成 `rebuild-plan.json` 后评估，输出 `workspace/review-gate.json`。

输入：
- `rebuild_plan.ready`、`rebuild_plan.review_hints`
- `evidence-promotion.json` 的 validated / promoted / rejected 摘要

门禁结果：
- `status`: `pass` / `warn` / `block`
- `blocking_hint_codes`：阻断交付的 risk hint
- `evidence_counts` 与 `evidence_review_required_items`
- `next_action`: `delivery_allowed` / `manual_review_before_delivery` / `manual_review_or_expand_evidence` / `review_stitch_proposals_before_delivery`

阻断规则：
- 任意 `severity=risk` 阻断自动交付
- `rebuild_plan.ready=false` 阻断
- 无 validated evidence 阻断
- ready=true 但无 promoted evidence 阻断
- pending review requirement（如 `flow_timeline.stitch_proposals`）阻断

Auto-stitch 各阶段（dry-run / conflict resolution / policy gate / materialization plan / rollback plan）固定 `would_materialize=false`，只在 reviewer 审批后 materialize。

## Delivery Transaction System

### Local Delivery Executor

`LocalDeliveryExecutor` 默认 dry-run。显式 `apply` 复制文件并写 delivery-receipt / delivery-transaction-journal。

支持的命令：
- `execute_local_delivery`：本地 artifact 交付
- `plan_delivery_resume` / `execute_delivery_resume`：恢复规划与执行
- `execute_delivery_transition`：preflight / apply recovery / commit cross-run transaction
- `execute_delivery_recovery`：recovery preflight → apply
- `write_delivery_rollback_state` / `execute_delivery_rollback`：rollback state 写入与执行

Transaction journal 支持：
- `delivery-transaction-journal.json` + append-only journal 审计
- `delivery-receipt.json` 交付回执
- `delivery-manifest-revision.json` manifest revision（commit 时）
- `backend-artifact-manifest-mutation.json` manifest mutation（in-place 模式）
- `backend-artifact-manifest.rollback.json` 原地更新前的 rollback checkpoint
- `delivery-resume-plan.json` / `delivery-resume-execution.json`
- `delivery-rollback-state.json` / `delivery-rollback-execution.json`

### External Delivery Providers

通过 `ExternalDeliveryProviderRegistry` 解析，内置 provider：

| Provider | Alias | Transport |
|----------|-------|-----------|
| review-only | noop, manual-handoff | blocked handoff |
| local-archive | filesystem-release | 本地归档 |
| webhook | http-webhook | POST |
| presigned-object | s3-presigned, presigned-url | PUT |
| github-release | gh-release | GitHub Release API |

支持 `reverse_deepagent.external_delivery_providers` entry point 发现外部 provider。

特性：
- `external_delivery_idempotency_key` = transaction id
- append-only `external-delivery-idempotency-ledger.json`
- duplicate guard 阻断重复 delivery
- retry / Retry-After / rate-limit attempt 摘要

### Transaction Lock Providers

由 delivery subagent 的 `manage_delivery_transaction_lock_provider` 暴露：`inspect_lock` / `acquire_lock` / `renew_lock` / `release_lock`。

默认 registry：
- `local-file-lock`（local-file）：本地 JSON lock
- `sqlite-lock`（db-lock, sqlite-transaction-lock）：SQLite transactional store
- `redis-lock`（redis, redis-lease-lock）：外部 Redis lease

支持 fencing token 审计，dry-run 只返回计划。

### Delivery Resume Workflow

`execute_delivery_resume_workflow` 支持 `plan_workflow` / `execute_workflow`，把多个显式 step（recovery、commit、lock acquire/renew/release）串成 review-gated workflow。

规划阶段输出：
- `lock_lifecycle_plan`：reviewed acquire/release 建议
- `lease_renewal_plan`：fencing token lease 续期建议
- `workflow_readiness_plan`：包含 `runtime_gate_evidence_projection` 与 `step_dependency_contexts`

### Transaction State Evaluation

`evaluate_delivery_transaction_state(...)` 把 result / journal / external result / recovery / commit artifact 归一化成：`planned`、`local_applied`、`manifest_patch_written`、`manifest_mutated`、`recovery_required`、`recovered`、`external_delivery_attempted`、`external_delivered`、`committed`、`blocked`。

`evaluate_delivery_rollback_state(...)` 进一步归一化 rollback phase：`rollback_preflight_required`、`rollback_decision_required`、`rollback_applied`、`committed` 等。

### Delivery Plugin Packages

- `packages/reverse-deepagent-external-delivery-provider-template/`：外部 delivery provider 模板
- 接入 S3 / OSS / GCS / GitLab Release 时优先复制模板

# BrowserProvider / MCP Deprecation Execution Plan

## Plan Task Card

- task_description: 将 `reverse-deepagent` 的 Web 逆向主链路从 `jsreverser-mcp` 迁移到项目自有的 `native-web + BrowserProvider + native collectors` 架构，并保留 MCP 作为 legacy 兼容后端。
- mode: execution-ready planning
- plan_target: BrowserProvider contract、NativeWebRuntime、CloakBrowser provider、native collectors、doctor、artifact parity、MCP legacy downgrade。
- constraints:
  - 不删除现有 MCP 能力，直到 native-web 达到基础采集闭环。
  - 浏览器是可插拔模块，MCP 不是新的抽象边界。
  - CloakBrowser 是 optional provider，不能成为硬依赖，不能提交二进制。
  - coordinator 不直接依赖 Playwright、CDP、CloakBrowser 或 MCP tool 名。
  - artifact schema 尽量保持向后兼容。
- execution_flags:
  - 按阶段推进。
  - 每个关键阶段跑测试、review diff、提交 commit。
  - 真实浏览器 smoke 需要显式启用，不默认下载或启动重型二进制。

## 当前阶段状态

| Phase | 状态 | 验收证据 |
| --- | --- | --- |
| 0. 文档与迁移口径 | 已完成 | `docs/runtime/browser-provider-architecture.md`、`docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md` |
| 1. BrowserProvider contract | 已完成 | `tests.test_browser_provider_contract`、`tests.test_browser_provider_registry` |
| 2. Playwright provider skeleton | 已完成 | `tests.test_playwright_session`、`tests.test_playwright_provider`；系统 Chrome executable path 真实 smoke 已验证 |
| 3. Native collector baseline | 已完成 | `tests.test_browser_collectors` |
| 4. NativeWebRuntime 最小接入 | 已完成 | `tests.test_native_web_runtime`；`remote-cdp` smoke 路径已接入；Playwright system Chrome smoke 已验证；runtime-eval 候选验证 baseline 已接入 |
| 5. CloakBrowser provider skeleton | 已完成 | `tests.test_cloakbrowser_provider`，optional `.[cloak]` 已接入；真实 launch / persistent profile / connect baseline / native-web fixture smoke 已验证 |
| 6. Browser doctor provider mode | 已完成 | `reverse-agent-doctor --browser ...` 已实现并测试 |
| 7. Native artifact parity | 已完成 | DOM、console、script inventory、navigation events 已落盘，manifest 带 BrowserProvider metadata，63 项相关测试通过 |
| 8. CDP-enhanced collectors | 已完成（fallback 增强已补） | requestWillBeSent、response body metadata、Debugger.scriptParsed source cache、WebSocket frame cache 已实现并测试；缺 CDP event cache 时，script source 可回落到 provider-neutral script inventory，WebSocket frame 可回落到 hook timeline；`remote-cdp` 提供真实 smoke 路径，Playwright system Chrome smoke 与 CloakBrowser fixture smoke 均已验证 |
| 9. Hook / breakpoint migration | 已完成（paused-session continuation preflight 与 durable paused-session snapshot inspect-only baseline 已补；跨进程 live CDP pause continuation、执行式 custom loader traversal / async chunk loading / 深层 module federation 分析、任意闭包内部函数自动 wrapper hook、JS heap 级细粒度 mutation audit / object graph diff、manual stitch candidates 已补、auto-stitch dry-run scoring baseline 已补；自动全链路跨请求 timeline materialization 待后续） | fetch/xhr、cookie、WebSocket、anti-debug hook baseline 已实现；target-function wrapper baseline 已实现，可对 `window.buildSign` 这类全局可达路径安装 wrapper 并输出 `function-hooks.json` / `function-hook-timeline.json`；webpack-like module export hook baseline 已实现，可对显式 `module_id` / `export_name` 通过 `window.__webpack_require__` 解析出的导出函数安装 wrapper 并输出 `module-hooks.json` / `module-hook-timeline.json`；module discovery baseline 已实现，可从 script inventory 提取 webpack-like `module.exports` 导出候选，也可只读 introspect `require.c` / `require.m` runtime cache / registry，并支持显式 `module_runtime_paths` 下的 custom object runtime / module federation exposed-module function-path candidate，输出 `module-registry.json` / `module-candidates.json`；closure-scope function discovery baseline 已实现，可在显式 paused callframe 内用只读 `typeof` 证明候选闭包函数并输出 `closure-functions.json` / `closure-function-candidates.json`；page-level mutation audit baseline 已实现，可围绕显式触发表达式输出 `page-mutation-audit.json` 粗粒度 before/after diff；MutationObserver timeline baseline 已实现，可围绕显式 trigger 输出 `mutation-observer-timeline.json` 有限 DOM mutation records；source-level logpoint baseline 已实现，可对脚本 URL / 行号安装条件断点，支持 generated bundle offset、Source Map exact、GLB bias、sourceRoot 和 indexed sections 到 CDP generated line / column 的最小重映射，并输出 `source-logpoints.json` / `source-logpoint-timeline.json`；retained paused-session registry baseline 已实现，可用 `pause_session_id` 续用同进程内保留的 paused session 并执行 inspect / evaluate / step / resume，且 `continuation_preflight` 会标出 `source=registry`、requested action、pre-action lifecycle 与 live continuation 可用性；durable paused-session snapshot inspect-only baseline 已实现，可通过 `persist_paused_session` / `paused_session_store_dir` 落盘 debugger session、timeline、callframes、breakpoints 和 inspect-only `continuation_preflight` 供后续进程 inspect / audit，并在跨进程 resume / step / evaluate 时返回 `status=action_blocked` / `live_paused_session_required`；BreakpointManager 通过 CDP capability gate 接入 `apply_minimal_protection`，`breakpoints.json` / `debugger-paused.json` / `callframes.json` / 显式 `callframe-evaluations.json` / `mutation-audit.json` / `debugger-actions.json` / `debugger-session.json` / `debugger-timeline.json` artifact ref 与 evidence 映射已补齐；native-web runtime-eval 候选验证已作为迁移中的最小 replay baseline；native-web recon `flow-timeline.json` baseline 已实现，可把 navigation / network / hook / replay 片段落盘，并为 entry 增加 request id、URL path、method、initiator function、hook path、candidate id 等保守 `correlation` hints；同时会派生 request id、URL path + method、function name、candidate id、hook path 维度的 `correlation_groups`，所有 group 都带 `stitching=false` / `scope=correlation-hints-only`，并用 `verification.status=weak|reviewable|ready_for_manual_stitch_review`、evidence booleans 与 `missing_for_ready` 标注人工复核准备度；`reviewable` / `ready_for_manual_stitch_review` group 会进一步生成 `stitch_candidates`，作为 manual-only 候选链并固定 `automatic_stitching=false`；其中 `ready_for_manual_stitch_review` candidate 还会生成 `stitch_proposals`，列出 reviewer approval requirements、blocking conditions 和 pending review decision，作为 review-gated stitching proposal baseline；pending proposal 现在会进入 evidence promotion 的 `review_required_*` 摘要，并由 review gate 以 `review_stitch_proposals_before_delivery` 阻断自动交付；显式 `stitch_review_decisions` 审批通过后可生成 `stitched-flow.json` reviewer-approved baseline，`stitching=true` 但 `automatic_stitching=false`，未审批时仍固定 `approved=false` / `stitching=false`；显式 `flow-timeline` continuation baseline 可继续把上一轮 timeline 与 network / hook / debugger / replay 片段归一化为 `flow-timeline.json`；`stitch_candidates` 现在还会派生 `auto_stitch_dry_runs`，输出 `confidence_score`、`score_reasons`、`conflict_reasons`、`review_required=true`、`would_materialize=false` 和 `automatic_stitching=false`，仅作为 scoring / review aid，不生成 `stitched-flow.json`，也不绕过 review gate；这些 hints、groups、candidates、dry-runs、proposals 和 approved baseline 仍不是自动全链路 materialization |
| 10. MCP legacy downgrade | 已完成 | `legacy-mcp` canonical backend 已实现，`mcp` / `jsreverser-mcp` 保留 deprecated alias 并输出 CLI warning；doctor 支持 `--legacy-mcp`；README / runtime docs 默认推荐 `native-web` |
| 11. DeepAgents workspace contract | 已完成（indexed-only contract + manifest-only alias baseline） | `src/reverse_deepagent/workspace_contract.py`、`tests.test_workspace_contract`；Web 与 platform-neutral pipeline 均输出 `workspace/workspace-contract.json`，`workspace/backend-artifact-manifest.json` 为已登记 workspace artifact entry 增加 `metadata.workspace_alias`；现有扁平 `workspace/*.json` 路径保持 canonical，不做物理迁移 |
| 12. BrowserProvider smoke matrix / lifecycle | 已完成（metadata-only baseline） | `src/reverse_deepagent/browser/smoke.py`、`tests.test_browser_smoke_matrix`、`tests.test_doctor`；`reverse-agent-doctor --browser-provider-matrix` 输出 side-effect-free provider/capability/lifecycle matrix，单 provider doctor 输出保留兼容字段并新增 `browser_provider.smoke_matrix`；真实启动仍只能通过显式 `--launch-browser-smoke` |
| 13. Auto-stitch dry-run scoring baseline | 已完成（dry-run only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`；`flow-timeline.json` 输出 `auto_stitch_dry_runs` 与 `auto_stitch_dry_run_count`，包含 `confidence_score`、`score_reasons`、`conflict_reasons`、`review_required=true`、`would_materialize=false`、`dry_run=true` 和 `automatic_stitching=false`；不自动生成 `stitched-flow.json`，不绕过 review gate |
| 14. Auto-stitch policy decision gate baseline | 已完成（decision-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`；`flow-timeline.json` 输出 `auto_stitch_policy_decisions` / `auto_stitch_policy_summary`，把 confidence threshold、missing evidence、conflict reasons 和 automatic materialization request 归一化成 `ready_for_review_gate` / `blocked` 决策；仍固定 `would_materialize=false`、`automatic_stitching=false`，不生成 `stitched-flow.json` |
| 15. Auto-stitch materialization plan baseline | 已完成（plan-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`；policy-eligible `auto_stitch_policy_decisions` 可生成 `auto_stitch_materialization_plans` / `auto_stitch_materialization_summary`，包含 target artifact、entry path、review requirements、conflict resolution、rollback plan 和 `writes_artifact=false`；不生成 `stitched-flow.json`，不替代 reviewer-approved materialization |
| 16. Review-approved auto-stitch materializer skeleton | 已完成（explicit-review-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；显式 `auto_stitch_materialization_review_decisions` 审批后，可把 policy-eligible plan 产出为 `auto_stitch_materialization_results`，并生成 `virtual://workspace/auto-stitch-materialization-results.json` 与 reviewer-approved `stitched-flow.json` baseline；仍固定 `automatic_stitching=false`，无审批不写 artifact |
| 17. Materialization audit / rollback writer baseline | 已完成（audit-and-plan-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；review-approved materialization result 会生成 `auto_stitch_materialization_audit_entries` / `auto_stitch_materialization_rollback_plans`，并暴露 `virtual://workspace/stitched-flow-materialization-audit.json` 与 `virtual://workspace/stitched-flow-rollback-plan.json`；rollback 只是人工复核计划，固定 `automatic_rollback=false` |
| 18. Auto-stitch conflict resolver baseline | 已完成（review-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；`flow-timeline.json` 输出 `auto_stitch_conflict_resolutions` / `auto_stitch_conflict_resolution_summary`，并暴露 `virtual://workspace/auto-stitch-conflict-resolutions.json`；resolver 只给出 review-preferred candidate、alternatives 与 unresolved conflicts，固定 `would_materialize=false` / `automatic_stitching=false` |
| 19. Materialization transaction log baseline | 已完成（transaction-log-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；review-approved materialization 会聚合 result / audit / rollback plan / conflict resolution 为 `auto_stitch_materialization_transactions` / summary，并暴露 `virtual://workspace/stitched-flow-materialization-transactions.json`；transaction log 只读，不执行 rollback，不重算 review gate |
| 20. Rollback execution baseline | 已完成（dry-run / explicit-review-only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；rollback-ready plan 会生成 `auto_stitch_rollback_execution_plans`，显式 `auto_stitch_rollback_execution_review_decisions` 审批后只记录 logical rollback result，并暴露 `virtual://workspace/stitched-flow-rollback-executions.json`；不物理改写 `stitched-flow.json`，不自动 rollback，不替换标准 review gate |
| 21. Post-rollback review gate recompute baseline | 已完成（blocking baseline，不替换标准 gate） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；显式 rollback execution result 会派生 `auto_stitch_rollback_review_gate_recomputations`，暴露 `virtual://workspace/review-gate-after-rollback.json`，默认 `blocked=true` / `delivery_allowed=false` / `does_not_replace_review_gate=true` |
| 22. Physical rollback dry-run diff baseline | 已完成（dry-run diff only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；post-rollback gate recomputation 会派生 `auto_stitch_physical_rollback_dry_run_diffs`，暴露 `virtual://workspace/stitched-flow-physical-rollback-diff.json`，只描述 would-remove / manifest impact，不物理修改 artifact |
| 23. Explicit-review-only physical rollback mutation baseline | 已完成（artifact model mutation only） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；显式 `auto_stitch_physical_rollback_review_decisions` 审批后生成 `auto_stitch_physical_rollback_results`，暴露 `virtual://workspace/stitched-flow-physical-rollback-results.json`，并从本轮 `stitched_flows` artifact model 中移除匹配 materialization；仍固定 `automatic_rollback=false`，不替换标准 `review-gate.json` |
| 24. Post-physical-rollback review gate rerun baseline | 已完成（blocking baseline，不替换标准 gate） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；physical rollback result 会派生 `auto_stitch_post_physical_rollback_review_gate_reruns`，暴露 `virtual://workspace/review-gate-after-physical-rollback.json`，默认 `blocked=true` / `delivery_allowed=false` / `does_not_replace_review_gate=true` |
| 25. Standard review gate replacement baseline | 已完成（explicit-review-only，Step 26 已补 guard rerun） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；显式 `auto_stitch_standard_review_gate_replacement_review_decisions` 审批后记录 `auto_stitch_standard_review_gate_replacement_results`，暴露 `virtual://workspace/review-gate-replacement-results.json`，标记标准 `workspace/review-gate.json` artifact model 已替换，但仍固定 `delivery_allowed=false` / `automatic_delivery=false` 并要求后续 delivery guard rerun |
| 26. Delivery guard rerun after standard review gate replacement baseline | 已完成（artifact-model guard rerun only，Step 27 已补 package baseline） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；standard review gate replacement result 会派生 `auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns`，暴露 `virtual://workspace/delivery-guard-after-review-gate-replacement.json`，记录 delivery guard rerun passed / delivery_allowed=true，但仍固定 `automatic_delivery=false` |
| 27. Final delivery package after delivery guard rerun baseline | 已完成（artifact-model package only，不提交跨运行 transaction） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；delivery guard passed 后派生 `auto_stitch_post_standard_review_gate_replacement_final_delivery_packages`，暴露 `virtual://workspace/final-delivery-package-after-review-gate-replacement.json`，记录 package ready / final delivery packaged / delivery_allowed=true，但仍固定 `automatic_delivery=false`、`external_delivery_performed=false`、`cross_run_transaction_committed=false` |
| 28. Final delivery transaction commit record baseline | 已完成（explicit-review-only record，不执行真实跨运行事务） | `tests.test_flow_timeline`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`；显式 `auto_stitch_transaction_commit_review_decisions` 审批后，基于 final delivery package 记录 `auto_stitch_transaction_commit_results`，暴露 `virtual://workspace/final-delivery-transaction-commit.json`，固定 `artifact_model_transaction_commit_recorded=true` 但 `cross_run_transaction_committed=false`、`manifest_revision_committed=false`、`filesystem_artifact_mutated=false`、`external_delivery_performed=false` |
| 29. Local delivery executor contract baseline | 已完成（local-filesystem executor，默认 dry-run） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；新增 `LocalDeliveryExecutor`、`DeliveryExecutorConfig`、`DeliveryReceipt` 和 `DeliveryTransactionJournal`，支持 dry-run planning 与显式 apply 本地复制；新增 `execute_local_delivery` tool 并挂入 delivery subagent；暴露 `workspace/delivery-receipt.json` / `workspace/delivery-transaction-journal.json` 路由，固定 `external_delivery_performed=false`、`manifest_revision_committed=false` |
| 30. Local delivery manifest revision baseline | 已完成（explicit local manifest revision，不改写标准 backend manifest） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `commit_manifest_revision=true` 时生成 `DeliveryManifestRevision`，apply 模式写 `workspace/delivery-manifest-revision.json` 并在 journal 标记 `manifest_revision_committed=true`，同时固定 `backend_manifest_mutated=false`、`external_delivery_performed=false` |
| 31. Backend artifact manifest mutation policy baseline | 已完成（local patched-copy policy，不 in-place 改写标准 manifest） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `commit_backend_manifest_mutation=true` 时生成 `BackendManifestMutation`，dry-run 只返回 plan，apply 模式写 `workspace/backend-artifact-manifest-mutation.json` 与 `workspace/backend-artifact-manifest.patched.json`，并固定 `backend_manifest_mutated=false`、`external_delivery_performed=false`、`cross_run_transaction_committed=false` |
| 32. Backend manifest in-place mutation preflight baseline | 已完成（preflight-only，不执行 in-place mutation） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `preflight_backend_manifest_in_place_mutation=true` 时生成 `BackendManifestInPlacePreflight`，dry-run 只返回 plan，apply 模式写 `workspace/backend-artifact-manifest-preflight.json`，校验 source digest、patched manifest 可用性和 artifact key 冲突，仍固定 `backend_manifest_mutated=false`、`external_delivery_performed=false`、`cross_run_transaction_committed=false` |
| 33. Backend manifest in-place mutation executor baseline | 已完成（explicit-review-only，本地 rollback checkpoint，不提交跨运行事务） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `approve_backend_manifest_in_place_mutation=true` 且 apply、patch written、preflight passed、expected source digest 匹配时，写 `workspace/backend-artifact-manifest-in-place-mutation.json` 与 `workspace/backend-artifact-manifest.rollback.json`，并原地更新标准 backend manifest；仍固定 `external_delivery_performed=false`、`cross_run_transaction_committed=false` |
| 34. Backend manifest cross-run recovery preflight baseline | 已完成（preflight-only，不 restore、不提交跨运行事务） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `preflight_backend_manifest_recovery=true` 时读取上一轮 `delivery-transaction-journal.json`、in-place mutation record、patched manifest、rollback checkpoint 和当前 source manifest digest，写 `workspace/backend-artifact-manifest-recovery-preflight.json`，输出 `ready_for_review` / `blocked` / `no_recovery_required`；仍固定 `external_delivery_performed=false`、`cross_run_transaction_committed=false` |
| 35. Backend manifest cross-run transaction commit baseline | 已完成（local-filesystem commit，不 external delivery） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `commit_cross_run_transaction=true` 且 apply、上一轮 journal、recovery preflight、source digest 与 expected transaction id 全部通过时，写 `workspace/backend-artifact-manifest-transaction-commit.json` 并把上一轮 journal 标记为 `cross_run_transaction_committed=true`；仍固定 `external_delivery_performed=false`，commit 本身不 restore manifest |
| 36. Backend manifest recovery apply baseline | 已完成（explicit-review-only rollback checkpoint restore，不 external delivery） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `apply_backend_manifest_recovery=true` 且 apply、上一轮 journal、ready recovery preflight、rollback checkpoint、source digest 与 expected transaction id 全部通过时，写 `workspace/backend-artifact-manifest-recovery.json`，把 `backend-artifact-manifest.rollback.json` 恢复为标准 `backend-artifact-manifest.json`，并把上一轮 journal 标记为 `backend_manifest_recovered=true`；仍固定 `external_delivery_performed=false`、`cross_run_transaction_committed=false`，不实现完整 recovery state machine |
| 37. ExternalDeliveryProvider contract baseline | 已完成（review-only provider 默认阻断，不发布） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；显式 `request_external_delivery=true` 时调用 `ExternalDeliveryProvider` contract，默认 `ReviewOnlyExternalDeliveryProvider` 写 `workspace/external-delivery-result.json` blocked handoff record，并在 journal 记录 `external_delivery_result_path` / `external_delivery_performed=false`；fake provider 测试覆盖配置 provider 后可把 `external_delivery_performed=true` 写回 result / journal；仍不内置真实上传、推送、发布或第三方交付实现 |
| 38. ExternalDeliveryProvider registry / entry-point discovery baseline | 已完成（provider registry，factory 不在 metadata load 阶段执行） | `tests.test_external_delivery_registry`、`tests.test_delivery_executors`；新增 `ExternalDeliveryProviderRegistry`、`ExternalDeliveryProviderRegistration`、`ExternalDeliveryProviderCapabilities`、`ExternalDeliveryProviderFactory`、`reverse_deepagent.external_delivery_providers` entry point group 与 `build_default_external_delivery_provider_registry()`；默认 registry 注册 `review-only`、`noop`、`manual-handoff`，加载 entry point registration 时不调用 provider factory；`LocalDeliveryExecutor` 在未注入 provider object 时通过 registry 解析 `external_delivery_provider_id`；该阶段不内置真实 release provider；webhook 已由 Step 43 补齐，presigned object-storage 已由 Step 44 补齐，GitHub Release 已由 Step 60 补齐 baseline |
| 39. ExternalDeliveryProvider doctor / metadata CLI baseline | 已完成（doctor metadata-only，不调用 provider factory） | `tests.test_doctor`、`tests.test_external_delivery_registry`；`reverse-agent-doctor --external-delivery-providers` 输出 `external_delivery_provider_matrix`，列出 provider ids、alias、entry point group、transport、`review_only`、`supports_external_delivery`、summary counts 和 side-effect policy；metadata-only 模式跳过 CDP port probe，不依赖 MCP / Chrome，不调用 provider factory，也不执行 external delivery |
| 40. External delivery idempotency / duplicate guard baseline | 已完成（duplicate guard 默认阻断，不调用 provider） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；新增 `external_delivery_idempotency_key`、`allow_duplicate_external_delivery` 和 `external-delivery-duplicate-guard.json`；idempotency key 默认等于 transaction id 并写入 package / journal metadata；同一 delivery root 中上一轮 journal 或 result 已标记 `external_delivery_performed=true` 时，后续 external delivery 默认在 provider factory / provider 调用前被 blocked，保留上一轮 journal 的 performed 状态；只有显式 `allow_duplicate_external_delivery=true` 才允许 reviewed retry |
| 41. LocalArchiveExternalDeliveryProvider / filesystem-release baseline | 已完成（本地文件系统外部交付 provider，dry-run 无副作用） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增 `LocalArchiveExternalDeliveryProvider`、`local-archive` provider id 与 `filesystem-release` / `archive` alias；`external_delivery_provider_config` / `external_delivery_provider_config_json` 支持传入 `archive_root`；apply 模式把已交付文件复制到本地 archive release dir，并写 `local-archive-manifest.json` / `local-archive-checksums.json`，doctor metadata-only 可见且不调用 factory；duplicate guard 仍在 provider factory 前执行 |
| 42. ExternalDeliveryProvider config redaction / capability metadata guard baseline | 已完成（provider config 只导出 summary，capability metadata 拒绝 secret-like key） | `tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增 `external_delivery_metadata_has_secret_like_keys` 与 external delivery secret keyword guard；`ExternalDeliveryProviderRegistration` 创建时拒绝 capability metadata 中的 token / secret / password / cookie / authorization / credential / private 等 key；`ExternalDeliveryPackage.metadata` 只写 `external_delivery_provider_config_summary`，不导出 provider config 原始值，为后续网络 provider 防泄漏打底；webhook 已由 Step 43 复用，presigned object-storage 已由 Step 44 复用，GitHub Release 已由 Step 60 复用 |
| 43. WebhookExternalDeliveryProvider / HTTP JSON provider baseline | 已完成（dry-run 不发网，apply 显式 POST） | `tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增内置 `WebhookExternalDeliveryProvider`、`webhook` provider id 与 `webhook-json` / `http-webhook` alias；registry / doctor metadata-only 可见且不调用 factory；dry-run 只返回 planned result，不打开 socket；apply 模式向显式 `webhook_url` POST JSON delivery package；metadata 只记录 redacted target URL、request body digest / bytes、status code 与是否请求成功，不记录响应体、响应 header 或请求 header 原始值 |
| 44. PresignedObjectExternalDeliveryProvider / object-storage PUT provider baseline | 已完成（dry-run 不发网，apply 显式 PUT） | `tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增内置 `PresignedObjectExternalDeliveryProvider`、`presigned-object` provider id 与 `object-storage` / `presigned-url` / `s3-presigned` alias；registry / doctor metadata-only 可见且不调用 factory；dry-run 只返回 planned result，不打开 socket；apply 模式向显式 `presigned_url` PUT JSON delivery package；metadata 只记录 redacted target URL、object name、request body digest / bytes、status code 与是否请求成功，不记录响应体、响应 header、请求 header 原始值或 presigned URL query / credentials |
| 45. RuntimeBackend doctor / metadata CLI baseline | 已完成（doctor metadata-only，不调用 backend factory） | `tests.test_doctor`、`tests.test_runtime_registry`；新增 `RuntimeBackendRegistry.list_registration_metadata()` 与 `reverse-agent-doctor --runtime-backends`，输出 `runtime_backend_matrix`，列出 backend ids、alias、entry point group、transport、target platforms、capability flags、summary counts 和 side-effect policy；metadata-only 模式跳过 CDP port probe，不依赖 MCP / Chrome，不调用 backend factory，也不启动浏览器 / MCP / adb / simctl / vendor devtools |
| 46. DeepAgents workspace manifest-only folder alias baseline | 已完成（manifest alias，不物理迁移） | `tests.test_workspace_contract`；`workspace/backend-artifact-manifest.json` 为已登记 workspace artifact entry 增加 `metadata.workspace_alias`，暴露 canonical flat path、foldered future path、virtual URI 和 producer roles；现有 `workspace/*.json` 仍保持 canonical path |
| 47. Delivery transaction state machine skeleton | 已完成（read-only evaluator / transition planner，不执行副作用） | `tests.test_delivery_state_machine`、`tests.test_delivery_executors`；新增 `delivery.state_machine`，`DeliveryExecutionResult.to_dict()` 内嵌 `transaction_state`，可把 result / journal / recovery / commit / external-delivery artifact 归一成 coarse state、completed_states、flags、evidence_paths、blocking_reasons 和 recommended_actions |
| 48. BrowserProvider registry / entry-point discovery baseline | 已完成（registry-driven provider resolution，不启动浏览器） | `tests.test_browser_provider_registry`、`tests.test_native_web_runtime`、`tests.test_doctor`；新增 `reverse_deepagent.browser_providers` entry point group、内置 provider registrations、registration metadata + aliases + keys 输出，`native-web` 通过 registry 解析 provider id / alias，doctor matrix 暴露 provider registration metadata 且 metadata-only 路径不调用 provider factory、不探测 CDP、不启动浏览器、不依赖 MCP |
| 49. Browser Runtime Subagent baseline | 已完成（metadata-only provider tools + explicit session readiness） | `tests.test_browser_runtime_subagent`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `browser_runtime` subagent、prompt、`list_browser_providers` / `describe_browser_provider` tools，runtime 存在时挂载 `ensure_browser_session`，默认 metadata-only 路径不启动浏览器、不探测 CDP、不调用外部 provider factory、不依赖 MCP |
| 50. BrowserProvider plugin package template | 已完成（optional package template，不改 core runtime） | `tests.test_browser_provider_plugin_template`、`tests.test_browser_provider_registry`；新增 `packages/reverse-deepagent-browser-provider-template/`，声明 `reverse_deepagent.browser_providers` entry point，提供 `template-browser` registration / factory / README，证明 metadata-only 注册不调用 factory、不启动浏览器、不探测 CDP、不依赖 MCP |
| 51. BrowserProvider capability compatibility matrix | 已完成（metadata-only capability consistency checks） | `tests.test_browser_smoke_matrix`、`tests.test_doctor`；`browser_provider_smoke_matrix` 每个 provider row 现在包含 `compatibility`，summary 输出 compatible / warning / error counts，doctor matrix 暴露 rule version，metadata-only 路径仍不调用 provider factory、不启动浏览器、不探测 CDP、不依赖 MCP |
| 52. Delivery transaction inspector / doctor baseline | 已完成（read-only artifact inspector，不执行恢复或发布） | `tests.test_delivery_inspector`、`tests.test_delivery_state_machine`、`tests.test_doctor`；新增 `delivery.inspector.inspect_delivery_transaction_root(...)` 与 `reverse-agent-doctor --delivery-transaction-root`，读取 delivery root 标准 transaction artifacts，输出 state_snapshot / transition_plan / artifact load status / missing optional artifacts / load_errors / side-effect policy；metadata-only doctor 路径不启动 Chrome、不检查 MCP、不调用 provider、不写文件 |
| 53. Review Subagent baseline | 已完成（read-only review gate tool，不审批、不交付） | `tests.test_review_subagent`、`tests.test_review_gate`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `subagents.review`、`prompts/review.txt` 与 `evaluate_delivery_review_gate` tool，默认 agent 包含 `review` 子智能体，workspace contract 将 `review` 标记为 implemented；tool 只读取 RebuildResult / EvidencePromotionResult JSON，输出 review gate 与 side-effect policy，不写 artifact、不执行 delivery、不调用 external provider、不记录 approval |
| 54. Timeline Subagent baseline | 已完成（read-only flow timeline review，不 materialize、不审批） | `tests.test_timeline_subagent`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `subagents.timeline`、`prompts/timeline.txt` 与 `review_flow_timeline` tool，默认 agent 在 `review` 前包含 `timeline` 子智能体，workspace contract 将 `timeline` 标记为 implemented；tool 只读取 flow-timeline JSON，输出 entries / correlation groups / stitch proposals / auto-stitch gate 摘要、blockers、warnings、review_required_items 和 side-effect policy，不写 artifact、不生成 stitched-flow、不执行 rollback / delivery |
| 55. Debugger Subagent baseline | 已完成（read-only debugger artifact review，不 resume / step / evaluate） | `tests.test_debugger_subagent`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `subagents.debugger`、`prompts/debugger.txt` 与 `review_debugger_artifacts` tool，默认 agent 在 `timeline` 前包含 `debugger` 子智能体，workspace contract 将 `debugger` 标记为 implemented；tool 只读取 debugger artifacts JSON，输出 paused-session / continuation preflight / callframes / timeline 摘要、blockers、warnings、review_required_items 和 side-effect policy，不发送 CDP 命令、不写 artifact、不恢复 paused session |
| 56. Hook Subagent baseline | 已完成（read-only hook artifact review，不 install / eval / invoke） | `tests.test_hook_subagent`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `subagents.hook`、`prompts/hook.txt` 与 `review_hook_artifacts` tool，默认 agent 在 `debugger` 与 `timeline` 之间包含 `hook` 子智能体，workspace contract 将 `hook` 标记为 implemented；tool 只读取 hook artifacts JSON，输出 function / module hook inventory、source-logpoint、candidate 和 timeline event 摘要、blockers、warnings、review_required_items 和 side-effect policy，不安装 hook、不 evaluate JS、不触发目标 |
| 57. Rebuild Subagent split | 已完成（rebuild generation / review 从 delivery 拆出） | `tests.test_rebuild_subagent`、`tests.test_delivery_tools`、`tests.test_workspace_contract`、`tests.test_subagent_smoke`；新增 `subagents.rebuild`、`prompts/rebuild.txt` 与 `review_rebuild_artifacts` tool，默认 agent 在 `review` 与 `delivery` 之间包含 `rebuild` 子智能体；`delivery` 子智能体收窄为 `execute_local_delivery`；workspace contract 将 `rebuild` 标记为 implemented，planned-contract 子智能体清零 |
| 58. WorkspacePathResolver / opt-in dual-write plan baseline | 已完成（resolver-only，不物理迁移） | `tests.test_workspace_contract`；新增 `WorkspacePathResolver` 与 `WorkspacePathResolution`，支持 artifact key、legacy path、future path、virtual URI 解析；默认 write path 仍为 legacy canonical path，显式 `enable_dual_write=True` 只返回 legacy + future path 的 plan-only 写入列表，不创建目录、不移动 artifact、不改变 authoritative path |
| 59. Workspace opt-in actual dual-write writer baseline | 已完成（显式开启才双写，legacy 仍 authoritative） | `tests.test_workspace_contract`；Web / platform deterministic pipeline 新增 `enable_workspace_dual_write` 显式开关，开启后已登记 workspace artifact 会同时写 legacy canonical path 与 `artifact_root/workspace/<area>/...` future path，并输出 `workspace/workspace-dual-write-plan.json` 审计记录；默认不双写、不移动旧文件、不改变 manifest canonical path |
| 114. Workspace dual-write pilot result artifact baseline | 已完成（默认只读检查，显式写审计结果） | `tests.test_workspace_artifact_reader`、`tests.test_workspace_contract`、`tests.test_rebuild_subagent`；新增 `record_workspace_dual_write_pilot_result`，对照 pilot plan 与 `workspace-dual-write-plan.json` 检查 legacy / future 文件存在性和 sha256，一键识别 out-of-scope / high-risk observed writes；可显式写 `workspace/workspace-dual-write-pilot-result.json`，不启用 dual-write、不迁移路径、不改变 canonical path |
| 115. Scoped workspace dual-write writer baseline | 已完成（显式 scope gate，legacy 仍 authoritative） | `tests.test_workspace_contract`、`tests.test_workspace_artifact_reader`、`tests.test_console_script`、`tests.test_run_demo`、`tests.test_platform_pipeline`；`WorkspacePathResolver` / Web pipeline / platform pipeline / CLI 支持 `workspace_dual_write_artifact_keys`，只对审阅过的 artifact key 写 future path，out-of-scope artifact legacy-only 并记录 scope metadata；不默认双写、不迁移路径、不改变 canonical path |
| 60. GitHubReleaseExternalDeliveryProvider baseline | 已完成（dry-run 无副作用，apply 显式 GitHub REST 发布 JSON asset） | `tests.test_external_delivery_registry`、`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_doctor`；新增内置 `GitHubReleaseExternalDeliveryProvider`、`github-release` provider id 与 `gh-release` / `github-release-assets` alias；registry / doctor metadata-only 可见且不调用 factory；dry-run 不打开 socket；apply 模式创建 GitHub release 并上传 redacted JSON delivery package asset；metadata 不记录 token、request headers、response body 或 response headers；duplicate guard 仍在 provider factory 前执行；显式 release 复用已由 Step 61 补齐，asset 覆盖 / 删除、retry / backoff 和更复杂第三方 release provider 仍为后续 provider 演进 |
| 61. GitHub Release existing-release reuse baseline | 已完成（explicit opt-in，不自动复用） | `tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor`；`GitHubReleaseExternalDeliveryProvider` 新增 `reuse_existing_release`，默认 `False`；apply 模式 create release 失败后，只有显式开启时才 GET `/repos/{owner}/{repo}/releases/tags/{tag}` 复用已有 release 的 upload URL 并继续上传 JSON asset；metadata 增加 `release_created`、`existing_release_lookup_attempted`、`existing_release_lookup_succeeded`、`existing_release_reused`、`existing_release_status_code` 与 redacted existing release API URL；doctor capability metadata 暴露 `supports_existing_release_reuse=true`；同名 asset preflight 已由 Step 62 补齐，仍不覆盖 / 删除已有 asset，不实现 retry / backoff |
| 62. GitHub Release asset duplicate preflight baseline | 已完成（默认阻断同名 asset，不覆盖 / 删除） | `tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor`；`GitHubReleaseExternalDeliveryProvider` 默认在 release 可用后读取 `assets_url` 并检查 `asset_name` 是否已存在；同名 asset 默认在上传前 blocked，显式 `allow_existing_asset=true` 才允许继续尝试上传；metadata 记录 redacted assets URL、asset lookup status、existing asset count 与 conflict flags；不记录 response body / headers / request headers / token；仍不删除 / 覆盖 asset；显式 retry baseline 已由 Step 63 补齐 |
| 63. External delivery explicit retry policy baseline | 已完成（默认 0 retry，显式配置才重试） | `tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增 provider-neutral `ExternalDeliveryHttpRequestResult` 与 `_http_request_with_retries(...)`，内置 `webhook`、`presigned-object`、`github-release` provider 支持 `retry_attempts`、`retry_backoff_seconds`、`retry_status_codes`；默认仍只请求一次，dry-run 不联网；metadata 记录 secret-safe attempt count、retry count、status/error 摘要和 retry 配置，不记录 request headers、response headers、response body 或 token；doctor / registry capability metadata 暴露 `supports_explicit_retry=true` 与 `default_retry_attempts=0` |
| 78. Review approval ledger baseline | 已完成（approval-audit-only） | `tests.test_review_approval`、`tests.test_review_subagent`、`tests.test_workspace_contract`；新增 `ReviewApprovalLedgerWriter` 与 `record_review_approval` tool，显式记录人工 review decision 到 `review-approval-record.json` / append-only `review-approval-ledger.json`；默认 dry-run，apply 必须 reviewer + `approve_decision_record=true`，只写审批审计，不执行 delivery / rollback / materialization |
| 79. Delivery resume runner baseline | 已完成（review-gated single-transition runner） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；新增 `DeliveryResumeRunner` / `execute_delivery_resume`，dry-run 只计划，apply 必须匹配 review approval ledger 后才委托 transition executor 执行单个 `preflight_backend_manifest_recovery` / `apply_backend_manifest_recovery` / `commit_cross_run_transaction`；写 `delivery-resume-execution.json` 审计记录，不启动新 delivery、不 external delivery、不 physical rollback |
| 80. Delivery transaction lock provider contract baseline | 已完成（provider contract + local-file reference，不是真分布式 consensus） | `tests.test_delivery_lock_provider`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；新增 `DeliveryTransactionLockProvider` contract、`DeliveryTransactionLockProviderRegistry`、`LocalFileDeliveryTransactionLockProvider` 与 `reverse_deepagent.delivery_lock_providers` entry point group；delivery subagent 新增 `manage_delivery_transaction_lock_provider`，默认 provider 可 dry-run inspect/acquire/renew/release，apply 写 `delivery-distributed-transaction-lock.json` / `delivery-distributed-transaction-lock-operation.json`；不替换 `delivery-transaction-lock.json` gate，不 contact external service，不提供 cross-machine consensus |
| 81. Delivery resume workflow scheduler baseline | 已完成（review-gated local durable journal，不是 daemon / distributed workflow engine） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_workspace_contract`；新增 `DeliveryResumeWorkflowScheduler` / `execute_delivery_resume_workflow`，支持 `plan_workflow` / `execute_workflow` 与显式 `preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery`、`commit_cross_run_transaction` steps；apply 必须每个 pending step 匹配 review approval ledger；写 `delivery-resume-workflow.json` / append-only `delivery-resume-workflow-journal.json` 并跳过已 journal 完成 step；不启动新 delivery、不 external delivery、不 acquire/release distributed lock、不 broader physical rollback |
| 82. ExternalDeliveryProvider plugin package template | 已完成（optional package template，不改 core delivery） | `tests.test_external_delivery_provider_plugin_template`、`tests.test_external_delivery_registry`、`tests.test_doctor`；新增 `packages/reverse-deepagent-external-delivery-provider-template/`，声明 `reverse_deepagent.external_delivery_providers` entry point，提供 `template-external-delivery` registration / factory / README，证明 metadata-only 注册不调用 factory、不联网、不读取 credentials、不上传发布；默认 dry-run 只计划，apply blocked，需 integrator 替换 `deliver()` |
| 83. SQLite delivery transaction lock provider baseline | 已完成（local SQLite transactional store，不是真分布式 consensus） | `tests.test_delivery_lock_provider`、`tests.test_delivery_tools`、`tests.test_workspace_contract`、`tests.test_doctor`；新增 `SQLiteDeliveryTransactionLockProvider` 与 `sqlite-lock` / `db-lock` / `sqlite-transaction-lock` / `local-db-lock` provider registration；apply 写 `delivery-distributed-transaction-lock.sqlite3` 作为权威 store，并继续写 `delivery-distributed-transaction-lock.json` projection 与 `delivery-distributed-transaction-lock-operation.json` audit record；支持 acquire / renew / release、lease、fencing token；不联系外部服务，不提供 Redis / etcd / DB consensus；Step 85 已补显式 downstream fencing token gate |
| 84. Redis delivery transaction lock provider baseline | 已完成（external Redis lease provider，不是 Redlock quorum consensus） | `tests.test_delivery_lock_provider`、`tests.test_delivery_tools`、`tests.test_workspace_contract`、`tests.test_doctor`；新增 `RedisDeliveryTransactionLockProvider` 与 `redis-lock` / `redis` / `redis-lease-lock` / `external-redis-lock` provider registration；dry-run 不联网，apply / inspect 使用外部 Redis key 作为权威 lease store，并继续写本地 JSON projection / operation record；支持 acquire / renew / release、lease、fencing token；不替换 `delivery-transaction-lock.json` gate，不自动 lease renewal / stale takeover，不实现 Redlock quorum consensus；Step 85 已补显式 downstream fencing token gate |
| 85. Downstream fencing token gate baseline | 已完成（explicit expected-token side-effect gate，不是自动全局 fencing enforcement） | `tests.test_delivery_executors`、`tests.test_delivery_tools`；`LocalDeliveryExecutor` 新增 `expected_transaction_lock_fencing_token` / `transaction_lock_fencing_record_name`，默认读取 `delivery-distributed-transaction-lock.json` projection；apply-mode 本地复制、manifest mutation、recovery、commit、external delivery 以及 transition / resume / workflow / recovery / rollback wrappers 均可显式要求 fencing token 匹配且 lease 未过期，不匹配、缺失、malformed 或 stale record 会阻断 side effects；不自动 acquire provider lock、不自动 renew lease、不替代 Redlock / consensus |
| 86. Explicit lease renewal workflow step baseline | 已完成（review-gated renew step，不是 daemon / auto-renew loop） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`；`DeliveryResumeWorkflowScheduler` 新增 `renew_delivery_transaction_lock_provider` step action，apply 必须匹配 `resume_renew_delivery_transaction_lock_provider` approval ledger entry；step 调用配置的 `DeliveryTransactionLockProvider.renew_lock`，写 provider operation / projection 并把 provider id、fencing token、lease expiry 写入 workflow journal；tool 新增 `transaction_lock_provider_id` / `transaction_lock_provider_metadata_json` 透传；不 acquire/release lock、不自动后台续租、不 stale takeover |
| 87. Explicit lock provider lifecycle workflow steps baseline | 已完成（review-gated acquire / renew / release steps，不是 automatic lifecycle manager） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`；`DeliveryResumeWorkflowScheduler` 统一支持 `acquire_delivery_transaction_lock_provider` / `renew_delivery_transaction_lock_provider` / `release_delivery_transaction_lock_provider`，分别映射 provider `acquire_lock` / `renew_lock` / `release_lock`；apply 必须匹配对应 `resume_acquire_*` / `resume_renew_*` / `resume_release_*` approval ledger entry；成功 step 把 provider id、fencing token、lease expiry 与 side-effect policy 写入 workflow journal；不自动 acquire-before-workflow、不自动 release-after-workflow、不 daemon / polling / stale takeover |
| 88. Workflow fencing token propagation baseline | 已完成（workflow-local propagation，不是 global automatic fencing） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`、`tests.test_workspace_contract`、`tests.test_doctor`；`DeliveryResumeWorkflowScheduler` 会把同一次 workflow execution 内成功 acquire / renew lock-provider step 返回的 fencing token 传播给后续 runner step 的 `expected_transaction_lock_fencing_token`；显式 config expected token 优先，release step 清空传播 token；step result 与 workflow journal 记录 `fencing_token_propagation`；Step 89 已补 resume-of-resume journal replay；不自动 acquire / renew / release、不 daemon / stale takeover |
| 89. Journal-state fencing replay baseline | 已完成（resume-of-resume conservative replay，不是 arbitrary side-effect replay） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`、`tests.test_workspace_contract`、`tests.test_doctor`；`DeliveryResumeWorkflowScheduler` 会从既有 `delivery-resume-workflow-journal.json` 的同 transaction 成功 acquire / renew / release 条目恢复最小 fencing state；跳过已完成 lock-provider step 时记录 `fencing_token_replay`；未过期 acquire / renew token 可继续传给后续 runner step，journaled release 清空 token，stale / malformed lease evidence 不传播；不重放 provider side effects、不 restore manifest、不 external delivery、不 daemon / stale takeover |
| 90. Skipped-step journal context replay baseline | 已完成（read-only context replay，不是 side-effect replay） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`、`tests.test_workspace_contract`、`tests.test_doctor`；`DeliveryResumeWorkflowScheduler` 为 skipped completed step 增加 `journal_replay` 摘要，保守带回同 transaction journal entry 的 entry status、runner status、transition status、lock evidence 与 side-effect policy；completed action 识别按当前 transaction id 过滤，避免其他 transaction journal 误跳过；不重放 runner payload、不 restore manifest、不 external delivery、不自动 rollback-vs-commit |
| 91. Lease renewal planning baseline | 已完成（plan-only，不是 daemon / auto-renew loop） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`、`tests.test_workspace_contract`、`tests.test_doctor`；`DeliveryResumeWorkflowScheduler` 生成 `lease_renewal_plan`，从 `delivery-distributed-transaction-lock.json` provider projection 和同 transaction workflow journal lease evidence 判断已有 fencing token 的 lease 是否过期或进入 warning window；默认 workflow planning 可前置 `renew_delivery_transaction_lock_provider`，tool 暴露 `lease_renewal_warning_seconds` 调整窗口；规划不联系 provider、不写 lock operation artifact、不自动 renew、不启动 daemon，执行仍需 `resume_renew_delivery_transaction_lock_provider` approval |
| 92. Lock lifecycle planning baseline | 已完成（plan-only，不是 automatic lifecycle manager） | `tests.test_delivery_resume`、`tests.test_delivery_tools`、`tests.test_delivery_lock_provider`、`tests.test_workspace_contract`、`tests.test_doctor`；`DeliveryResumeWorkflowScheduler` 生成 `lock_lifecycle_plan`，根据 provider projection 与同 transaction workflow journal lock evidence 给默认 workflow 添加 review-gated acquire / release 建议；缺少 provider lock evidence 的 recovery workflow 可前置 `acquire_delivery_transaction_lock_provider`，terminal transaction 仍有 provider lock evidence 时可规划 `release_delivery_transaction_lock_provider`；显式 `step_actions` 不被改写；规划不联系 provider、不写 operation artifact、不自动 acquire / release、不 stale takeover、不启动 daemon |
| 93. Workflow readiness plan baseline | 已完成（read-only readiness，不是 workflow engine） | `tests.test_delivery_resume`；`DeliveryResumeWorkflowScheduler` 生成 `workflow_readiness_plan`，聚合 planned steps、approval gaps、checks、blocking reasons、`lock_lifecycle_plan`、`lease_renewal_plan` 与 journal replay context，输出 `ready_for_review` / `ready_to_execute` / `blocked` / `no_steps` 和 next review actions；不调用 provider、不写 operation artifact、不自动执行、不启动 daemon |
| 94. Workflow step dependency context baseline | 已完成（read-only dependency matrix，不替代 runtime gate） | `tests.test_delivery_resume`；`workflow_readiness_plan.step_dependency_contexts` 逐步输出 approval、serial predecessor、journal replay、provider lock、fencing、recovery preflight 与 runtime gate review metadata，区分 journal 已完成、计划内前序可提供和 apply-time 仍需重验；不执行 step、不写 artifact、不绕过 digest / rollback / lock / fencing checks |
| 95. Workflow runtime-gate evidence projection baseline | 已完成（read-only artifact projection，不替代 apply-time checks） | `tests.test_delivery_resume`；`workflow_readiness_plan.runtime_gate_evidence_projection` 只读投影 delivery root 中的 transaction journal、rollback checkpoint、recovery preflight、provider lock projection、local transaction lock、terminal commit record 与 backend manifest，标记 observed / missing / malformed / stale / transaction mismatch，并把 per-step `runtime_gate_evidence` 挂到 dependency context；不联系 provider、不写 artifact、不宣称 gate 已通过 |
| 96. Roadmap / future-work status cleanup | 已完成（docs-only 状态纠偏） | `ROADMAP.md` 改为 Done / Active / Deferred 状态化路线图；`docs/runtime/browser-provider-architecture.md` 将旧 future-work 长句拆成 completed hardening、active capability-gated work 与 explicitly deferred automation；不改代码、不改变 runtime 行为 |

## 阶段执行记录与剩余顺序

当前状态：Phase 0-113 已完成，`remote-cdp` smoke 路径已接入，Playwright system Chrome smoke、CloakBrowser fixture smoke、Playwright breakpoint paused/callframe smoke、显式 evaluateOnCallFrame baseline、callframe evaluation policy baseline、mutation audit baseline、page-level mutation audit baseline、MutationObserver timeline baseline、debugger step-control baseline、paused-session continuation preflight、durable paused-session snapshot inspect-only baseline、single-run debugger timeline baseline、target-function wrapper baseline、source-level logpoint baseline、source map / bundle offset remap baseline、source-map bias / sourceRoot / indexed section remap baseline、source-map names / URL equivalence / nested indexed-section metadata baseline、module export hook baseline、module discovery baseline、runtime module cache / registry introspection baseline、custom runtime / module federation function-path candidate baseline、read-only async chunk graph / loader metadata baseline、closure-scope function discovery baseline、native-web recon flow timeline baseline、flow timeline correlation hints、conservative correlation groups、group verification readiness、manual stitch candidates、review-gated stitch proposals、pending stitch proposal evidence promotion / review gate blocking、reviewer-approved stitched-flow materialization baseline、explicit flow timeline continuation baseline、auto-stitch dry-run scoring baseline、auto-stitch policy decision gate baseline、auto-stitch materialization plan baseline、review-approved auto-stitch materializer skeleton、materialization audit / rollback writer baseline、auto-stitch conflict resolver baseline、materialization transaction log baseline、rollback execution dry-run / explicit-review-only baseline、post-rollback review gate recompute baseline、physical rollback dry-run diff baseline、explicit-review-only physical rollback mutation baseline、post-physical-rollback review gate rerun baseline、standard review gate replacement baseline、post-standard-review-gate-replacement delivery guard rerun baseline、final delivery package after delivery guard rerun baseline、final delivery transaction commit record baseline、local delivery executor contract baseline、local delivery manifest revision baseline、backend artifact manifest mutation policy baseline、backend manifest in-place mutation preflight baseline、explicit-review-only backend manifest in-place mutation executor baseline、backend manifest cross-run recovery preflight baseline、backend manifest cross-run transaction commit baseline、backend manifest recovery apply baseline、ExternalDeliveryProvider contract baseline、ExternalDeliveryProvider registry / entry-point discovery baseline、ExternalDeliveryProvider doctor / metadata CLI baseline、external delivery idempotency / duplicate guard baseline、GitHub Release external delivery provider baseline、GitHub Release existing-release reuse baseline、GitHub Release asset duplicate preflight baseline、External delivery explicit retry policy baseline、external delivery idempotency ledger baseline、delivery transaction transition executor baseline、GitHub Release asset overwrite/delete preflight plan baseline、GitHub Release explicit asset delete + replacement upload baseline、Provider-specific retry / rate-limit metadata baseline、Delivery transaction recovery workflow executor baseline、Delivery transaction idempotency guard baseline、Delivery cross-run rollback state machine baseline、Delivery rollback state artifact writer baseline、Delivery rollback executor dry-run / preflight baseline、Delivery rollback apply executor explicit-review-only baseline、Delivery transaction lock / resume preflight baseline、Delivery transaction lock release / stale review baseline、Durable delivery resume planner baseline、Review approval ledger baseline、Delivery resume runner baseline、Delivery transaction lock provider contract baseline、Delivery resume workflow scheduler baseline、ExternalDeliveryProvider plugin package template、SQLite delivery transaction lock provider baseline、Redis delivery transaction lock provider baseline、Downstream fencing token gate baseline、Explicit lease renewal workflow step baseline、Explicit lock provider lifecycle workflow steps baseline、Workflow fencing token propagation baseline、Journal-state fencing replay baseline、Skipped-step journal context replay baseline、Lease renewal planning baseline、Lock lifecycle planning baseline、Workflow readiness plan baseline、Workflow step dependency context baseline、Workflow runtime-gate evidence projection baseline、Roadmap / future-work status cleanup、Runtime context stability diff baseline、Runtime-context-driven rebuild review hints baseline、Protected-flow triage hook planner baseline、Strategy evidence scoring baseline、BrowserProvider compatibility rule catalog baseline、Functional external BrowserProvider fixture plugin baseline、Workspace artifact reader resolver baseline、Review helper artifact-ref resolver adoption baseline、Delivery artifact-list resolver adoption baseline、Workspace resolver compatibility metrics baseline、Workspace consumer adoption audit baseline、Rebuild generation artifact-ref input adoption baseline、Delivery source path compatibility audit baseline、Workspace migration readiness report baseline、Limited workspace dual-write pilot plan baseline，以及 retained paused-session registry baseline 均已验证，MCP alias deprecation warning 已接入，最终 code review 已完成并修复 module-hook 路由、module hook path quoting 和 page-mutation global snapshot 副作用风险；MCP 物理拆包前置步骤已完成：RuntimeBackendRegistry 支持 `reverse_deepagent.runtime_backends` entry-point discovery，加载外部 backend registration 时不调用 backend factory；`legacy-mcp` registration / factory / alias warning 已从 coordinator 内联逻辑挪到 `reverse_deepagent.runtime.legacy_mcp`，并支持 `build_default_runtime_registry(include_legacy_mcp=False)` 构建不带 MCP backend 的 clean registry；`packages/reverse-deepagent-legacy-mcp/` optional plugin package 已拥有 legacy MCP registration / factory、config 和 stdio bridge 实现，core 侧 `reverse_deepagent.runtime.legacy_mcp` 只保留兼容 shim、默认命令常量、alias warning、doctor 代理和 install guidance，不再内置 legacy MCP factory fallback 或 stdio MCP transport；默认 registry 会先加载外部 entry points，若未安装 optional package，`legacy-mcp` / `mcp` 会返回结构化安装建议且不会先启动受管 Chrome。DeepAgents workspace contract indexed-only baseline 已落地，当前输出 `workspace/workspace-contract.json`，覆盖虚拟文件夹、子智能体角色、middleware chain 和现有扁平 artifact route。BrowserProvider registry / smoke matrix / lifecycle baseline 已落地，doctor 可输出 registry-driven metadata-only provider matrix，真实启动仍需显式 `--launch-browser-smoke`。RuntimeBackend doctor / metadata CLI baseline 已落地，`reverse-agent-doctor --runtime-backends` 可输出 side-effect-free runtime backend matrix，不调用 backend factory，不启动 Chrome / MCP / 平台工具。DeepAgents workspace manifest-only alias baseline 已落地，backend artifact manifest 会为已登记 workspace artifact entry 增加 `metadata.workspace_alias`，暴露 canonical flat path、foldered future path 与 virtual URI，同时保持扁平路径 canonical。Delivery transaction state machine skeleton 已落地，`DeliveryExecutionResult.to_dict()` 会内嵌只读 `transaction_state`，把 delivery result / journal / recovery / commit / external-delivery artifact 归一成 coarse state、completed states、flags、evidence paths、blockers 和 next-action hints。Delivery transaction inspector / doctor baseline 已落地，`reverse-agent-doctor --delivery-transaction-root` 可 side-effect-free 读取 delivery root 标准 transaction artifacts，输出 state_snapshot、transition_plan、artifact load status、missing optional artifacts、load_errors 和 read-only side-effect policy。Debugger Subagent baseline 已落地，默认 agent 在 `timeline` 前包含 `debugger` 子智能体，可 read-only 审计 debugger-session、debugger-timeline、debugger-paused、callframes、continuation preflight、callframe evaluations、mutation audit 和 debugger actions，但不发送 CDP 命令、不 resume / step / evaluate、不写 artifact。Hook Subagent baseline 已落地，默认 agent 在 `debugger` 与 `timeline` 之间包含 `hook` 子智能体，可 read-only 审计 function / module hook inventory、hook timeline、source-logpoint 和 hook candidates，但不安装 hook、不 evaluate JavaScript、不触发目标函数、不写 artifact。Rebuild Subagent split 已落地，默认 agent 在 `review` 与 `delivery` 之间包含 `rebuild` 子智能体，可生成 rebuild bundle 并 read-only 复核 RebuildResult / rebuild-plan；`delivery` 子智能体只保留 local / external delivery transaction 与显式 transition execution，不再混入 rebuild generation。Review Subagent baseline 已落地，默认 agent 包含 `review` 子智能体，可 read-only 评估 RebuildResult / EvidencePromotionResult 的 review gate、review hints 和 evidence review requirements，并可显式记录 review approval ledger 审计 artifact，但不执行 delivery。Review approval ledger baseline 已落地，`review` 子智能体可通过显式 `record_review_approval` 写 `review-approval-record.json` / `review-approval-ledger.json` 审计记录，默认 dry-run，apply 必须包含 reviewer 与 `approve_decision_record=true`，且不 materialize、不 rollback、不交付。Delivery resume runner baseline 已落地，`delivery` 子智能体可通过显式 `execute_delivery_resume` 在匹配 approval ledger 后执行单个 recovery / commit transition 并写 `delivery-resume-execution.json`，但不启动新 delivery、不 external delivery、不 physical rollback。Timeline Subagent baseline 已落地，默认 agent 在 `review` 前包含 `timeline` 子智能体，可 read-only 审计 flow timeline、correlation groups、stitch proposals 与 auto-stitch gate，但不 materialize、不记录 approval、不执行 rollback / delivery。planned-contract 子智能体已清零；后续仍需生产级第三方 BrowserProvider plugin implementation、真实第三方 provider capability rules 的后续定制、跨进程 live CDP paused execution continuation、执行式 custom loader traversal / async chunk loading / 深层 module federation 分析、任意闭包内部函数 automatic wrapper hook、JS heap 级细粒度 mutation audit / object graph diff、full source-map consumer semantics / bundler-specific symbol scoping beyond the current credentialless source-map URL fetch metadata baseline、DeepAgents 虚拟文件夹物理迁移 / review-gated follow-through on limited dual-write pilot plan output，以及更完整的自动全链路跨请求 timeline conflict resolver / 真实第三方 external delivery provider implementation beyond template / advanced adaptive provider retry policy / broader physical state machine beyond local manifest rollback apply / additional external distributed lock providers beyond Redis / local-file / SQLite baselines / broader durable resume scheduler beyond workflow step dependency context baseline / daemon / distributed orchestration / 无需审批 automatic materializer / automatic lease-renewal loop / automatic lock lifecycle manager。Android / iOS / 小程序完整运行链路继续搁置，只保留 minimal probe / artifact export baseline。Step 5.1 到 Step 74 保留为已执行阶段记录，便于 review 和回溯。





### Step 96：Roadmap / future-work status cleanup

- `ROADMAP.md`：从早期版本化 wish list 改成状态化路线图，分为 current direction、done / baseline shipped、active non-mobile follow-ups、explicitly deferred 与 validation posture。
- `docs/runtime/browser-provider-architecture.md`：将旧 future-work 超长句拆成 completed hardening、active capability-gated future work 与 explicitly deferred automation，避免把 Step 88-95 已完成 baseline 继续写成 future work。
- Boundary：这是 docs-only 状态纠偏，不改变 runtime / provider / delivery 行为，不新增测试入口，不移动 workspace artifact，不触碰 Android / iOS / 小程序完整运行链路。
- 验证：`git diff --check`，人工检查文档没有旧 `mcp` 默认主线、旧分支名或移动端完整链路被误提到 active track。

### Step 95：Workflow runtime-gate evidence projection baseline

- `workflow_readiness_plan.runtime_gate_evidence_projection`：只读读取 delivery root 中的 `delivery-transaction-journal.json`、`backend-artifact-manifest.rollback.json`、`backend-artifact-manifest-recovery-preflight.json`、`delivery-distributed-transaction-lock.json`、`delivery-transaction-lock.json`、`backend-artifact-manifest-transaction-commit.json` 与当前 backend manifest 路径。
- Artifact status：每个 artifact 输出 `observed` / `missing` / `malformed` / `stale`、路径、SHA-256 digest、事务匹配状态、lease stale 状态与 non-secret 摘要；provider lock / local lock 只暴露 token / owner / resume token 是否存在，不回传原始 token。
- Step context：每个 `step_dependency_contexts[*].runtime_gate_evidence` 只引用与该 step 有关的 artifact refs，并汇总 observed / missing / malformed / stale / transaction mismatch artifact keys；`dependency_summary` 增加 runtime-gate evidence 缺失、损坏、过期与 transaction mismatch step counts。
- Boundary：这是 read-only artifact projection；artifact observed 不等于 runtime gate passed，apply-time 仍由 `DeliveryResumeRunner` / `DeliveryTransactionTransitionExecutor` / `LocalDeliveryExecutor` 重新执行 digest、rollback checkpoint、transaction lock、lease 与 fencing-token checks；planning 不联系 provider、不写 artifact、不启动 daemon、不自动执行。
- 测试：覆盖正常 recoverable transaction 的 observed projection、malformed recovery preflight JSON、stale provider lock lease、dry-run 不写 workflow / provider operation artifact，以及 token presence-only redaction。

### Step 94：Workflow step dependency context baseline

- `workflow_readiness_plan.step_dependency_contexts`：为每个 planned step 输出 order、action、executor、readiness、approval、serial predecessor、journal replay、provider lock、fencing、recovery preflight 与 runtime gate review metadata。
- Conservative evidence model：明确区分 `journal_replay_available`、`planned_predecessor_*` 与 `runtime_*_review_required`；计划内 acquire / renew / preflight 只能作为后续 step 的候选前序证据，release 会清空后续 planned lock / fencing evidence，且任何候选证据都不能冒充 apply-time gate 已通过。
- Dependency summary：输出 approval missing、journal replay、provider-lock review、fencing review、recovery-preflight review 与 runtime-gate review 的 step counts，方便 delivery / review subagent 快速定位阻断点。
- Boundary：这是 read-only dependency matrix；不调用 provider、不写 workflow / lock artifact、不执行 step、不重放 side effect、不绕过 LocalDeliveryExecutor 的 digest、rollback checkpoint、transaction lock 或 fencing-token checks、不启动 daemon。
- 测试：覆盖 default acquire planning 的 predecessor lock evidence、审批齐全 acquire / release lifecycle 的 fencing predecessor metadata、release 后 planned lock / fencing evidence 清空，以及 resume-of-resume skipped preflight 的 journal replay / recovery-preflight dependency metadata。


### Step 93：Workflow readiness plan baseline

- `DeliveryResumeWorkflowScheduler`：在 `plan_workflow` / `execute_workflow` 中生成只读 `workflow_readiness_plan`，聚合 planned steps、pending / completed step counts、approval summary、checks、blocking reasons、`lock_lifecycle_plan`、`lease_renewal_plan` 与 existing workflow journal summary。
- Readiness status：输出 `ready_for_review`、`ready_to_execute`、`blocked` 或 `no_steps`；同时列出 required / missing / matched approval actions、lock provider action 需求、fencing review 需求、journal replay context 和 next review actions，方便 review / delivery subagent 消费。
- Boundary：这是 `dry_run_plan_only=true` 的 review metadata baseline；不调用 provider、不写 `delivery-distributed-transaction-lock-operation.json`、不执行 workflow step、不自动 acquire / renew / release、不启动 daemon、不替代 approval ledger、不自动 rollback-vs-commit。
- 测试：覆盖缺失 provider lock 时 ready-for-review 与 approval gaps、apply 缺审批 blocked readiness、审批齐全 apply 的 pre-execution ready-to-execute readiness。


### Step 92：Lock lifecycle planning baseline

- `DeliveryResumeWorkflowScheduler`：在 `plan_workflow` / default workflow planning 中生成 `lock_lifecycle_plan`，读取 provider projection 与同 transaction workflow journal acquire / renew / release evidence，输出 source、provider、owner、fencing token presence、lease stale、active evidence 与 recommended step actions。
- Acquire recommendation：当默认 recovery / commit workflow 有 runner step，但没有任何 provider lock evidence 时，可前置 `acquire_delivery_transaction_lock_provider`；显式 `step_actions_json` / `step_actions` 不被隐式改写。
- Release recommendation：当 resume plan 已处于 terminal transaction，且 provider projection / journal 仍显示 lock evidence 时，只规划 `release_delivery_transaction_lock_provider`，并允许 terminal release-only workflow 通过 scheduler checks。
- Boundary：这是 `dry_run_plan_only=true` 的 lifecycle planning baseline；规划不调用 provider、不写 `delivery-distributed-transaction-lock-operation.json`、不自动 acquire / release、不后台续租、不 stale takeover、不启动 daemon。真正 acquire / release 仍必须通过 reviewed workflow step 与 `resume_acquire_delivery_transaction_lock_provider` / `resume_release_delivery_transaction_lock_provider` approval。
- 测试：覆盖缺失 provider lock 时 acquire planning、terminal provider lock 时 release planning、显式 step_actions 不被 lifecycle plan 改写，以及 dry-run 不写 provider operation。

### Step 91：Lease renewal planning baseline

- `DeliveryResumeWorkflowScheduler`：在 `plan_workflow` / default workflow planning 中生成 `lease_renewal_plan`，读取 `delivery-distributed-transaction-lock.json` projection，并在 projection 缺失可用 lease 时保守回看同 transaction workflow journal 的 acquire / renew / release lease evidence。
- Renewal recommendation：当已有 fencing token 的 lease 已过期或进入 `lease_renewal_warning_seconds` warning window 时，默认 workflow planning 可把 `renew_delivery_transaction_lock_provider` 前置到 planned steps；显式 `step_actions_json` 不被隐式改写。
- Tool surface：`execute_delivery_resume_workflow` 暴露 `lease_renewal_warning_seconds`，默认 warning window 为 `transaction_lock_lease_seconds // 3` 且不少于 1 秒。
- Boundary：这是 `dry_run_plan_only=true` 的 planning baseline；规划不调用 provider、不写 `delivery-distributed-transaction-lock-operation.json`、不后台续租、不启动 daemon、不自动 acquire / release、不 stale takeover。真正 renewal 仍必须通过 reviewed `renew_delivery_transaction_lock_provider` step 与 `resume_renew_delivery_transaction_lock_provider` approval。
- 测试：scheduler 直接测试覆盖 expired / healthy projection；tool 测试覆盖 `lease_renewal_warning_seconds` 透传与 dry-run 不写 provider operation。

### Step 67：GitHub Release explicit asset delete + replacement upload baseline

- `GitHubReleaseExternalDeliveryProvider`：在同名 asset lookup 命中后，只有显式配置 `approve_existing_asset_delete=true` 与 `approve_replacement_upload=true`，且可选 `expected_existing_asset_id` 与 lookup 到的 asset id 匹配时，才会发送 DELETE 删除旧 asset。
- Replacement upload：DELETE 成功后才继续走原 upload URL 上传 replacement JSON asset；DELETE 失败、asset id mismatch、缺失 delete URL 或审批不足时均阻断，不上传 replacement。
- Metadata / ledger：external-delivery-result metadata 记录 delete approval、identity match、delete attempt/status、delete performed、overwrite performed、replacement upload attempt 和 partial-failure plan；idempotency ledger 继续归一 delete / upload attempt summary，仍不记录 token、headers、response body 或 URL query secret。
- Registry / doctor：`github-release` capability metadata 现在标记 `supports_existing_asset_overwrite=true`、`supports_existing_asset_delete=true`，并保留 `existing_asset_overwrite_requires_explicit_approval=true`。
- Boundary：这是显式审批 baseline，不自动覆盖同名 asset，不绕过 duplicate guard，不处理复杂 adaptive retry governor / GitHub secondary rate-limit 专用策略；cross-run rollback state machine beyond recovery workflow executor baseline 仍是后续工作。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor` 定向 70 项通过。


### Step 80：Delivery transaction lock provider contract baseline

- Provider contract：新增 `delivery.lock_provider`，提供 `DeliveryTransactionLockProvider`、`DeliveryTransactionLockProviderConfig`、`DeliveryTransactionLockOperation`、`DeliveryTransactionLockProviderRegistry` 和 `reverse_deepagent.delivery_lock_providers` entry point group。
- Local reference provider：默认 `local-file-lock`，alias 为 `filesystem-lock` / `local-distributed-lock`，支持 `inspect_lock`、`acquire_lock`、`renew_lock`、`release_lock`，apply 写 `delivery-distributed-transaction-lock.json` 与 `delivery-distributed-transaction-lock-operation.json`。
- Tool / subagent：delivery subagent 新增 `manage_delivery_transaction_lock_provider`，位于 `execute_delivery_resume` 后，作为 provider contract 操作入口。
- Workspace：新增 `workspace/delivery-distributed-transaction-lock.json` 与 `workspace/delivery-distributed-transaction-lock-operation.json` -> `/workspace/delivery/` routes。
- Boundary：这是 provider seam + local filesystem reference baseline，不替换现有 `delivery-transaction-lock.json` LocalDeliveryExecutor gate，不联系 Redis / etcd / DB / object storage，不提供跨机器 consensus，不执行 delivery / external delivery / manifest mutation / transaction commit，也不自动 stale takeover。
- 测试：`tests.test_delivery_lock_provider` 覆盖 registry metadata、dry-run、acquire / renew / blocked acquire / approved release 和 tool；`tests.test_delivery_tools` 覆盖 subagent tool 顺序；`tests.test_workspace_contract` 覆盖新 route。

### Step 81：Delivery resume workflow scheduler baseline

- Scheduler：新增 `delivery.resume_scheduler`，提供 `DeliveryResumeWorkflowScheduler`、`DeliveryResumeWorkflowSchedulerConfig`、`DeliveryResumeWorkflowExecution` 与 supported action / step action 常量。
- Workflow：支持 `plan_workflow` 与 `execute_workflow`；step action 覆盖 `preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery`、`commit_cross_run_transaction`，内部逐步委托 `DeliveryResumeRunner`，沿用既有 transition / digest / journal / lock / idempotency checks。
- Review gate：apply 模式要求每个 pending step 在 `review-approval-ledger.json` 中有匹配审批；已在 workflow journal 中完成的 step 会被标记为 `skipped_completed`，用于 resume-of-resume baseline。
- Artifact / workspace：成功 apply 写 `delivery-resume-workflow.json` 与 append-only `delivery-resume-workflow-journal.json`；workspace contract 新增 `workspace/delivery-resume-workflow.json` 与 `workspace/delivery-resume-workflow-journal.json` -> `/workspace/delivery/` routes。
- Tool / subagent：delivery subagent 新增 `execute_delivery_resume_workflow`，位于 `execute_delivery_resume` 与 `manage_delivery_transaction_lock_provider` 之间。
- Boundary：这是本地 delivery root 上的 review-gated durable workflow journal baseline，不是后台 timer / daemon，不是分布式 workflow engine，不启动新 delivery，不 external delivery，不 acquire/release distributed lock，不自动选择 rollback-vs-commit，不执行 broader physical rollback。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_resume` 覆盖 dry-run 规划、缺少 step approval 阻断、多 step recovery apply、resume-of-resume 跳过已完成 step 和 tool；`tests.test_delivery_tools` 覆盖 subagent tool 顺序；`tests.test_workspace_contract` 覆盖新 route。

### Step 82：ExternalDeliveryProvider plugin package template

- Optional package template：新增 `packages/reverse-deepagent-external-delivery-provider-template/`，作为 S3 / OSS / GCS / GitLab Release / 内部发布系统 provider 的 copy-and-replace 起点。
- Entry point：声明 `reverse_deepagent.external_delivery_providers` entry point，`template-external-delivery = reverse_deepagent_external_delivery_provider_template:external_delivery_provider_registration`。
- Contract：`external_delivery_provider_registration()` 返回 `ExternalDeliveryProviderRegistration`，metadata-only 注册不调用 factory、不打开 socket、不读取 credentials、不上传、不发布；capability metadata 保持 non-secret。
- Template provider：`TemplateExternalDeliveryProvider.deliver()` 默认不发布；dry-run 对有效 local delivery package 返回 `planned`，apply 返回 `blocked`，并提示替换 `deliver()` 后再投入生产。
- Boundary：这是第三方 external delivery provider 的模板和侧效应边界基线，不是新的真实 S3 / OSS / GCS / GitLab provider，不实现 advanced adaptive retry，也不绕过 core duplicate guard / idempotency ledger / review gate。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_external_delivery_provider_plugin_template` 覆盖 pyproject entry point、dependency、metadata-only registration、factory 显式调用、dry-run plan、apply block 和不发布边界；`tests.test_external_delivery_registry` / `tests.test_doctor` 保持 registry / doctor metadata-only 行为。

### Step 83：SQLite delivery transaction lock provider baseline

- Provider：新增 `SQLiteDeliveryTransactionLockProvider`，默认 DB 文件为 `delivery-distributed-transaction-lock.sqlite3`。
- Registry：默认 lock provider registry 新增 `sqlite-lock`，aliases 为 `db-lock` / `sqlite-transaction-lock` / `local-db-lock`。
- Transactional store：apply acquire / renew 通过 SQLite `BEGIN IMMEDIATE` 更新 `delivery_transaction_locks` row，并继续写 `delivery-distributed-transaction-lock.json` projection 和 `delivery-distributed-transaction-lock-operation.json` audit record。
- Semantics：复用既有 lock checks，支持 expected owner、expected fencing token、release approval、stale takeover gate、lease 与 fencing token。
- Boundary：这是 local SQLite transactional baseline；不联系 Redis / etcd / Postgres / MySQL，不提供跨机器 consensus，不自动 lease renewal，也不替换现有 `delivery-transaction-lock.json` LocalDeliveryExecutor gate；Step 85 已补显式 expected-token downstream fencing gate，但不自动全局 enforce。
- 测试：`tests.test_delivery_lock_provider` 覆盖 registry metadata、SQLite acquire / renew / release 和 tool alias；`tests.test_delivery_tools` / `tests.test_workspace_contract` / `tests.test_doctor` 作为集成回归范围。

### Step 84：Redis delivery transaction lock provider baseline

- Provider：新增 `RedisDeliveryTransactionLockProvider`，Redis key 默认为 `reverse-deepagent:delivery:distributed-transaction-lock`，也可通过 metadata `redis_lock_key` 覆盖。
- Registry：默认 lock provider registry 新增 `redis-lock`，aliases 为 `redis` / `redis-lease-lock` / `external-redis-lock`；metadata-only listing 不创建 client、不打开 socket、不读取 credentials。
- External store：dry-run 不联网；非 dry-run provider operation 需要注入 Redis client 或提供 `redis_url`，读取 Redis key 作为权威 lock store；apply acquire 使用 `SET NX EX`，renew / release 优先使用 Lua compare-set / compare-delete，测试中 fake client 覆盖无 Lua fallback。
- Projection：成功 acquire / renew 继续写 `delivery-distributed-transaction-lock.json` projection；成功 release 删除 projection；成功 inspect/acquire/renew/release 写 `delivery-distributed-transaction-lock-operation.json` audit record。
- Safety：operation metadata 会 redact `redis_url` / URL-like / secret-like 字段；side-effect policy 明确 `external_service_contacted`，dry-run 固定不触达外部服务。
- Boundary：这是 external Redis lease baseline；不实现 Redlock quorum consensus，不自动 lease renewal，不自动 stale takeover，不替换现有 `delivery-transaction-lock.json` gate；Step 85 已补显式 expected-token downstream fencing gate，但不自动全局 enforce。
- 测试：`tests.test_delivery_lock_provider` 覆盖 registry metadata、dry-run read-only、Redis acquire / renew / release、缺 redis_url 阻断、URL redaction 和 tool alias；`tests.test_delivery_tools` / `tests.test_workspace_contract` / `tests.test_doctor` 作为集成回归范围。


### Step 85：Downstream fencing token gate baseline

- Executor：`DeliveryExecutorConfig` 新增 `expected_transaction_lock_fencing_token` 与 `transaction_lock_fencing_record_name`，默认读取 `delivery-distributed-transaction-lock.json` provider projection。
- Gate：`require_transaction_lock=true` 且显式传入 expected token 时，`LocalDeliveryExecutor` 会校验 projection 存在、JSON 合法、`fencing_token` 匹配且 `lease_expires_at` 未过期；失败时阻断 apply-mode side effects，不写 receipt / journal，不复制 artifact，不 mutate manifest，不 recovery / commit / external delivery。
- Wrappers：`execute_local_delivery`、`execute_delivery_transition`、`execute_delivery_resume`、`execute_delivery_resume_workflow`、`execute_delivery_recovery`、`execute_delivery_rollback` 均透传 expected fencing token。
- Boundary：这是显式 expected-token side-effect gate，不自动 acquire / renew provider lock，不实现 Redlock / consensus，不代表所有调用方自动启用 fencing。
- 测试：`tests.test_delivery_executors` 覆盖 token match allow 与 mismatch block；`tests.test_delivery_tools` 作为工具兼容回归范围。

### Step 86：Explicit lease renewal workflow step baseline

- Scheduler：`DeliveryResumeWorkflowScheduler` 新增 `renew_delivery_transaction_lock_provider` step action，并把成功状态 `renewed` 纳入 workflow success statuses。
- Review gate：apply 模式必须在 `review-approval-ledger.json` 中匹配 `resume_renew_delivery_transaction_lock_provider`，否则不会调用 provider，也不会写 lock operation / workflow journal。
- Provider renew：续租 step 调用配置的 `DeliveryTransactionLockProvider.renew_lock`，透传 owner、lease seconds、expected fencing token、workflow metadata 和 provider-specific metadata。
- Tool：`execute_delivery_resume_workflow` 新增 `transaction_lock_provider_id` 与 `transaction_lock_provider_metadata_json`，用于显式选择 local-file / SQLite / Redis / plugin provider，并传入类似 Redis lock key 这类 provider 配置。
- Journal：成功续租会把 `lock_status`、`lock_provider_id`、`lock_fencing_token`、`lock_lease_expires_at` 与 lock side-effect policy 写入 append-only `delivery-resume-workflow-journal.json`。
- Boundary：这是 review-gated explicit renewal step，不是后台 daemon，不是 timer / polling loop，不自动 acquire / release lock，不 stale takeover，不实现 Redlock quorum consensus，不替代 downstream fencing-token gate。
- 测试：`tests.test_delivery_resume` 覆盖 dry-run 只规划不写 provider、缺审批阻断、审批后 renew 写 journal 和 tool provider metadata 透传；`tests.test_delivery_tools` / `tests.test_delivery_lock_provider` 作为集成回归范围。

### Step 87：Explicit lock provider lifecycle workflow steps baseline

- Scheduler：`DeliveryResumeWorkflowScheduler` 将 lock provider workflow step 抽成统一映射，支持 `acquire_delivery_transaction_lock_provider`、`renew_delivery_transaction_lock_provider` 与 `release_delivery_transaction_lock_provider`。
- Provider actions：三种 step 分别调用 `DeliveryTransactionLockProvider` 的 `acquire_lock`、`renew_lock`、`release_lock`，成功状态分别为 `acquired`、`renewed`、`released`。
- Review gate：apply 模式必须匹配 `resume_acquire_delivery_transaction_lock_provider`、`resume_renew_delivery_transaction_lock_provider` 或 `resume_release_delivery_transaction_lock_provider` 审批；缺审批时不调用 provider。
- Side-effect policy：workflow result 现在按 step result 汇总 `distributed_lock_acquired`、`distributed_lock_renewed`、`distributed_lock_released`。
- Journal：成功 acquire / renew / release 都会把 provider operation、lock status、provider id、fencing token、lease expiry 和 side-effect policy 写入 append-only workflow journal。
- Boundary：这是显式 review-gated lifecycle step surface，不是自动 lock lifecycle manager；不自动 acquire-before-workflow、不自动 release-after-workflow、不 daemon / polling、不自动 stale takeover、不实现 Redlock quorum consensus、不替代 downstream fencing-token gate。
- 测试：`tests.test_delivery_resume` 覆盖 all lock-provider steps dry-run plan、审批后 acquire+release lifecycle、renew regression 和 tool provider metadata 透传；`tests.test_delivery_tools` / `tests.test_delivery_lock_provider` 作为集成回归范围。

### Step 88：Workflow fencing token propagation baseline

- Scheduler：`DeliveryResumeWorkflowScheduler` 在单次 `execute_delivery_resume_workflow` 执行中维护 workflow-local fencing token state。
- Propagation：成功 `acquire_delivery_transaction_lock_provider` / `renew_delivery_transaction_lock_provider` step 返回 fencing token 后，后续 runner step 自动收到 `expected_transaction_lock_fencing_token`；显式 `config.expected_transaction_lock_fencing_token` 优先级更高。
- Release clear：成功 `release_delivery_transaction_lock_provider` step 会清空已传播 token，后续 runner step 不再继承旧 fencing token。
- Metadata / journal：runner step result 和 append-only `delivery-resume-workflow-journal.json` 会记录 `fencing_token_propagation`，包含 expected token、source、显式 token override 和是否发生 propagation。
- Boundary：这是 same-execution evidence propagation，不是跨运行 journal replay、不是自动 acquire / renew / release、不是 daemon / polling、不 stale takeover、不实现 Redlock quorum consensus，也不是所有调用方的全局 automatic fencing enforcement。
- 测试：`tests.test_delivery_resume` 覆盖 acquire 后传播到 apply recovery、release 后清空传播 token、journal metadata 与下游 fencing gate；`tests.test_delivery_tools` / `tests.test_delivery_lock_provider` / `tests.test_workspace_contract` / `tests.test_doctor` 作为集成回归范围。

### Step 89：Journal-state fencing replay baseline

- Scheduler：`DeliveryResumeWorkflowScheduler` 在执行 pending step 前读取既有 `delivery-resume-workflow-journal.json`，构造保守 journal fencing replay state。
- Replay：resume-of-resume 跳过已完成 `acquire_delivery_transaction_lock_provider` / `renew_delivery_transaction_lock_provider` step 时，可从同 transaction 的成功 journal 条目恢复未过期 fencing token 给后续 runner step。
- Release clear：journal 中成功 `release_delivery_transaction_lock_provider` 会清空 replay state，后续 runner step 不继承旧 fencing token。
- Metadata：skipped step result 记录 `fencing_token_replay`，后续 runner step 继续记录 `fencing_token_propagation`，source 会标为 `workflow_journal:<action>`。
- Boundary：只 replay 最小 fencing-token evidence，不重放 provider action、不 restore manifest、不 commit transaction、不 external delivery、不自动 renew lease、不 stale takeover、不实现 Redlock quorum consensus。
- 测试：`tests.test_delivery_resume` 覆盖 journaled acquire replay 到 apply recovery、journaled release 清空 replay state、下游 fencing gate 与既有 resume-of-resume 回归；`tests.test_delivery_tools` / `tests.test_delivery_lock_provider` / `tests.test_workspace_contract` / `tests.test_doctor` 作为集成回归范围。

### Step 90：Skipped-step journal context replay baseline

- Scheduler：`DeliveryResumeWorkflowScheduler` 为已有 workflow journal 构建同 transaction 的 read-only replay index。
- Skipped step metadata：已完成 step 被跳过时，step result 增加 `journal_replay`，记录上一轮 entry status、runner status、transition status、lock provider / fencing / lease evidence、created_at 与 side-effect policy。
- Transaction scope：completed action 识别按当前 transaction id 过滤，避免其他 transaction 的旧 journal entry 让本轮 workflow 误跳过 step。
- Boundary：这是只读审计 / dependency context replay，不重放 runner payload、不执行 transition、不 restore manifest、不 commit transaction、不发布 external delivery、不自动 rollback-vs-commit。
- 测试：`tests.test_delivery_resume` 覆盖 skipped preflight journal context replay、read-only side-effect metadata、runner / transition status 可见性，以及其他 transaction journal 不触发跳过。


### Step 79：Delivery resume runner baseline

- `delivery.resume_runner`：新增 `DeliveryResumeRunner`、`DeliveryResumeRunnerConfig`、`DeliveryResumeExecution` 与 `SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS`，把 Step 77 resume plan 和 Step 78 approval ledger 串成单步 review-gated runner。
- Tool / subagent：delivery subagent 新增 `execute_delivery_resume`，位于 `plan_delivery_resume` 之后；支持 `plan_only`、`preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery`、`commit_cross_run_transaction`。
- Approval gate：apply 模式默认要求 `review-approval-ledger.json` 中存在匹配 transaction subject、runner action 和 `decision=approved` 的 written entry；dry-run 可无审批，只做计划和 transition dry-run。
- Execution boundary：runner 只委托既有 `DeliveryTransactionTransitionExecutor` 执行一个明确 transition，保留 LocalDeliveryExecutor 的 journal / digest / recovery / commit / lock checks；不自动选择 ambiguous rollback-vs-commit 路径。
- Artifact / workspace：apply 成功写 `delivery-resume-execution.json`；workspace contract 新增 `workspace/delivery-resume-execution.json` -> `/workspace/delivery/delivery-resume-execution.json`。
- Boundary：这是 review-gated single-transition resume runner，不是完整 durable workflow scheduler；不启动新 local delivery，不 external delivery，不 release/acquire distributed lock，不 stale takeover，不 broader physical rollback。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_resume` 覆盖 dry-run、缺 approval 阻断、审批后 preflight 执行和 tool；`tests.test_delivery_tools` 覆盖 delivery subagent tool 顺序；`tests.test_workspace_contract` 覆盖 route。


### Step 78：Review approval ledger baseline

- `review_approval`：新增 `ReviewApprovalConfig`、`ReviewApprovalRecord`、`ReviewApprovalLedgerWriter` 与 supported decision / mode 常量，提供独立的人工 review decision 审计记录 writer。
- Tool / subagent：review subagent 新增 `record_review_approval` tool；`evaluate_delivery_review_gate` 继续保持 read-only，`record_review_approval` 只有显式调用才记录审批审计。
- Artifact / workspace：默认写入 `artifact_root/workspace/review-approval-record.json` 与 append-only `artifact_root/workspace/review-approval-ledger.json`；workspace contract 新增 `workspace/review-approval-record.json` 和 `workspace/review-approval-ledger.json` -> `/workspace/review/` routes。
- Safety gates：dry-run 不写文件；apply 必须 `approve_decision_record=true`、存在 reviewer、decision / mode 合法，可选 expected subject digest 匹配；阻断时不写 record / ledger。
- Boundary：这是审批审计 baseline，不执行 delivery、external delivery、manifest mutation、transaction commit、rollback、materialization 或 automatic approval；后续 full durable resume workflow scheduler / rollback executor / delivery executor 可把 ledger 作为 review-gated 输入。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_review_approval` 覆盖 dry-run、apply 审批阻断、append-only ledger、digest mismatch、tool side-effect policy；`tests.test_review_subagent` 与 `tests.test_workspace_contract` 覆盖子智能体工具和 route。


### Step 77：Durable delivery resume planner baseline

- `delivery.resume`：新增 `DeliveryResumePlanner`、`DeliveryResumePlannerConfig`、`DeliveryResumePlan` 与 `SUPPORTED_DELIVERY_RESUME_ACTIONS`，从 delivery root 只读汇总 transaction state、rollback state、transition plan、transaction lock 与 lock release 证据，生成 durable resume 建议。
- Artifact：显式 `mode=apply` 且 checks 通过时只写 `delivery-resume-plan.json`；dry-run 不写文件。该 artifact 包含 `recommended_resume_action`、`resume_steps`、`checks`、`blocking_reasons`、`lock_summary` 和 side-effect policy。
- Lock gate：active lock 属于其他 owner 且 expected resume token 不匹配时，resume plan blocked，并建议 `review_or_release_delivery_transaction_lock`；同 owner 或匹配 resume token 可继续生成 reviewed resume plan；stale lock 只进入 review / release 建议，不自动 takeover。
- Tool / subagent：delivery subagent 新增 `plan_delivery_resume` tool，位于 `execute_local_delivery` 之后、transition/recovery/rollback executor 之前；tool 支持 `delivery_root`、`transaction_id`、`mode`、`write_resume_plan`、`expected_resume_token`、`transaction_lock_owner` 和 metadata JSON。
- Inspector / workspace：delivery inspector 索引 `delivery-resume-plan.json`；workspace contract 新增 `workspace/delivery-resume-plan.json` -> `/workspace/delivery/delivery-resume-plan.json`。
- Boundary：这是 resume planner / audit artifact writer，不是完整 durable workflow scheduler；不执行 transition，不 restore manifest，不 commit transaction，不 external delivery，不 acquire/release distributed lock，不 physical rollback。后续仍需 full durable resume workflow scheduler、true distributed transaction lock、broader physical rollback state machine、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_resume` 覆盖 no-transaction dry-run、active lock owner mismatch 阻断、resume token match 放行、apply 只写 resume plan、terminal transaction no-resume、tool 写 plan；`tests.test_delivery_inspector` 与 `tests.test_workspace_contract` 覆盖 artifact 索引；delivery 定向 44 项通过。

### Step 76：Delivery transaction lock release / stale review baseline

- `LocalDeliveryExecutor`：新增显式 `release_transaction_lock` cleanup / review 动作，默认 dry-run 只生成 release plan；apply 模式必须设置 `approve_transaction_lock_release=true` 才允许删除本地 `delivery-transaction-lock.json`。
- Safety checks：可选 `expected_transaction_lock_owner`、`expected_transaction_lock_transaction_id` 与 `expected_resume_token` 必须匹配既有 lock；malformed lock、owner / transaction / token mismatch 或缺少审批都会 blocked，并写 `delivery-transaction-lock-release.json` 审计记录，不删除 lock。
- Stale review：stale lock 会被检测并写入 release artifact，但不会自动 takeover；只有显式 release approval 通过后才作为本地 cleanup 删除 lock。
- Propagation：`execute_local_delivery` tool 暴露 release 参数；delivery inspector 与 workspace contract 索引 `workspace/delivery-transaction-lock-release.json` -> `/workspace/delivery/delivery-transaction-lock-release.json`。
- Boundary：这是 local delivery root lock cleanup / stale review baseline，不是 distributed lock release，不提供 lease renewal、fencing、consensus、automatic stale takeover 或完整 durable workflow scheduler。
- 测试：新增未审批阻断、审批匹配删除、expected owner mismatch 阻断、tool 调用、inspector 读取与 workspace route 断言。
- 后续仍需真正 distributed transaction lock、durable resume workflow、broader physical rollback state machine、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。

### Step 75：Delivery transaction lock / resume preflight baseline

- `LocalDeliveryExecutor`：新增 opt-in `require_transaction_lock`、`transaction_lock_owner`、`transaction_lock_lease_seconds` 与 `expected_resume_token` 配置；apply-mode 需要执行本地 artifact 复制、backend manifest 原地 mutation、recovery apply、cross-run commit 或 external delivery request 时，可先写 / 检查 `delivery-transaction-lock.json`。
- Lock / resume：lock artifact 记录 owner、operation、lease_expires_at、resume_token、expected_resume_token、checks、blocking_reasons 和 recommended_actions；同 owner 或匹配 resume token 可继续，其他 owner、token mismatch 或 stale lock 默认阻断，要求人工 review / cleanup，不自动接管 stale lock。
- Side-effect gate：锁阻断时保持 `status=blocked` / `next_action=review_or_release_delivery_transaction_lock`，不复制 artifact、不写 receipt / journal / mutation / recovery / commit / external-delivery result，不调用 provider，也不覆盖既有 lock；helper 统一按 effective dry-run 处理，避免 blocked 后续被 commit / recovery / external delivery 状态覆盖。
- Propagation：transition / recovery / rollback executor 与 delivery tools 透传 lock 参数；delivery inspector 与 workspace contract 索引 `workspace/delivery-transaction-lock.json` -> `/workspace/delivery/delivery-transaction-lock.json`。
- Boundary：这是 local delivery root lock / resume preflight baseline，不是 distributed lock，不提供跨机器 consensus、lease renewal、fencing token、automatic stale lock takeover 或完整 durable resume workflow。
- 测试：新增 local lock acquire / block / resume、锁阻断不改 backend manifest、不写终态 artifact、tool 参数透传、inspector 读取与 workspace route 断言。
- 后续仍需真正 distributed transaction lock、durable resume workflow、broader physical rollback state machine、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。

### Step 74：Delivery rollback apply executor explicit-review-only baseline

- `delivery.rollback`：`DeliveryRollbackExecutor` 的 `SUPPORTED_DELIVERY_ROLLBACK_ACTIONS` 新增 `apply_rollback`，并为 config 增加 `approve_rollback` 与 `expected_rollback_phase` 显式 gate。
- Apply path：`apply_rollback` 在 apply 模式下必须处于 `rollback_decision_required`（或调用方显式要求的 expected phase）、提供 `expected_transaction_id` 与 `backend_manifest_path`，并设置 `approve_rollback=true`；通过后委托 `DeliveryTransactionRecoveryExecutor(action=apply_recovery)` 执行本地 manifest recovery。
- Artifacts / side effects：成功后写 `delivery-rollback-state.json`、`backend-artifact-manifest-recovery.json` 与 `delivery-rollback-execution.json`，并在 execution side-effect policy 中标记 `manifest_recovered=true` / `local_manifest_rollback_performed=true` / `files_mutated=true`；`physical_rollback_performed=false` 和 `broader_filesystem_physical_rollback_performed=false` 保持为边界声明。
- Safety gates：缺少审批、缺少 expected transaction id、缺少 backend manifest path、rollback phase 不匹配、terminal / blocked rollback state、external delivery performed、duplicate terminal guard 或 malformed artifact 都会阻断，不写 recovery result。
- Boundary：这是 explicit-review-only local manifest rollback baseline，不 commit transaction、不发布 external delivery、不 acquire distributed lock、不实现 resume semantics，也不执行 broader filesystem physical rollback。
- 测试：`tests.test_delivery_state_machine` 覆盖未审批阻断与显式审批恢复 manifest；`tests.test_delivery_tools` 覆盖 tool 调用。
- 后续仍需 broader physical rollback state machine、stronger distributed transaction locking / resume semantics、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。

### Step 73：Delivery rollback executor dry-run / preflight baseline

- `delivery.rollback`：新增 `DeliveryRollbackExecutor`、`DeliveryRollbackExecutorConfig`、`DeliveryRollbackExecution` 与 `SUPPORTED_DELIVERY_ROLLBACK_ACTIONS`，在 rollback state writer 和 transition executor 之上提供保守 rollback workflow shell。
- Actions：支持 `plan_rollback` 与 `preflight_rollback`；默认 dry-run 只规划，不写文件；显式 `mode=apply` 的 `preflight_rollback` 会先写 `delivery-rollback-state.json`，再委托 `DeliveryTransactionTransitionExecutor` 写 `backend-artifact-manifest-recovery-preflight.json`，最后写 `delivery-rollback-execution.json` 审计记录。
- Safety gates：apply preflight 要求 recoverable phase、`expected_transaction_id` 和 `backend_manifest_path`；terminal / blocked rollback state、external delivery performed、duplicate terminal guard 或 malformed artifact 会阻断。
- Boundary：这是 preflight baseline，不执行 `apply_backend_manifest_recovery`，不 commit transaction，不发布 external delivery，不 acquire distributed lock，不执行 physical rollback，也不实现 resume semantics。
- Tool / workspace：delivery subagent 新增 `execute_delivery_rollback` tool；workspace contract 索引 `workspace/delivery-rollback-execution.json` -> `/workspace/delivery/delivery-rollback-execution.json`。
- 测试：`tests.test_delivery_state_machine` 覆盖 dry-run plan、apply preflight 写 state + recovery preflight、external delivery terminal blocker；`tests.test_delivery_tools` 覆盖 tool 调用和 subagent 暴露；`tests.test_workspace_contract` 覆盖 route future path。
- 后续仍需 broader physical rollback state machine、stronger distributed transaction locking / resume semantics、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。

### Step 72：Delivery rollback state artifact writer baseline

- `delivery.rollback_writer`：新增 `DeliveryRollbackStateArtifactWriter`、`DeliveryRollbackStateWriterConfig` 与 `DeliveryRollbackStateWrite`，复用 delivery transaction inspector 读取既有 transaction artifacts，并把 `evaluate_delivery_rollback_state(...)` 的只读结果封装为可持久化审计记录。
- Tool / subagent：delivery subagent 新增 `write_delivery_rollback_state` tool；默认 `mode=dry-run` 只返回计划，不写文件；显式 `mode=apply` 且 artifact load 无错误时写 `delivery-rollback-state.json`。
- Boundary：writer 只写 rollback-state audit artifact，不 restore manifest、不 commit transaction、不调用 external delivery provider、不 acquire distributed lock、不执行 physical rollback；blocked rollback phase 也可被写入，方便后续人工 review 和 resume workflow 使用。
- Workspace / API：`workspace/delivery-rollback-state.json` route 继续归入 `/workspace/delivery/`；public delivery API 导出 writer 类型。
- 测试：`tests.test_delivery_state_machine` 覆盖 dry-run 不写与 apply 写 artifact；`tests.test_delivery_tools` 覆盖 tool 调用和 subagent 暴露；`tests.test_workspace_contract` 覆盖 route future path。
- 后续仍需 write-capable cross-run rollback executor / physical state machine、stronger distributed transaction locking / resume semantics、advanced adaptive provider retry policy 和第三方 external delivery provider；Android / iOS / 小程序完整运行链路继续搁置。

### Step 71：Delivery cross-run rollback state machine baseline

- `delivery.rollback_state`：新增 `DeliveryRollbackPhase`、`DeliveryRollbackTransition`、`DeliveryRollbackState` 与 `evaluate_delivery_rollback_state(...)`，把 transaction journal、recovery preflight、recovery result、commit record、external delivery result 和 terminal idempotency guard 归一成只读 rollback workflow phase。
- Phases：覆盖 `no_transaction`、`local_delivery_applied`、`rollback_preflight_required`、`rollback_decision_required`、`rollback_applied`、`committed`、`external_delivery_performed`、`duplicate_terminal_action_blocked` 和 `blocked`。
- Review-gated transitions：在 `rollback_preflight_required` 阶段建议 `preflight_backend_manifest_recovery`；在 `rollback_decision_required` 阶段同时暴露 `apply_backend_manifest_recovery` 与 `commit_cross_run_transaction`，明确 reviewer 必须选择 rollback 或 commit。
- Inspector / workspace：delivery inspector 输出 `rollback_state`；workspace contract 索引 `workspace/delivery-rollback-state.json` -> `/workspace/delivery/delivery-rollback-state.json`；API 从 `reverse_deepagent.delivery` 导出 rollback state 类型与 evaluator。
- Boundary：这是 read-only cross-run rollback state machine baseline，不执行 manifest restore / commit / external delivery，不写 rollback state artifact，不实现 physical rollback executor、distributed lock 或 automatic resume。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_state_machine`、`tests.test_delivery_inspector`、`tests.test_delivery_tools`、`tests.test_workspace_contract` 定向 45 项通过。

### Step 70：Delivery transaction idempotency guard baseline

- `LocalDeliveryExecutor`：新增本地 `DeliveryTransactionIdempotencyGuard`，用于拦截重复执行已完成的 `apply_backend_manifest_recovery` 或 `commit_cross_run_transaction`。
- Artifact preservation：当 journal 已标记 `backend_manifest_recovered=true` / `cross_run_transaction_committed=true`，或既有 terminal artifact 已是 `recovered` / `committed` 时，重复 apply 会写 `delivery-transaction-idempotency-guard.json`，不会覆盖原有 `backend-artifact-manifest-recovery.json` / `backend-artifact-manifest-transaction-commit.json`。
- Workspace / result：`DeliveryExecutionResult.to_dict()` 暴露 `transaction_idempotency_guard`；transaction state / inspector 可读取 guard flag 与 evidence path；workspace contract 索引 `workspace/delivery-transaction-idempotency-guard.json` -> `/workspace/delivery/delivery-transaction-idempotency-guard.json`。
- Boundary：这是单 delivery root 的 terminal action duplicate guard，不是分布式 transaction lock，不做 automatic resume / retry，不替代写入型 cross-run rollback executor / physical state machine beyond read-only rollback state baseline。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_executors` 覆盖重复 recovery / commit 不覆盖 terminal artifact；delivery 聚焦 76 项通过。


### Step 69：Delivery transaction recovery workflow executor baseline

- `delivery.recovery`：新增 `DeliveryTransactionRecoveryExecutor`、`DeliveryRecoveryExecutorConfig`、`DeliveryRecoveryExecution` 与 `SUPPORTED_DELIVERY_RECOVERY_ACTIONS`，在单步 transition shell 之上提供 recovery workflow 编排。
- Actions：支持 `plan_recovery`、`preflight_recovery` 和显式审批的 `apply_recovery`；默认 dry-run 只规划，apply recovery 必须配置 `approve_recovery=true` 与 `expected_transaction_id`。
- Orchestration：`apply_recovery` 会按顺序委托 `DeliveryTransactionTransitionExecutor` 执行 `preflight_backend_manifest_recovery` -> `apply_backend_manifest_recovery`，底层 journal / digest / rollback checkpoint / manifest checks 仍由 `LocalDeliveryExecutor` 负责。
- Tool / workspace：delivery subagent 新增 `execute_delivery_recovery` tool；workspace contract 索引 `workspace/delivery-recovery-execution.json` -> `/workspace/delivery/delivery-recovery-execution.json`。
- Boundary：这是 recovery workflow baseline，不自动选择 commit vs rollback，不执行 external delivery，不提交 cross-run transaction，不实现写入型 cross-run rollback executor / physical state machine beyond read-only rollback state baseline；transaction terminal duplicate guard 已由 Step 70 补齐，但更强的分布式锁 / resume semantics 仍是后续工作。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_state_machine`、`tests.test_delivery_tools`、`tests.test_delivery_inspector`、`tests.test_workspace_contract`、`tests.test_subagent_smoke` 定向 43 项通过。

### Step 68：Provider-specific retry / rate-limit metadata baseline

- `WebhookExternalDeliveryProvider` / `PresignedObjectExternalDeliveryProvider` / `GitHubReleaseExternalDeliveryProvider`：在已有 explicit retry baseline 上新增 `retry_jitter_seconds` 与 `honor_retry_after` provider config；默认仍保持 `retry_attempts=0`、`retry_backoff_seconds=0`、`retry_jitter_seconds=0`，不主动放大请求或等待。
- HTTP attempt metadata：`_http_request_with_retries(...)` 现在解析 `Retry-After` 与 GitHub-compatible `X-RateLimit-*` headers，并为每次 attempt 记录 `retry_after_seconds`、`retry_after_seen`、`retry_after_honored`、`planned_retry_delay_seconds`、`jitter_seconds_configured` 和 secret-safe `rate_limit` 摘要；不记录原始 headers、response body、request headers、token 或 URL query secret。
- Provider / ledger summary：external-delivery-result metadata 为 request / release / lookup / delete / upload stage 输出 `*_retry_summary`；`external-delivery-idempotency-ledger.json` 的 attempt summary 同步保留 Retry-After / rate-limit / budget exhaustion 摘要，仍是审计流水，不执行 recovery 或 rollback。
- Registry / doctor：webhook、presigned-object、github-release capability metadata 暴露 `supports_retry_after_metadata`、`supports_rate_limit_metadata`、`supports_retry_budget_metadata`、`supports_retry_jitter_config` 与 `default_retry_jitter_seconds=0`。
- Boundary：这是 metadata hardening，不是自适应 retry governor；GitHub secondary rate-limit 专用退避、分布式 retry budget、第三方 external delivery provider、cross-run rollback state machine beyond recovery workflow executor baseline 仍是后续工作。Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor` 定向 71 项通过。

### Step 66：GitHub Release asset overwrite/delete preflight plan baseline

- `GitHubReleaseExternalDeliveryProvider`：在同名 asset lookup 命中时，新增 secret-safe `existing_asset` 摘要与 `existing_asset_overwrite_plan`，用于描述 delete existing asset + upload replacement asset 的人工审批要求和 partial-failure plan。
- Side-effect boundary：这是 preflight plan，不发送 `DELETE` 请求，不覆盖 asset，不改变 `allow_existing_asset=true` 的既有语义；`allow_existing_asset` 仍只表示允许继续尝试 duplicate upload，不等价于 overwrite。
- Redaction：matched asset 只记录 id、name、redacted API URL、size / content-type / state 等摘要；不记录 response body、request / response headers、token、URL query secret 或 `browser_download_url` 原始路径。
- Registry / doctor：`github-release` capability metadata 新增 `supports_existing_asset_overwrite_preflight=true` 与 `supports_existing_asset_delete_preflight=true`，同时继续标记 `supports_existing_asset_overwrite=false` / `supports_existing_asset_delete=false`。
- Boundary：真正的 GitHub asset DELETE + replacement upload、partial failure recovery、provider-specific Retry-After / rate-limit metadata 已由 Step 68 补齐，更高级 adaptive retry governor 仍是后续步骤；Android / iOS / 小程序完整运行链路继续搁置。
- 测试：`tests.test_delivery_executors`、`tests.test_external_delivery_registry`、`tests.test_doctor` 定向 67 项通过。

### Step 65：Delivery transaction transition executor baseline

- `delivery.transitions`：新增 `DeliveryTransactionTransitionExecutor`、`DeliveryTransitionExecutorConfig`、`DeliveryTransitionExecution` 和 `SUPPORTED_DELIVERY_TRANSITIONS`，把已有 delivery transaction inspector / transition planner 与 `LocalDeliveryExecutor` recovery / commit 能力串成显式 transition execution shell。
- Supported transitions：当前仅支持 `preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery` 和 `commit_cross_run_transaction`；dry-run 可规划，apply 必须显式指定 transition，不允许 `auto` 在有歧义的 `apply_recovery_or_commit_after_review` 上直接执行。
- Tool / subagent：delivery subagent 现在暴露 `execute_local_delivery` 与 `execute_delivery_transition`；后者默认 dry-run，apply 时仍委托 `LocalDeliveryExecutor` 执行已有 digest / journal / recovery / commit checks，不绕过检查。
- Artifact / workspace：新增 `delivery-transition-execution.json` execution audit record，并通过 inspector 与 workspace contract 暴露 `workspace/delivery-transition-execution.json` -> `/workspace/delivery/delivery-transition-execution.json`。
- Boundary：这是 explicit transition shell；recovery workflow baseline 已由 Step 69 补齐，但它仍不是写入型 cross-run rollback executor / physical state machine beyond read-only rollback state baseline；不自动选择 recovery vs commit，不发布 external delivery，不执行 automatic rollback，不替代 state machine / inspector 的 read-only 边界。
- 测试：`tests.test_delivery_state_machine`、`tests.test_delivery_tools`、`tests.test_delivery_inspector`、`tests.test_workspace_contract` 定向 38 项通过；Android / iOS / 小程序完整运行链路继续搁置。

### Step 64：External delivery idempotency ledger baseline

- `delivery.executors`：新增 `ExternalDeliveryIdempotencyLedger` 与 `external-delivery-idempotency-ledger.json` append-only audit artifact；显式 `request_external_delivery=true` 且 apply 写 external delivery result 时，同步记录 transaction id、idempotency key、provider id、result status、performed 状态、duplicate guard、provider factory invocation、blocking reasons、recommended actions 和 retry attempt summary。
- Duplicate guard：同一 delivery root 下第二次 external delivery 被 duplicate guard 阻断时，也会 append ledger entry；provider factory 仍不会被调用，`external-delivery-duplicate-guard.json` 行为保持不变。
- Retry metadata：webhook / presigned object / GitHub Release provider 的 explicit retry attempts 会被归一到 ledger 的 `attempt_summary`，只记录 attempt number、status code、error class、retryable 和 will_retry，不记录 request headers、response headers、response body、token 或 URL query secret。
- State / inspector / workspace：`DeliveryTransactionJournal` 增加 `external_delivery_idempotency_ledger_path`；`evaluate_delivery_transaction_state(...)` 暴露 `external_delivery_idempotency_ledger_recorded` flag 与 evidence path；`inspect_delivery_transaction_root(...)` 读取 ledger artifact；workspace contract 新增 `workspace/external-delivery-idempotency-ledger.json` -> `/workspace/delivery/external-delivery-idempotency-ledger.json` 路由。
- Boundary：ledger 是审计 baseline，不执行 publish / retry / recovery / rollback，不替代 duplicate guard，不绕过 review；dry-run 不写 ledger 文件；cross-run rollback state machine beyond recovery workflow executor baseline、provider-specific Retry-After / rate-limit metadata 已由 Step 68 补齐，GitHub asset overwrite / delete 已由 Step 66 / Step 67 补齐；更高级 adaptive retry policy 仍是后续工作。
- 测试：`tests.test_delivery_executors`、`tests.test_delivery_state_machine`、`tests.test_delivery_inspector`、`tests.test_workspace_contract` 定向 59 项通过；Android / iOS / 小程序完整运行链路继续搁置。

### Step 63：External delivery explicit retry policy baseline

- Provider-neutral helper：新增 `ExternalDeliveryHttpRequestResult` 与 `_http_request_with_retries(...)`，统一记录 HTTP attempt 摘要，支持 retryable status code、显式 retry attempts 和可选 backoff。
- Provider config：`WebhookExternalDeliveryProvider`、`PresignedObjectExternalDeliveryProvider` 与 `GitHubReleaseExternalDeliveryProvider` 支持 `retry_attempts`、`retry_backoff_seconds`、`retry_status_codes`，默认 `retry_attempts=0`，保持旧行为。
- Metadata：apply 结果记录 `retry_enabled`、`retry_attempts_configured`、`retry_status_codes`、`request_attempt_count` / GitHub 分阶段 attempt count、retry count 和 `request_attempts` / GitHub 分阶段 attempts；attempt 摘要只包含 attempt number、status code、error、retryable 和 will_retry。
- Redaction boundary：不记录 request headers、response headers、response body、URL query secret 或 token；dry-run 仍 side-effect-free，不打开 socket。
- Doctor metadata：`webhook`、`presigned-object`、`github-release` capability metadata 新增 `supports_explicit_retry=true`、`default_retry_attempts=0` 与默认 retry status codes。
- Boundary：这是 explicit retry baseline，不自动放大外部发布副作用；idempotency ledger 绑定已由 Step 64 收口；更复杂的 per-provider rate-limit policy、jitter、retry budget 和 GitHub asset overwrite / delete 仍是后续工作。
- 测试：`tests.test_delivery_executors` 覆盖 webhook 503 -> retry -> 204 成功链路与 secret redaction；`tests.test_external_delivery_registry` / `tests.test_doctor` 覆盖 capability metadata。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 62：GitHub Release asset duplicate preflight baseline

- Provider config：`GitHubReleaseExternalDeliveryProvider` 新增 `check_existing_asset` 与 `allow_existing_asset`，默认检查 existing release assets，且默认不允许同名 asset 继续上传。
- Apply flow：release create 或 explicit existing-release reuse 成功后，会读取 GitHub release `assets_url`，GET assets list，检查 `asset_name` 是否已存在；同名 asset 默认在 upload 前 blocked。
- Override：显式 `allow_existing_asset=true` 只表示允许继续尝试 upload，不删除、不覆盖已有 asset，也不保证 GitHub API 会接受 duplicate asset。
- Metadata：新增 redacted `assets_url`、`asset_lookup_attempted`、`asset_lookup_succeeded`、`existing_asset_found`、`existing_asset_count`、`asset_lookup_status_code`、`check_existing_asset` 与 `allow_existing_asset`；继续不记录 response body / headers / request headers / token。
- Doctor metadata：`github-release` capability metadata 新增 `supports_existing_asset_preflight=true`、`existing_asset_conflict_default=block` 与 `supports_existing_asset_overwrite=false`，metadata-only 路径仍不调用 provider factory、不联网。
- Boundary：这是 conservative duplicate preflight baseline；仍不执行 asset delete / overwrite，不实现 retry / backoff，不替代完整 cross-run transaction state machine。
- 测试：`tests.test_delivery_executors` 覆盖 fake GitHub API create -> assets lookup -> upload、existing-release reuse -> assets lookup -> upload、同名 asset 默认 blocked、`allow_existing_asset=true` 显式继续 upload attempt 与 secret redaction；`tests.test_external_delivery_registry` / `tests.test_doctor` 覆盖 capability metadata。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 61：GitHub Release existing-release reuse baseline

- Provider config：`GitHubReleaseExternalDeliveryProvider` 新增 `reuse_existing_release`，默认 `False`，避免 create release 失败时自动复用旧 release。
- Apply flow：显式开启后，create release 未拿到 upload URL 时会 GET `/repos/{owner}/{repo}/releases/tags/{tag}`，成功拿到 existing release upload URL 后继续上传 JSON delivery package asset。
- Metadata：新增 `release_created`、`existing_release_lookup_attempted`、`existing_release_lookup_succeeded`、`existing_release_reused`、`existing_release_status_code` 和 redacted `existing_release_api_url`，继续不记录 response body / headers / request headers / token。
- Doctor metadata：`github-release` capability metadata 新增 `supports_existing_release_reuse=true`，metadata-only 路径仍不调用 provider factory、不联网。
- Boundary：这是 explicit opt-in release reuse baseline；同名 asset preflight 已由 Step 62 补齐；仍不覆盖 / 删除 release assets，不实现 retry / backoff，不替代完整 cross-run transaction state machine。
- 测试：`tests.test_delivery_executors` 覆盖 fake GitHub API create 422 -> GET tag -> upload 三段请求链与 secret redaction；`tests.test_external_delivery_registry` / `tests.test_doctor` 覆盖 capability metadata。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 60：GitHubReleaseExternalDeliveryProvider baseline

- Provider：新增 `GitHubReleaseExternalDeliveryProvider`，内置 provider id 为 `github-release`，alias 为 `gh-release` / `github-release-assets`。
- Registry / doctor：默认 `ExternalDeliveryProviderRegistry` 与 `reverse-agent-doctor --external-delivery-providers` 可 metadata-only 暴露 GitHub Release provider，不调用 provider factory、不发布、不依赖 MCP / Chrome。
- Dry-run：`DeliveryExecutionMode.DRY_RUN` 只返回 planned / blocked preflight result，不打开 socket，并对 GitHub API URL query / credentials、token 和 request headers 做序列化隔离。
- Apply：显式 apply 时通过 GitHub REST create release，再向返回的 upload URL 上传 provider-neutral JSON delivery package asset。
- Redaction：result metadata 只保留 redacted release / upload URL、request body digest / bytes、status code 和 attempted / success flags；不记录 token、request headers、response body 或 response headers。
- Tool：`execute_local_delivery` 可通过 `external_delivery_provider_config_json` 透传 GitHub Release provider 配置，仍只导出 config summary，不导出原始 secret 值。
- Boundary：当前为 JSON asset upload baseline；显式 release 复用已由 Step 61 补齐，同名 asset preflight 已由 Step 62 补齐，但仍不覆盖 / 删除既有 asset，不实现 retry / backoff，不替代完整 cross-run transaction state machine。
- 测试：`tests.test_external_delivery_registry` 覆盖 provider / alias；`tests.test_delivery_executors` 覆盖 dry-run redaction 与 fake GitHub API apply 双 POST；`tests.test_delivery_tools` 覆盖 tool config redaction；`tests.test_doctor` 覆盖 provider matrix count / alias / transport。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 59：Workspace opt-in actual dual-write writer baseline

- Pipeline opt-in：`run_reverse_pipeline(...)`、`write_outputs(...)`、`run_platform_pipeline(...)` 和 `write_platform_outputs(...)` 新增 `enable_workspace_dual_write`，默认 `False` 保持 legacy-only 写入。
- Actual writer：显式开启后，已登记 workspace artifact 会通过 `WorkspacePathResolver` 同时写 legacy canonical path 与 `artifact_root/workspace/<area>/...` foldered future path。
- Audit artifact：新增 route `workspace_dual_write_plan` / `workspace/workspace-dual-write-plan.json`，双写开启时写入审计记录，列出 artifact key、canonical path、future path、virtual URI、实际写入 path、migration status 与 authoritative-path 边界。
- Manifest boundary：`workspace/backend-artifact-manifest.json` 仍以 legacy path 作为 manifest entry path；foldered path 继续通过 `metadata.workspace_alias.future_path` 和 dual-write plan 发现。
- Contract payload：新增 `actual_dual_write_writer_available=true`，`path_resolver.opt_in_dual_write_policy=legacy-and-future-path`，同时继续声明 `dual_write_default_enabled=false` 与 `physical_migration_default_enabled=false`。
- 测试：`tests.test_workspace_contract` 覆盖默认不创建 foldered physical artifact、显式双写创建 future path、双写审计 plan、manifest canonical path 不变。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 58：WorkspacePathResolver / opt-in dual-write plan baseline

- `workspace_contract.WorkspacePathResolver`：新增 resolver-only 路径解析层，可按 artifact key、legacy path、foldered future path 或 `virtual://workspace/...` URI 找到同一 `WorkspaceArtifactRoute`。
- `WorkspacePathResolution`：输出 canonical path / canonical URI / future path / virtual URI / read paths / write paths / producer roles / migration status，默认保持 legacy `workspace/*.json` authoritative。
- Opt-in dual-write plan：显式 `enable_dual_write=True` 时，`write_paths` 包含 legacy canonical path 与 foldered future path，但只做 plan-only 返回，不创建目录、不复制文件、不移动 artifact、不修改 pipeline 写入点。
- Manifest alias：`metadata.workspace_alias` 增加 `canonical_uri` 与 `resolver_migration_status=resolver-only`，继续保留 `migration_status=manifest-alias-only`。
- Contract payload：`path_migration_policy` 增加 resolver availability、dual-write opt-in 与 physical migration default disabled 字段，并新增 `path_resolver` policy 摘要。
- 测试：`tests.test_workspace_contract` 覆盖默认 legacy authoritative、future path / virtual URI 解析、opt-in dual-write plan 和 pipeline manifest alias 兼容。
- Android / iOS / 小程序完整运行链路继续搁置。

### Step 57：Rebuild Subagent split

- `subagents.rebuild`：新增 `rebuild` 子智能体、prompt 和 `build_rebuild_subagent(...)`，默认 `build_reverse_agent(...)` 将其放在 `review` 与 `delivery` 之间。
- Tool：`rebuild` 子智能体持有 `build_rebuild_delivery` 和新增 `review_rebuild_artifacts`；前者负责写 rebuild-plan / rebuild files，后者只读复核 RebuildResult / rebuild-plan readiness、generated files、review_hints、runtime-assisted recommendation 和 declared outputs。
- Delivery split：`subagents.delivery` 改名为 `delivery` 语义边界，工具收窄为 `execute_local_delivery`，不再混入 rebuild generation。
- Workspace contract：`rebuild` 从 `planned-contract` 晋升为 `implemented`，当前 planned-contract 子智能体清零。
- Side-effect boundary：`review_rebuild_artifacts` 固定 read-only，不写 artifact、不执行 replay / Scrapy、不执行 local / external delivery、不 mutate manifest。
- 测试：`tests.test_rebuild_subagent` 覆盖 risk review hint block、ready bundle pass、not-ready warning、prompt loader 和默认 agent subagent 顺序；`tests.test_delivery_tools` 同步 delivery 只暴露 local delivery tool；`tests.test_workspace_contract` 同步角色状态；`tests.test_subagent_smoke` 回归 DeepAgents delegation。
- Android / iOS / 小程序完整运行链路继续搁置。


### Step 56：Hook Subagent baseline

- `subagents.hook`：新增 `hook` 子智能体、prompt 和 `build_hook_subagent(...)`，默认 `build_reverse_agent(...)` 将其放在 `debugger` 与 `timeline` 之间。
- Tool：新增 `make_review_hook_artifacts_tool()` / `review_hook_artifacts`，读取已有 hook artifact 聚合 JSON，输出 function / module hook inventory、source-logpoint、candidate、timeline event 和 installed target 摘要。
- Review blockers：识别 hook failure、missing targets、installed hooks without events、candidates without installed hooks，并给出 `review_required_items` 与 `next_action`。
- Side-effect boundary：tool 固定 read-only，不安装 hook / breakpoint / logpoint，不 evaluate JavaScript，不触发目标函数 / module export，不写 hook artifact，不触发 delivery。
- Workspace contract：`hook` 从 `planned-contract` 晋升为 `implemented`，负责 `/workspace/hooks/` 的 hook artifact review / capture readiness 边界。
- 测试：`tests.test_hook_subagent` 覆盖 installed-without-events warning、captured events pass、failed hook block、side-effect policy、prompt loader 和默认 agent subagent 顺序；`tests.test_workspace_contract` 同步角色状态；`tests.test_subagent_smoke` 回归 DeepAgents delegation。
- `rebuild` 已由 Step 57 收口，当前 planned-contract 子智能体已清零；Android / iOS / 小程序完整运行链路继续搁置。


### Step 55：Debugger Subagent baseline

- `subagents.debugger`：新增 `debugger` 子智能体、prompt 和 `build_debugger_subagent(...)`，默认 `build_reverse_agent(...)` 将其放在 `timeline` 前。
- Tool：新增 `make_review_debugger_artifacts_tool()` / `review_debugger_artifacts`，读取已有 debugger artifact 聚合 JSON，输出 paused-session 状态、continuation preflight、callframe、callframe evaluation、mutation audit、debugger action 和 debugger timeline 摘要。
- Review blockers：识别 durable snapshot live action blocked、debugger failure、pause failure、missing artifact、paused without callframes 和 live continuation unavailable，并给出 `review_required_items` 与 `next_action`。
- Side-effect boundary：tool 固定 read-only，不连接 CDP、不发送 Debugger / Runtime 命令、不 resume / step / evaluate、不安装 breakpoint / hook、不写 debugger artifact、不触发 delivery。
- Workspace contract：`debugger` 从 `planned-contract` 晋升为 `implemented`，负责 `/workspace/debugger/` 的 debugger artifact review / paused-session preflight 边界。
- 测试：`tests.test_debugger_subagent` 覆盖 durable snapshot live resume block、live available pass、missing artifact warn、side-effect policy、prompt loader 和默认 agent subagent 顺序；`tests.test_workspace_contract` 同步角色状态；`tests.test_subagent_smoke` 回归 DeepAgents delegation。
- 当前 planned-contract 子智能体已清零；`hook` 已由 Step 56 收口，`rebuild` 已由 Step 57 收口；Android / iOS / 小程序完整运行链路继续搁置。


### Step 54：Timeline Subagent baseline

- `subagents.timeline`：新增 `timeline` 子智能体、prompt 和 `build_timeline_subagent(...)`，默认 `build_reverse_agent(...)` 将其放在 `review` 前。
- Tool：新增 `make_review_flow_timeline_tool()` / `review_flow_timeline`，读取已有 `flow-timeline.json` 结构化 JSON，输出 entry source counts、correlation group readiness、stitch proposal 状态、auto-stitch dry-run / conflict / policy / materialization / rollback 摘要。
- Review blockers：识别 pending stitch proposal、blocked policy decision、unresolved stitch conflict、materialization request without approval，并给出 `review_required_items` 与 `next_action`。
- Side-effect boundary：tool 固定 read-only，不写 timeline artifact、不生成 `stitched-flow.json`、不记录 reviewer approval、不执行 rollback、不触发 delivery。
- Workspace contract：`timeline` 从 `planned-contract` 晋升为 `implemented`，负责 `/workspace/timeline/` 的 timeline review / stitch proposal blocker 边界。
- 测试：`tests.test_timeline_subagent` 覆盖 pending proposal block、approved timeline pass、side-effect policy、prompt loader 和默认 agent subagent 顺序；`tests.test_workspace_contract` 同步角色状态；`tests.test_subagent_smoke` 回归 DeepAgents delegation。
- 当前 planned-contract 子智能体已清零；`debugger` 已由 Step 55 收口，`hook` 已由 Step 56 收口，`rebuild` 已由 Step 57 收口；Android / iOS / 小程序完整运行链路继续搁置。


### Step 53：Review Subagent baseline

- `subagents.review`：新增 `review` 子智能体、prompt 和 `build_review_subagent(...)`，默认 `build_reverse_agent(...)` 在无 runtime 时也会挂载该子智能体。
- Tool：新增 `make_evaluate_review_gate_tool()` / `evaluate_delivery_review_gate`，读取 `RebuildResult` JSON 和可选 `EvidencePromotionResult` JSON，复用 `evaluate_review_gate(...)` 输出 delivery gate。
- Side-effect boundary：tool 固定 read-only，不写 artifact、不复制文件、不执行 local delivery、不调用 external provider、不记录 reviewer approval。
- Workspace contract：`review` 从 `planned-contract` 晋升为 `implemented`，负责 `/workspace/review/`、`/workspace/evidence/`、`/workspace/timeline/` 的 review gate / evidence review requirement 边界。
- 测试：`tests.test_review_subagent` 覆盖 gate pass / block、side-effect policy、prompt loader 和默认 agent subagent 顺序；`tests.test_workspace_contract` 同步角色状态；`tests.test_subagent_smoke` 回归 DeepAgents delegation。
- 当前 planned-contract 子智能体已清零；`debugger` 已由 Step 55 收口，`hook` 已由 Step 56 收口，`rebuild` 已由 Step 57 收口；Android / iOS / 小程序完整运行链路继续搁置。


### Step 52：Delivery transaction inspector / doctor baseline

- `delivery.inspector`：新增 `inspect_delivery_transaction_root(...)`，只读取 delivery root 中的 `delivery-transaction-journal.json`、`external-delivery-result.json`、`backend-artifact-manifest-recovery-preflight.json`、`backend-artifact-manifest-recovery.json` 和 `backend-artifact-manifest-transaction-commit.json`。
- State reuse：inspector 复用 `evaluate_delivery_transaction_state(...)` 与 `plan_delivery_transition(...)`，输出 `state_snapshot`、`transition_plan`、artifact exists / loaded / keys / error 状态、`missing_artifacts` 和 `load_errors`。
- Doctor：新增 `reverse-agent-doctor --delivery-transaction-root ...`，metadata-only 路径跳过 CDP port probe，不要求 MCP / Chrome，不调用 browser/runtime/external provider factory。
- Side-effect boundary：read-only inspector 不复制文件、不 restore manifest、不写 transaction commit、不调用 external delivery provider、不上传、不发布。
- 测试：`tests.test_delivery_inspector` 覆盖 journal-only local_applied、external result + commit record、malformed JSON 不抛异常；`tests.test_doctor` 覆盖 delivery transaction doctor 不依赖浏览器或 MCP；`tests.test_delivery_state_machine` 回归 state / transition baseline。
- recovery workflow baseline 已由 Step 69 补齐；后续仍需 write-capable cross-run rollback executor / physical state machine beyond read-only rollback state baseline / stronger distributed transaction locking beyond local idempotency guard baseline / 更多第三方 provider / advanced adaptive provider retry policy；Android / iOS / 小程序完整运行链路继续搁置。


### Step 51：BrowserProvider capability compatibility matrix

- `browser.smoke`：新增 `validate_browser_provider_capability_compatibility(...)` 和 `BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION`，在 metadata-only matrix 中校验 provider capability 组合是否自洽。
- Rule baseline：覆盖 `breakpoints_require_cdp`、`persistent_context_requires_lifecycle`、`response_body_requires_network_or_cdp`、`request_initiator_requires_network_or_cdp`、`websocket_frames_require_network_or_cdp`，并对 runtime eval / script source / CDP / managed browser 的可疑组合给 warning。
- Matrix output：`browser_provider_smoke_matrix` 每个 provider row 增加 `compatibility`，顶层增加 `compatibility_rule_version`，summary 增加 `compatible_count` / `warning_count` / `error_count`；doctor matrix 的 `ok` 会把 compatibility error 计入失败。
- Side-effect boundary：compatibility validator 只读取 capability metadata，不调用 provider factory、不导入可选浏览器 SDK、不探测 CDP、不启动浏览器、不依赖 MCP。
- 测试：`tests.test_browser_smoke_matrix` 覆盖兼容 provider、breakpoint without CDP 错误、不兼容 provider matrix not-ok；`tests.test_doctor` 覆盖 doctor matrix 输出 rule version 和内置 provider compatibility。
- planned-contract 子智能体已清零；后续仍需真实第三方 BrowserProvider plugin implementation，以及真实第三方 provider 接入后的 provider-specific compatibility rules。Android / iOS / 小程序完整运行链路继续搁置。


### Step 50：BrowserProvider plugin package template

- `packages/reverse-deepagent-browser-provider-template/`：新增可复制 optional package 模板，声明 `reverse_deepagent.browser_providers` entry point。
- `template-browser` registration：提供 `BrowserProviderRegistration`、非敏感 `BrowserProviderCapabilities`、alias 和 factory；registration / metadata listing 不调用 factory、不启动浏览器、不探测 CDP、不依赖 MCP。
- Provider skeleton：`TemplateBrowserProvider.start()` / `connect()` 默认抛出 `BrowserProviderUnavailableError`，防止模板包伪装成真实浏览器集成；接入方需要替换生命周期和 session/page adapter。
- README：说明如何复制 provider id、aliases、capability metadata、factory 与 entry point，并强调 optional SDK import / 真启动必须延迟到 explicit runtime 或 doctor smoke。
- 测试：`tests.test_browser_provider_plugin_template` 覆盖 pyproject entry point、依赖声明、registration metadata side-effect-free、registry alias resolve 和 explicit factory create；`tests.test_browser_provider_registry` 回归 registry contract。
- planned-contract 子智能体已清零；后续仍需真实第三方 BrowserProvider plugin implementation，以及真实第三方 provider 接入后的 provider-specific compatibility rules；更细粒度 metadata-only compatibility matrix 已由 Step 51 收口。Android / iOS / 小程序完整运行链路继续搁置。


### Step 49：Browser Runtime Subagent baseline

- `subagents.browser_runtime`：新增 `browser_runtime` 子智能体，作为 BrowserProvider 能力发现与会话健康检查的独立边界；它不执行 Web recon、source search、network sampling、hook / protection / breakpoint patch。
- Tools：新增 `list_browser_providers` 和 `describe_browser_provider`，均走 `BrowserProviderRegistry.list_registration_metadata()` / metadata lookup，返回 provider matrix、alias、capability flags 和 side-effect policy；metadata-only 路径不启动浏览器、不探测 CDP、不调用外部 provider factory、不依赖 MCP。
- Runtime session：当 agent 构建时传入 Web runtime，`browser_runtime` 才附加 `ensure_browser_session`，用于显式 session readiness 检查；无 runtime 时仅保留 metadata tools。
- Orchestration：`build_reverse_agent(...)` 在 runtime 存在时把 `browser_runtime` 放在 `web_recon` 之前，保证 provider 能力边界先于 Web recon 暴露给 DeepAgents。
- Workspace contract：`browser_runtime` 从 `planned-contract` 晋升为 `implemented`，继续拥有 `/workspace/browser/` 与 `/workspace/runtime/`。
- 测试：`tests.test_browser_runtime_subagent` 覆盖 metadata-only matrix、alias describe、unknown provider structured error、prompt loader、subagent tool set 和默认 agent subagent 顺序；`tests.test_workspace_contract` 同步角色状态。
- planned-contract 子智能体已清零；后续仍需真实第三方 BrowserProvider plugin implementation，以及 BrowserProvider plugin package template 后续真实接入与 provider capability compatibility matrix 演进。Android / iOS / 小程序完整运行链路继续搁置。


### Step 48：BrowserProvider registry / entry-point discovery baseline

- `browser.registry`：新增 `BROWSER_PROVIDER_ENTRY_POINT_GROUP=reverse_deepagent.browser_providers`、`load_entry_points()`、`list_registration_metadata()`、内置 provider registration helpers 和 `build_default_browser_provider_registry()`。
- `native-web`：`create_native_web_runtime()` 改为通过 `BrowserProviderRegistry` 解析 `playwright-chromium`、`cloakbrowser`、`remote-cdp` 及其 alias，不再在 runtime factory 中维护 provider if/else 分支。
- `doctor`：`reverse-agent-doctor --browser-provider-matrix` 现在暴露 `entry_point_group`、`provider_registration_metadata`、`registered_provider_ids` 和 `provider_factories_invoked=false` side-effect policy；metadata-only 路径仍不探测 CDP、不启动浏览器、不依赖 MCP。
- 测试：`tests.test_browser_provider_registry` 覆盖默认内置 provider、alias、entry point 载入不调用 factory、非法 entry point payload；`tests.test_native_web_runtime` / `tests.test_doctor` / provider tests 回归 provider config 与错误兼容。
- `browser_runtime` 子智能体实体化已由 Step 49 收口，独立 BrowserProvider plugin package template 已由 Step 50 收口，provider capability compatibility matrix 已由 Step 51 收口。Android / iOS / 小程序完整运行链路继续搁置。


### Step 47：Delivery transaction state machine skeleton

- `delivery.state_machine`：新增 `DeliveryTransactionState`、`DeliveryTransactionSnapshot`、`DeliveryTransitionPlan`、`evaluate_delivery_transaction_state(...)` 和 `plan_delivery_transition(...)`。
- `DeliveryExecutionResult.to_dict()`：新增内嵌 `transaction_state`，从执行结果、transaction journal、external delivery result、backend manifest recovery / commit record 归一化出 current state、completed_states、flags、evidence_paths、blocking_reasons 和 recommended_actions。
- 状态覆盖：`planned`、`local_applied`、`manifest_revision_committed`、`manifest_patch_written`、`manifest_preflight_passed`、`manifest_mutated`、`recovery_required`、`recovered`、`external_delivery_attempted`、`external_delivered`、`committed`、`blocked`。
- 边界：这是 read-only evaluator / conservative transition planner，不会执行文件复制、manifest mutation、rollback recovery、external delivery、GitHub Release 或网络发布；完整 write-capable cross-run rollback executor / physical state machine 与更强分布式锁仍是后续工作。
- 测试：`tests.test_delivery_state_machine` 覆盖 dry-run、apply、本地 manifest mutation、review-only blocker、fake external delivery、cross-run commit journal re-evaluation；`tests.test_delivery_executors` 回归验证现有 executor 行为未被改变。
- Android / iOS / 小程序完整运行链路继续搁置。


### Step 46：DeepAgents workspace manifest-only folder alias baseline

- `workspace_manifest_alias_metadata()`：新增 workspace artifact route -> manifest alias helper，为已登记 artifact key 生成 `metadata.workspace_alias`。
- `workspace/backend-artifact-manifest.json`：Web pipeline 与 platform-neutral pipeline 的 manifest entry 现在会记录 `canonical_path`、`canonical_path_remains_authoritative=true`、`virtual_folder`、`future_path`、`virtual_uri`、`producer_roles` 和 `migration_status=manifest-alias-only`。
- 兼容边界：不移动、不重命名、不 dual-write 现有 `workspace/*.json` 文件；manifest `path` 仍指向原 canonical filesystem path，foldered path 只是 compatibility alias / future path。
- 测试：`tests.test_workspace_contract` 覆盖 helper、contract policy、Web pipeline manifest alias 和 platform-neutral pipeline manifest alias。
- 后续仍需物理 folder migration / dual-write compatibility、消费者迁移、cross-run rollback state machine 和 stronger distributed transaction locking beyond local idempotency guard baseline；Android / iOS / 小程序完整运行链路继续搁置。


### Step 45：RuntimeBackend doctor / metadata CLI baseline

- `RuntimeBackendRegistry.list_registration_metadata()`：新增 canonical backend metadata + aliases + keys 输出，不创建 runtime，不调用 backend factory。
- `reverse-agent-doctor --runtime-backends`：新增 metadata-only doctor 模式，输出 `runtime_backend_matrix`，包括 `matrix_version`、`entry_point_group`、`backend_ids`、`backends`、`capability_flags`、summary counts 与 side-effect policy。
- side-effect policy：matrix 固定声明 `backend_factories_invoked=false`、`browser_sessions_started=false`、`chrome_started=false`、`mcp_started=false`、`platform_tools_invoked=false`；metadata-only 模式跳过 CDP port probe。
- 覆盖范围：默认 matrix 展示 core runtime backends（`mock`、`native-web`、`remote-cdp`、`playwright-cli`、`chrome-cdp`、`browser-cli`、`android-adb`、`ios-simulator`、`mini-program-devtools`）及其 alias；已安装的 `reverse_deepagent.runtime_backends` entry point plugin 会被加载 registration metadata，但不会调用 factory。
- 测试：`tests.test_doctor` 覆盖默认 matrix、summary counts、side-effect policy 和 entry point factory-not-invoked；`tests.test_runtime_registry` 覆盖 registration metadata API。
- 后续仍需 DeepAgents 虚拟文件夹物理迁移 / broader consumer adoption、write-capable cross-run rollback executor / physical state machine beyond read-only rollback state baseline / stronger distributed transaction locking beyond local idempotency guard baseline、更多第三方 provider / advanced adaptive provider retry policy，以及更高级 Browser/CDP 调试能力；Android / iOS / 小程序完整运行链路继续搁置。


### Step 44：PresignedObjectExternalDeliveryProvider / object-storage PUT provider baseline

- `PresignedObjectExternalDeliveryProvider`：新增内置 `presigned-object` provider，支持 `presigned_url`、`object_name`、`content_type`、`headers` 和 `timeout_seconds` runtime config；dry-run 不打开网络 socket，只返回 planned / blocked result。
- Provider alias：默认 registry 新增 `object-storage`、`presigned-url`、`s3-presigned`，`reverse-agent-doctor --external-delivery-providers` 会 side-effect-free 展示 `transport=object-storage`、`supports_external_delivery=true`、`review_only=false`。
- apply 行为：只有显式 `request_external_delivery=true`、`mode=apply`、provider 指向 `presigned-object` alias 且配置了 `presigned_url` 时，才会对 presigned URL 执行 HTTP `PUT`，body 为 provider-neutral JSON delivery package。
- metadata 保密：result metadata 只记录 redacted target URL、`target_query_redacted`、`target_credentials_redacted`、`object_name`、request body digest / bytes、request attempted / succeeded、response status code、configured header count 和 content type；不记录请求 header、响应 header、响应 body、presigned URL query 或 URL credentials。
- tool / prompt / README：`execute_local_delivery` 文档、delivery subagent prompt 和 README 已补 `presigned-object` / `object-storage` 配置口径；README 同时修正 webhook 已实现但旧文档仍写 future 的问题。
- 测试：`tests.test_delivery_executors` 覆盖 dry-run redaction / no-network 与本地 HTTP server PUT apply；`tests.test_delivery_tools` 覆盖 tool JSON config dry-run；`tests.test_external_delivery_registry` 覆盖 provider alias / factory；`tests.test_doctor` 覆盖 provider matrix 计数和 alias。
- 后续仍需更多第三方 provider / advanced adaptive provider retry policy，以及 write-capable cross-run rollback executor / physical state machine beyond read-only rollback state baseline / stronger distributed transaction locking beyond local idempotency guard baseline；本 baseline 不管理云 SDK、bucket、credentials，也不绕过 duplicate guard。


### Step 35：Backend manifest cross-run transaction commit baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestTransactionCommit`、`commit_cross_run_transaction` 与 `expected_commit_transaction_id` 配置；可读取上一轮 `delivery-transaction-journal.json`、默认 recovery preflight、当前 source manifest digest 与 rollback checkpoint 状态。
- commit 只在显式 `mode=apply`、expected transaction id 匹配、recovery preflight 为 `ready_for_review` / `no_recovery_required`、source digest 与 recovery preflight 一致、上一轮 journal 未 external delivery 且未重复 cross-run commit 时通过。
- commit 成功时写 `backend-artifact-manifest-transaction-commit.json`，并更新上一轮 journal 的 `cross_run_transaction_committed=true` 与 `backend_manifest_transaction_commit_path`，同时保留上一轮 artifact entries、manifest mutation path、rollback path 等字段。
- commit blocked 时仍写 reviewable commit record，但不覆盖上一轮 journal。
- `execute_local_delivery` tool：新增 `commit_cross_run_transaction` 与 `expected_commit_transaction_id` 参数。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-transaction-commit.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- `cross_run_transaction_committed=true` 只表示本地 delivery transaction journal 被显式 commit；不执行 external delivery，不上传、不推送。
- commit 依赖 recovery preflight，source manifest 在 recovery preflight 后发生 drift 时必须 blocked，并保留上一轮 journal 未提交状态。
- 该 baseline 本身不 restore manifest；显式 rollback-checkpoint restore 已由 Step 36 接上。它仍不实现 external delivery executor，不实现跨运行 physical rollback state machine。

### Step 36：Backend manifest recovery apply baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestRecovery`、`apply_backend_manifest_recovery` 与 `backend_manifest_recovery_name` 配置；可读取上一轮 `delivery-transaction-journal.json`、`backend-artifact-manifest-recovery-preflight.json`、rollback checkpoint 与当前标准 backend manifest digest。
- recovery apply 只在显式 `mode=apply`、recovery preflight 为 `ready_for_review`、expected transaction id 匹配、上一轮 journal 未 external delivery / 未 cross-run commit / 未 recovered、source manifest digest 未 drift、rollback digest 与 preflight 一致时通过。
- recovery 成功时写 `backend-artifact-manifest-recovery.json`，把 `backend-artifact-manifest.rollback.json` 恢复为标准 `backend-artifact-manifest.json`，并更新上一轮 journal 的 `backend_manifest_recovered=true` 与 `backend_manifest_recovery_path`。
- recovery blocked 时仍写 reviewable recovery record，但不覆盖上一轮 journal，也不修改标准 backend manifest。
- `execute_local_delivery` tool：新增 `apply_backend_manifest_recovery` 参数。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-recovery.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- `backend_manifest_recovered=true` 只表示本地显式 recovery apply 已从 rollback checkpoint 恢复标准 manifest；不执行 external delivery，不上传、不推送，也不提交 cross-run transaction。
- source manifest 在 recovery preflight 后发生 drift 时必须 blocked，并保留上一轮 journal 未恢复状态。
- 该 baseline 是 explicit-review-only rollback-checkpoint restore，不是自动恢复，不是完整 manifest recovery state machine，也不是 cross-run physical rollback transaction state machine。


### Step 37：ExternalDeliveryProvider contract baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `ExternalDeliveryPackage`、`ExternalDeliveryResult`、`ExternalDeliveryProvider` protocol、`ReviewOnlyExternalDeliveryProvider`、`request_external_delivery`、`external_delivery_result_name`、`external_delivery_provider_id` 与 `external_delivery_provider` 配置。
- 显式 `request_external_delivery=true` 时，会构造 provider-neutral package 并调用 provider；默认 review-only provider 只写 blocked handoff result，不执行上传、推送、发布或第三方系统调用。
- `delivery-transaction-journal.json`：新增 `external_delivery_result_path`，并可记录配置 provider 返回的 `external_delivery_performed=true`；默认 review-only provider 固定 `external_delivery_performed=false`。
- `execute_local_delivery` tool：新增 `request_external_delivery` 与 `external_delivery_provider_id` 参数。
- `workspace-contract.json`：新增 `workspace/external-delivery-result.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：review-only provider blocked record、fake provider performed contract、tool 参数和 workspace route。

验收口径：

- 该 baseline 只证明 external delivery provider contract 与 artifact / journal 回写链路；默认 provider 永不发布。
- GitHub Release provider 已有内置 JSON asset upload baseline；asset 覆盖 / retry 与第三方 delivery provider 仍需后续 provider 插件实现；webhook 与 presigned object-storage provider 已有内置 baseline。
- `external_delivery_performed=true` 只能来自显式配置 provider 的返回值，不能由本地 copy、manifest commit 或 transaction commit 隐式推导。


### Step 38：ExternalDeliveryProvider registry / entry-point discovery baseline

状态：已完成。

变更摘要：

- 新增 `src/reverse_deepagent/delivery/registry.py`，提供 `ExternalDeliveryProviderRegistry`、`ExternalDeliveryProviderRegistration`、`ExternalDeliveryProviderCapabilities`、`ExternalDeliveryProviderFactory` 与 `EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP = "reverse_deepagent.external_delivery_providers"`。
- 默认 registry 通过 `build_default_external_delivery_provider_registry()` 注册 `review-only` provider，并提供 `noop` / `manual-handoff` alias。
- registry 支持加载 entry point 返回的单个 registration、callable registration producer 或 registration iterable；加载 metadata 时只注册 factory，不调用 provider factory，保持 side-effect-light。
- `LocalDeliveryExecutor`：未显式注入 `external_delivery_provider` 时，通过 `external_delivery_provider_registry` 或默认 registry 解析 `external_delivery_provider_id`。
- 测试覆盖：默认 registry metadata / alias、重复 key、capability id mismatch、entry point 加载不调用 factory、callable 多 registration、无效 payload、entry point load error，以及 executor 使用默认 registry alias。

验收口径：

- registry baseline 只解决 provider 插拔和发现，不内置真实外部发布实现。
- GitHub Release provider 已以内置 baseline 挂到 `reverse_deepagent.external_delivery_providers`；asset 覆盖 / retry 与第三方 delivery provider 应以后续插件形式挂入；webhook 与 presigned object-storage provider 已有内置 baseline。
- provider metadata listing 不得上传、推送、发布或调用 provider factory。

### Step 39：ExternalDeliveryProvider doctor / metadata CLI baseline

状态：已完成。

变更摘要：

- `ExternalDeliveryProviderRegistry`：新增 `list_registration_metadata()`，在不创建 provider 的前提下输出 canonical provider metadata、alias 和 registered keys。
- `reverse-agent-doctor`：新增 `--external-delivery-providers`，输出 `external_delivery_provider_matrix`，包含 `entry_point_group`、provider ids、alias、transport、`review_only`、`supports_external_delivery`、summary counts 和 side-effect policy。
- metadata-only doctor 模式会跳过 CDP port probe，不要求 MCP / Chrome，也不会调用 `ExternalDeliveryProvider` factory。
- 测试覆盖：默认 review-only provider matrix、alias 可见性、missing MCP 不影响 external delivery provider metadata-only doctor，以及 fake entry point registration 加载时不调用 factory。

验收口径：

- 该 baseline 只提供外部交付 provider 可见性和 doctor 诊断面，不执行 external delivery。
- `side_effect_policy.provider_factories_invoked=false`、`external_delivery_requested=false`、`external_delivery_performed=false` 是 doctor metadata-only 模式的硬边界。
- GitHub Release provider 已有内置 JSON asset upload baseline；asset 覆盖 / retry 与第三方 delivery provider 仍需后续插件实现；webhook 与 presigned object-storage provider 已有内置 baseline。

### Step 40：External delivery idempotency / duplicate guard baseline

状态：已完成。

变更摘要：

- `DeliveryExecutorConfig`：新增 `external_delivery_idempotency_key`、`allow_duplicate_external_delivery` 和 `external_delivery_duplicate_guard_name`。
- `ExternalDeliveryPackage` / provider metadata：写入 `external_delivery_idempotency_key` 与 `allow_duplicate_external_delivery`，真实 provider 可复用该 key 做幂等。
- `DeliveryTransactionJournal`：新增 `external_delivery_idempotency_key` 字段；duplicate guard 触发时会保留上一轮 journal 中的 `external_delivery_performed=true` 与原 external result path，避免覆盖交付证据。
- `LocalDeliveryExecutor`：同一 delivery root 中如果上一轮 `delivery-transaction-journal.json` 或 `external-delivery-result.json` 已标记 `external_delivery_performed=true`，默认在 provider factory / provider 调用前返回 blocked `ExternalDeliveryResult`，并写 `external-delivery-duplicate-guard.json`。
- `execute_local_delivery` tool：新增 `external_delivery_idempotency_key` 与 `allow_duplicate_external_delivery` 参数。
- `workspace-contract.json`：新增 `workspace/external-delivery-duplicate-guard.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：重复 external delivery 默认不调用 provider、duplicate guard artifact 写入、上一轮 performed journal 状态保留、显式 `allow_duplicate_external_delivery=true` 后才允许 provider retry，以及 tool 参数透传。

验收口径：

- duplicate guard 只防止重复 external delivery provider 调用，不阻止本地文件复制或人工显式 retry。
- `allow_duplicate_external_delivery=true` 是显式 reviewed override；默认必须保持 false。
- 该 baseline 不是完整 cross-run transaction state machine；webhook 与 presigned object-storage provider 已由后续 Step 43 / Step 44 补齐，GitHub Release provider baseline 已由 Step 60 补齐，asset 覆盖 / retry 仍待后续。

### Step 41：LocalArchiveExternalDeliveryProvider / filesystem-release baseline

状态：已完成。

变更摘要：

- `LocalArchiveExternalDeliveryProvider`：新增内置 `local-archive` provider，dry-run 只返回 planned result，不创建 archive 目录；apply 模式把 `LocalDeliveryExecutor` 已复制到 delivery root 的 artifact 再复制到本地 archive release dir。
- `ExternalDeliveryProviderRegistry`：默认注册 `local-archive`，并提供 `filesystem-release` / `archive` alias；doctor metadata-only 输出中可见 `transport=filesystem`、`supports_external_delivery=true`、`review_only=false`，且仍不调用 provider factory。
- `DeliveryExecutorConfig` / `execute_local_delivery` tool：新增 `external_delivery_provider_config` 与 `external_delivery_provider_config_json`，当前可用于传入 `archive_root`；webhook 与 presigned object-storage provider 已复用同一 provider-specific config seam，GitHub Release provider 已沿用该 seam。
- external delivery result metadata：记录 `archive_root`、`archive_release_dir`、`archive_manifest_path`、`archive_checksums_path`、`archived_artifacts` 与 filesystem transport limitation；archive release dir 内写 `local-archive-manifest.json` 与 `local-archive-checksums.json`。
- 测试覆盖：local-archive dry-run 无副作用、apply 归档已交付 artifact、tool JSON config 透传、registry alias / metadata、doctor provider matrix summary。

验收口径：

- `local-archive` 是第一个真实 external delivery provider，但边界只到本地文件系统 archive；不上传网络服务、不创建 GitHub Release；网络发布由显式 GitHub Release / webhook / presigned provider 处理，且不绕过 review / duplicate guard。
- duplicate guard 仍必须在 provider factory / provider 调用前执行；`allow_duplicate_external_delivery=false` 继续是默认硬约束。
- 后续仍需 advanced adaptive provider retry policy 与更多第三方 provider，以及 write-capable cross-run rollback executor / physical state machine beyond read-only rollback state baseline / stronger distributed transaction locking beyond local idempotency guard baseline；webhook 与 presigned object-storage provider 已有内置 baseline。

### Step 42：ExternalDeliveryProvider config redaction / capability metadata guard baseline

状态：已完成。

变更摘要：

- `external_delivery_metadata_has_secret_like_keys`：新增 external delivery 专用 secret-like metadata 检测，覆盖 `key`、`token`、`secret`、`password`、`cookie`、`authorization`、`credential`、`private` 等明显敏感 key。
- `ExternalDeliveryProviderRegistration`：registration 初始化阶段拒绝 capability metadata 中出现 secret-like key，保证 `reverse-agent-doctor --external-delivery-providers` 和 registry metadata listing 不会变成 token 泄漏通道。
- `DeliveryExecutorConfig.external_delivery_provider_config`：保留 runtime provider config 传给 provider factory，但 `ExternalDeliveryPackage.metadata` 只导出 `external_delivery_provider_config_summary`，包含 configured / key_count / non_secret_keys / secret_like_key_count / raw_values_exported=false，不导出原始值。
- 测试覆盖：capability metadata secret-like key rejection、runtime provider config summary、不把 webhook URL / token 等 provider config 原始值写入 package artifact。

验收口径：

- provider runtime config 可以携带真实凭据供 provider 使用，但不得被 doctor matrix、capability metadata、package metadata 或 result metadata 默认明文导出。
- GitHub Release provider 已复用该 summary / metadata guard，不得自定义绕过；webhook 与 presigned object-storage provider 已复用该 guard。

### Step 43：WebhookExternalDeliveryProvider / HTTP JSON provider baseline

状态：已完成。

变更摘要：

- `WebhookExternalDeliveryProvider`：新增内置 `webhook` provider，支持 `webhook_url`、`headers` 和 `timeout_seconds` runtime config；dry-run 不打开网络 socket，只返回 planned / blocked result。
- `ExternalDeliveryProviderRegistry`：默认注册 `webhook`，并提供 `webhook-json` / `http-webhook` alias；doctor metadata-only 输出中可见 `transport=webhook`、`supports_external_delivery=true`、`review_only=false`，且仍不调用 provider factory。
- apply 模式：向显式 `webhook_url` POST JSON delivery package；只把 request body digest / bytes、redacted target URL、status code、request_attempted / request_succeeded 写入 result metadata。
- redaction policy：metadata 不记录请求 header 原始值，不记录响应体，不记录响应 header；URL username / password 和 query string 默认从 metadata target URL 中移除，并用 `target_credentials_redacted` / `target_query_redacted` 标记。
- 测试覆盖：dry-run 不发网且 redacts URL credential / query / header value；apply 使用本地 HTTP server 验证 JSON POST、204 success、Authorization header 只发送不记录、result metadata 不包含 query secret / header secret。

验收口径：

- `webhook` 是真实 HTTP JSON external delivery provider，但只有显式 `request_external_delivery=true`、`external_delivery_provider_id=webhook|http-webhook` 且 `mode=apply` 时才会发请求。
- duplicate guard 仍在 provider factory / provider 调用前执行；dry-run 仍保持 side-effect free。
- GitHub Release provider、recovery workflow baseline 已补齐；后续仍需 write-capable cross-run rollback executor / physical state machine beyond read-only rollback state baseline / stronger distributed transaction locking beyond local idempotency guard baseline。


### Step 34：Backend manifest cross-run recovery preflight baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestRecoveryPreflight`、`preflight_backend_manifest_recovery` 与 `expected_recovery_transaction_id` 配置；可读取上一轮 delivery transaction journal、in-place mutation record、patched manifest、rollback checkpoint 与当前 source manifest digest。
- recovery preflight 会输出 `ready_for_review`、`blocked` 或 `no_recovery_required`，并记录 source / rollback digest、一致性 checks、blocking reasons 与 recommended actions。
- recovery-only apply 模式不会覆盖上一轮 `delivery-transaction-journal.json`；只写 `backend-artifact-manifest-recovery-preflight.json`。
- `execute_local_delivery` tool：新增 `preflight_backend_manifest_recovery` 与 `expected_recovery_transaction_id` 参数。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-recovery-preflight.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- preflight 只读取并判断上一轮 transaction artifact，不 restore manifest，不改写 source manifest，不提交 cross-run transaction。
- source manifest digest 与 in-place mutation record 的 post digest 不一致时，输出 `status=blocked` 与 `source_matches_post_mutation_digest_if_mutated` blocking reason。
- 没有发生 backend manifest in-place mutation 的上一轮 journal 会输出 `no_recovery_required`，而不是伪装成 recoverable。
- 后续仍需 manifest recovery state machine、stronger distributed transaction locking / duplicate-resume hardening beyond local idempotency guard baseline 和外部交付执行器。

### Step 33：Backend manifest in-place mutation executor baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestInPlaceMutation` 与 `approve_backend_manifest_in_place_mutation` 配置；只有显式审批、`mode=apply`、patch 已写入、preflight 通过且 expected source digest 与当前 source manifest 匹配时，才执行标准 backend manifest 原地 mutation。
- mutation 前写本地 rollback checkpoint：`backend-artifact-manifest.rollback.json`；mutation 结果写入 `backend-artifact-manifest-in-place-mutation.json`，并在 journal / result 中暴露 `backend_manifest_mutated`、`backend_manifest_rollback_written`、mutation path 和 rollback path。
- `execute_local_delivery` tool：新增 `approve_backend_manifest_in_place_mutation` 参数。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-in-place-mutation.json` 与 `workspace/backend-artifact-manifest.rollback.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- 默认不审批时，即使 preflight passed，也不执行 source manifest 原地 mutation，不写 rollback checkpoint。
- digest mismatch 即使显式审批也会生成 `status=blocked`，不改写 source manifest，不写 rollback checkpoint。
- 显式审批通过后只执行本地标准 manifest mutation 与本地 rollback checkpoint；仍不执行 external delivery，不提交 true cross-run transaction，也不提供跨运行 manifest recovery state machine。

### Step 32：Backend manifest in-place mutation preflight baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestInPlacePreflight` 与 `preflight_backend_manifest_in_place_mutation` 配置；dry-run 下只返回 planned preflight，不写 delivery 目录；apply 成功且显式开启时写 `backend-artifact-manifest-preflight.json`。
- preflight 会校验 source backend manifest 是否存在、可选 expected digest 是否匹配、local patched manifest 是否可用、patched entries 是否存在重复 artifact key，并固定记录 `backend_manifest_mutated=false`。
- `execute_local_delivery` tool：新增 `preflight_backend_manifest_in_place_mutation` 与 `expected_backend_manifest_digest_sha256` 参数。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-preflight.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- 默认仍是 dry-run，不产生文件系统副作用。
- preflight 只判断未来 in-place mutation 是否可进入下一步审批；它不执行 source manifest in-place mutation。
- digest mismatch 会生成 `status=blocked` 与 blocking reason，不会把阻断状态伪装成已提交。
- `in_place_mutation_allowed=true` 只表示 preflight 通过，不等价于 `backend_manifest_mutated=true`；本阶段仍固定 `backend_manifest_mutated=false`、`external_delivery_performed=false`、`cross_run_transaction_committed=false`。
- 后续仍需 cross-run recovery state machine、stronger distributed transaction locking / duplicate-resume hardening beyond local idempotency guard baseline 和外部交付执行器。

### Step 31：Backend artifact manifest mutation policy baseline

状态：已完成。

变更摘要：

- `LocalDeliveryExecutor`：新增 `BackendManifestMutation` 与 `commit_backend_manifest_mutation` 配置；dry-run 下只返回 planned mutation，不写 delivery 目录；apply 成功且显式开启时写 `backend-artifact-manifest-mutation.json` 与 `backend-artifact-manifest.patched.json`。
- `execute_local_delivery` tool：新增 `commit_backend_manifest_mutation` 与 `backend_manifest_path` 参数，用于把 reviewed artifact 的本地交付结果转成 backend manifest patch plan。
- `workspace-contract.json`：新增 `workspace/backend-artifact-manifest-mutation.json` 与 `workspace/backend-artifact-manifest.patched.json` indexed-only route，归入 `/workspace/delivery/`。
- 测试覆盖：`tests.test_delivery_executors`、`tests.test_delivery_tools`、`tests.test_workspace_contract`。

验收口径：

- 默认仍是 dry-run，不产生文件系统副作用。
- `commit_backend_manifest_mutation=true` 的 dry-run 只返回 `backend_manifest_mutation_planned=true`，不会写 mutation 或 patched manifest 文件。
- apply 模式写的是本地 patched copy 与 mutation record，不 in-place 改写源 `workspace/backend-artifact-manifest.json`。
- `backend_manifest_patch_written=true` 不等价于 `backend_manifest_mutated=true`；本阶段仍固定 `backend_manifest_mutated=false`、`external_delivery_performed=false`、`cross_run_transaction_committed=false`。
- 后续仍需 backend manifest in-place mutation policy、cross-run recovery state machine、stronger distributed transaction locking 和外部交付执行器。

### Step 30：Local delivery manifest revision baseline

交付物：

- `DeliveryExecutorConfig.commit_manifest_revision`：默认 `false`，只有显式启用才生成 manifest revision。
- `DeliveryManifestRevision`：记录 transaction id、revision id、delivered artifacts、source artifact count、revision path、`committed`、`dry_run` 和 `backend_manifest_mutated=false`。
- `LocalDeliveryExecutor`：dry-run 下只返回 planned manifest revision，不写文件；apply 成功且 `commit_manifest_revision=true` 时写 `delivery-manifest-revision.json`，并在 `DeliveryTransactionJournal` 中设置 `manifest_revision_committed=true` 与 `manifest_revision_path`。
- `execute_local_delivery` tool：新增 `commit_manifest_revision` 参数。
- `workspace-contract.json`：新增 `workspace/delivery-manifest-revision.json` indexed-only route，归入 `/workspace/delivery/`。
- `tests/test_delivery_executors.py`、`tests/test_delivery_tools.py`、`tests/test_workspace_contract.py`：覆盖默认不提交 revision、dry-run 只计划、apply 显式提交 local manifest revision、tool 参数和 workspace route。

边界：

- 这是 local delivery manifest revision baseline，不改写标准 `workspace/backend-artifact-manifest.json`。
- `manifest_revision_committed=true` 只表示本地 delivery revision artifact 已写入；不代表 cross-run backend manifest mutation、external delivery 或 recovery state machine 已完成。
- 后续仍需 backend manifest mutation policy、cross-run recovery state machine、stronger distributed transaction locking 和外部交付执行器。

验证：

```bash
"./.venv/bin/python" -m unittest tests.test_delivery_executors tests.test_delivery_tools tests.test_workspace_contract -v
```

### Step 29：Local delivery executor contract baseline

交付物：

- `src/reverse_deepagent/delivery/executors.py`：新增 `LocalDeliveryExecutor`、`DeliveryExecutorConfig`、`DeliveryArtifact`、`DeliveryReceipt`、`DeliveryTransactionJournal` 和 `DeliveryExecutionResult`。
- executor 默认 `mode=dry-run`，只生成 planned artifacts、digest、destination 和 next action，不创建 delivery 目录，不写 receipt / journal。
- 显式 `mode=apply` 时，仅把 reviewed filesystem artifacts 复制到本地 delivery 目录，并写入 `delivery-receipt.json` 与 `delivery-transaction-journal.json`。
- `workspace-contract.json`：新增 `workspace/delivery-receipt.json` 与 `workspace/delivery-transaction-journal.json` indexed-only route，归入 `/workspace/delivery/`。
- `tools.delivery_tools` 与 delivery subagent：新增 `execute_local_delivery` tool；delivery prompt 明确默认 dry-run，只有显式 apply 才允许产生本地文件复制副作用。
- `coordinator` artifact category map：为 receipt / journal 预留 `export` category，后续接入 pipeline manifest 时不需要再改分类。
- `tests/test_delivery_executors.py`、`tests/test_delivery_tools.py`、`tests/test_workspace_contract.py`：覆盖 dry-run 无副作用、apply 本地复制并写 receipt / journal、missing required source 阻断，以及 workspace route。

边界：

- 这是 local-filesystem delivery executor contract baseline，不是 external delivery executor；不会发 webhook、上传 release、推送远端或调用第三方发布系统。
- 当前 journal 是未来 cross-run transaction state machine 的输入格式雏形；`manifest_revision_committed=false`，还不提交 manifest revision。
- apply 模式会产生本地文件系统副作用，但只能由显式调用触发；默认 pipeline 不自动调用该 executor。

验证：

```bash
"./.venv/bin/python" -m unittest tests.test_delivery_executors tests.test_workspace_contract -v
```

### Step 28：Final delivery transaction commit record baseline

交付物：

- `FlowTimelineSpec.auto_stitch_transaction_commit_review_decisions`：支持 `auto_stitch_transaction_commit_review_decisions` / `transaction_commit_review_decisions` / `final_delivery_transaction_review_decisions` 等显式审批输入。
- `flow-timeline.json`：新增 `auto_stitch_transaction_commit_review_decisions`、`auto_stitch_transaction_commit_results`、`auto_stitch_transaction_commit_result_count` 和 `auto_stitch_transaction_commit_summary`。
- `FlowTimelineManager`：显式审批通过后，基于 Step 27 final delivery package 生成 `transaction_commit_recorded` result，输出 `workspace/final-delivery-transaction-commit.json` / `virtual://workspace/final-delivery-transaction-commit.json` 的 artifact-model record。
- `NativeWebRuntime`：explicit flow-timeline protection、recon artifact metadata 和 artifact refs 暴露 transaction commit result count / summary；新增 `record_final_delivery_transaction_commit` applied action。
- `workspace-contract.json`：新增 `workspace/final-delivery-transaction-commit.json` indexed-only route，归入 `/workspace/delivery/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖无审批时要求 review、审批后记录 commit result、ArtifactRef、metadata、workspace route，以及 `artifact_model_transaction_commit_recorded=true` 但 `cross_run_transaction_committed=false` / `manifest_revision_committed=false` / `filesystem_artifact_mutated=false` / `external_delivery_performed=false` 边界。

边界：

- 该 baseline 是 explicit-review-only artifact-model transaction commit record，不是 true cross-run transaction commit executor。
- 它不写入真实文件系统 artifact，不提交 manifest revision，不执行 external delivery，也不提供失败恢复状态机。
- 后续仍需补 `TransactionExecutor` / `DeliveryExecutor` contract、durable transaction journal、manifest revision commit、filesystem artifact mutation、failure recovery 和 external delivery executor。

验证：

```bash
git diff --check
"./.venv/bin/python" -m compileall -q "src/reverse_deepagent" "tests"
PYTHONDONTWRITEBYTECODE=1 "./.venv/bin/python" -m unittest \
  tests.test_flow_timeline \
  tests.test_native_web_runtime \
  tests.test_workspace_contract \
  -v
PYTHONDONTWRITEBYTECODE=1 "./.venv/bin/python" -m unittest discover -s tests -v
```

### Step 27：Final delivery package after delivery guard rerun baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_post_standard_review_gate_replacement_final_delivery_packages`、`auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count` 和 `auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary`。
- `FlowTimelineManager`：基于 `delivery_guard_rerun_passed` result 生成 final delivery package baseline，记录 package artifact、included artifacts、final result / manifest links，以及 `package_ready=true` / `final_delivery_packaged=true`。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 final delivery package count / summary；新增 `virtual://workspace/final-delivery-package-after-review-gate-replacement.json` artifact ref；applied action 增加 `package_final_delivery_after_standard_review_gate_replacement`。
- `workspace-contract.json`：新增 `workspace/final-delivery-package-after-review-gate-replacement.json` indexed-only route，归入 `/workspace/delivery/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 guard passed 后派生 final delivery package、ArtifactRef、metadata、workspace route，以及 `automatic_delivery=false` / `external_delivery_performed=false` / `cross_run_transaction_committed=false` 边界。

边界：

- 该 baseline 只说明最终交付包在 artifact model 中已经准备好；不执行外部交付，不提交跨运行 transaction，不写 manifest revision commit。
- `delivery_allowed=true` 与 `final_delivery_packaged=true` 是 package 状态，不等于 `automatic_delivery=true`。
- 后续仍需 cross-run transaction commit hardening、manifest recovery / rollback state machine、失败恢复和 external delivery executor。

### Step 26：Delivery guard rerun after standard review gate replacement baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns`、`auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count` 和 `auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary`。
- `FlowTimelineManager`：基于 `standard_review_gate_replaced` result 生成 post-standard-review-gate-replacement delivery guard rerun baseline，记录 `delivery_guard_rerun_performed=true`、`delivery_guard_passed=true`、`delivery_allowed=true` 和 `automatic_delivery=false`。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 delivery guard rerun count / summary；新增 `virtual://workspace/delivery-guard-after-review-gate-replacement.json` artifact ref；applied action 增加 `rerun_delivery_guard_after_standard_review_gate_replacement`。
- `workspace-contract.json`：新增 `workspace/delivery-guard-after-review-gate-replacement.json` indexed-only route，归入 `/workspace/delivery/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 replacement result 后派生 delivery guard rerun、ArtifactRef、metadata、workspace route，以及 `delivery_allowed=true` / `automatic_delivery=false` / `manual_delivery_required=true` 边界。

边界：

- 该 baseline 只表示标准 review gate replacement 后的 delivery guard 已在本轮 artifact model 中重跑并通过；Step 27 已补 final delivery package baseline，但仍不触发自动交付。
- `delivery_allowed=true` 是 guard 状态，不等价于 `automatic_delivery=true`；Step 27 已补 artifact-model final delivery package，后续仍需 cross-run transaction commit 或 external delivery 动作。
- 跨运行 physical rollback transaction state machine、manifest revision commit、失败恢复、external delivery executor 和无需审批 automatic materializer 仍未实现。

### Step 25：Standard review gate replacement baseline

交付物：

- `FlowTimelineSpec.auto_stitch_standard_review_gate_replacement_review_decisions`：支持 `auto_stitch_standard_review_gate_replacement_review_decisions` / `standard_review_gate_replacement_review_decisions` / `review_gate_replacement_review_decisions` 等显式审批输入。
- `flow-timeline.json`：新增 `auto_stitch_standard_review_gate_replacement_review_decisions`、`auto_stitch_standard_review_gate_replacement_results`、`auto_stitch_standard_review_gate_replacement_result_count` 和 `auto_stitch_standard_review_gate_replacement_summary`。
- `FlowTimelineManager`：在 post-physical-rollback review gate rerun 获得显式 approval 后，记录 `standard_review_gate_replaced` result，并把 rerun 从 blocking 状态转为 review-approved replacement record。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 replacement review decision / result count 和 summary；新增 `virtual://workspace/review-gate-replacement-results.json` artifact ref；applied action 增加 `replace_standard_review_gate_after_physical_rollback`。
- `workspace-contract.json`：新增 `workspace/review-gate-replacement-results.json` indexed-only route，归入 `/workspace/review/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖默认无审批不 replacement、审批后 replacement result、ArtifactRef、metadata、workspace route，以及 `delivery_guard_rerun_required=true` / `delivery_allowed=false` / `automatic_delivery=false` 边界。

边界：

- 该 baseline 只在显式 review approval 后记录标准 `workspace/review-gate.json` artifact model replacement result；delivery guard rerun baseline 已由 Step 26 补齐，但仍不自动交付。
- replacement result 表示本轮 artifact model 进入“标准 gate 已替换，需继续 delivery guard rerun”的状态，不代表跨运行文件系统 patch 或完整 transaction commit。
- Step 26 已实现 delivery guard rerun after standard review gate replacement baseline；Step 27 已补 final delivery package baseline；下一步应考虑 cross-run transaction commit hardening、跨运行 physical rollback transaction state machine、失败恢复和 manifest recovery。

### Step 24：Post-physical-rollback review gate rerun baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_post_physical_rollback_review_gate_reruns`、`auto_stitch_post_physical_rollback_review_gate_rerun_count` 和 `auto_stitch_post_physical_rollback_review_gate_rerun_summary`。
- `FlowTimelineManager`：基于 `physical_rollback_applied` result 生成 post-physical-rollback standard review gate rerun baseline，记录 removed stitched flow、remaining stitched flow、标准 gate artifact 和 replacement blocker。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 rerun count / summary；新增 `virtual://workspace/review-gate-after-physical-rollback.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/review-gate-after-physical-rollback.json` indexed-only route，归入 `/workspace/review/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 physical rollback applied 后派生 blocking gate rerun、ArtifactRef、metadata、workspace route，以及 `does_not_replace_review_gate=true` / `delivery_allowed=false` / `would_replace_review_gate=false` 边界。

边界：

- 该 baseline 只记录标准 review gate 需要 rerun，并输出 `review-gate-after-physical-rollback.json`；不覆盖标准 `workspace/review-gate.json`。
- 默认阻断交付；Step 25 已补 replacement baseline，Step 26 已补 delivery guard rerun baseline，final delivery package baseline 已由 Step 27 补齐，cross-run transaction commit / external delivery executor 仍需后续实现。
- 仍不启用 automatic rollback，不实现跨运行 transaction state machine。

### Step 23：Explicit-review-only physical rollback mutation baseline

交付物：

- `FlowTimelineSpec.auto_stitch_physical_rollback_review_decisions`：支持 `auto_stitch_physical_rollback_review_decisions` / `physical_rollback_review_decisions` 等显式审批输入。
- `flow-timeline.json`：新增 `auto_stitch_physical_rollback_review_decisions`、`auto_stitch_physical_rollback_results`、`auto_stitch_physical_rollback_result_count` 和 `auto_stitch_physical_rollback_result_summary`。
- `FlowTimelineManager`：审批通过后把 physical rollback dry-run diff 转成 `physical_rollback_applied` result，并从本轮 `stitched_flows` artifact model 中移除匹配的 `materialization_result_id` / `plan_id` / `candidate_id` / `group_id` / `entry_sequences`。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 physical rollback result count / summary；新增 `virtual://workspace/stitched-flow-physical-rollback-results.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/stitched-flow-physical-rollback-results.json` indexed-only route，归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖默认无审批不 mutation、审批后 `target_artifact_mutated=true`、`stitched_flow_count=0`、result artifact、workspace route，以及 `automatic_rollback=false` / `would_replace_review_gate=false` 边界。

边界：

- 该 baseline 是 explicit-review-only，不会因为存在 dry-run diff 自动回滚。
- 当前 mutation 发生在本轮 `FlowTimelineResult.stitched_flows` artifact model；真实文件系统双写、manifest revision 状态机、失败恢复和跨运行 artifact patch 仍需后续 transaction state machine。
- Step 24 已补出 post-physical-rollback review gate rerun baseline，Step 25 已补出 explicit-review-only 标准 review gate replacement baseline；cross-run transaction commit / external delivery executor 与跨运行 transaction state machine 仍未实现。

### Step 22：Physical rollback dry-run diff baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_physical_rollback_dry_run_diffs`、`auto_stitch_physical_rollback_dry_run_diff_count` 和 `auto_stitch_physical_rollback_dry_run_diff_summary`。
- `FlowTimelineManager`：基于 logical rollback result 与 post-rollback review gate recomputation 生成 physical rollback dry-run diff，描述待移除 entry、remove selectors、manifest updates 和标准 review gate rerun 要求。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 dry-run diff count / summary；新增 `virtual://workspace/stitched-flow-physical-rollback-diff.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/stitched-flow-physical-rollback-diff.json` indexed-only route，归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 dry-run diff 内容、ArtifactRef、metadata、workspace route，以及 `dry_run_only=true` / `writes_artifact=false` / `target_artifact_mutated=false` 边界。

边界：

- 该 baseline 只输出 would-remove / would-update-manifest / would-rerun-gate 差异计划，不删除、覆盖或改写 `workspace/stitched-flow.json`。
- `would_mutate_if_approved=true` 只表示未来显式审批后的潜在物理动作；当前固定 `writes_artifact=false` / `physical_artifact_mutated=false` / `automatic_rollback=false`。
- 标准 `workspace/review-gate.json` replacement baseline 已由 Step 25 补齐；Step 23 已在 dry-run diff 基础上补出 explicit-review-only artifact model mutation，后续应接 cross-run transaction commit、transaction state machine 与跨运行 artifact patch。

### Step 21：Post-rollback review gate recompute baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_rollback_review_gate_recomputations`、`auto_stitch_rollback_review_gate_recomputation_count` 和 `auto_stitch_rollback_review_gate_recomputation_summary`。
- `FlowTimelineManager`：基于 `logical_revert_recorded` 的 rollback execution result 生成 post-rollback review gate recomputation baseline，默认 `blocked=true` / `delivery_allowed=false`。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 recomputation count / summary；新增 `virtual://workspace/review-gate-after-rollback.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/review-gate-after-rollback.json` indexed-only route，归入 `/workspace/review/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 logical rollback result 触发 recomputation、ArtifactRef、metadata、workspace route，以及 `does_not_replace_review_gate=true` / `delivery_allowed=false` / `target_artifact_mutated=false` 边界。

边界：

- 该 baseline 只是 post-rollback gate recomputation 记录，不覆盖 `workspace/review-gate.json`，也不假装标准 delivery gate 已重新执行。
- recomputation 默认阻断交付，要求 reviewer 确认 logical rollback result、`stitched-flow.json` 当前状态，并重新运行标准 review gate。
- 仍不执行物理 rollback，不改写 `stitched-flow.json`，固定 `automatic_rollback=false` / `target_artifact_mutated=false`。
- Step 22 已补出 physical rollback dry-run diff，Step 23 已补出 explicit-review-only artifact model mutation，Step 25 已补出标准 review gate replacement baseline；cross-run transaction commit / external delivery executor 与 recovery workflow baseline 已补齐；跨运行 physical rollback transaction state machine 与 stronger distributed transaction locking beyond local idempotency guard baseline 仍未实现。

### Step 20：Rollback execution dry-run / explicit-review-only baseline

交付物：

- `FlowTimelineSpec.auto_stitch_rollback_execution_review_decisions`：支持 `auto_stitch_rollback_execution_review_decisions` / `autoStitchRollbackExecutionReviewDecisions` / `rollback_execution_review_decisions` / `stitched_flow_rollback_review_decisions` 等显式审批输入。
- `flow-timeline.json`：新增 `auto_stitch_rollback_execution_plans`、`auto_stitch_rollback_execution_plan_count`、`auto_stitch_rollback_execution_summary`、`auto_stitch_rollback_execution_review_decisions`、`auto_stitch_rollback_execution_review_decision_count`、`auto_stitch_rollback_execution_results`、`auto_stitch_rollback_execution_result_count` 和 `auto_stitch_rollback_execution_result_summary`。
- `FlowTimelineManager`：基于 `rollback_ready` 的 materialization rollback plan 生成默认 dry-run execution plan；只有显式 rollback execution approval 才会记录 logical rollback result。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 rollback execution plan / review / result count 与 summary；新增 `virtual://workspace/stitched-flow-rollback-executions.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/stitched-flow-rollback-executions.json` indexed-only route，归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖默认 dry-run execution plan、显式审批 logical rollback result、ArtifactRef、metadata、workspace route，以及 `automatic_rollback=false` / `automatic_stitching=false` / `target_artifact_mutated=false` 边界。

边界：

- rollback execution plan 默认 `dry_run=true` / `would_revert=false` / `writes_artifact=false`，只提示 reviewer 审批，不执行物理回滚。
- 显式审批后只记录 logical revert result，固定 `physical_artifact_mutated=false` / `target_artifact_mutated=false`；不会删除、覆盖或改写 `workspace/stitched-flow.json`。
- `automatic_rollback=false` / `automatic_stitching=false` 继续保持，不能宣称支持真实自动回滚或自动全链路 stitching。
- Step 21 已在 rollback execution result 基础上输出 post-rollback review gate recompute baseline，Step 22 已输出 physical rollback dry-run diff，Step 25 已输出标准 review gate replacement baseline；真实跨运行 mutation executor、transaction commit 与 external delivery executor 仍未实现。

### Step 19：Materialization transaction log baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_materialization_transactions`、`auto_stitch_materialization_transaction_count` 和 `auto_stitch_materialization_transaction_summary`。
- `FlowTimelineManager`：把 review-approved materialization result、audit entry、rollback plan 和 conflict resolution 聚合为 transaction-log-only 记录，包含 stage 状态、integrity links、source artifacts 和 review metadata。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 transaction count / summary；新增 `virtual://workspace/stitched-flow-materialization-transactions.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/stitched-flow-materialization-transactions.json` indexed-only route，归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 transaction record、summary、ArtifactRef、metadata、workspace route，以及 `transaction_log_only=true` / `automatic_rollback=false` / `automatic_stitching=false` 边界。

边界：

- transaction log 是聚合视图，不执行 rollback，不删除或改写 `stitched-flow.json`。
- transaction ready 只表示 result / audit / rollback plan 三段引用完整，不代表可以自动交付。
- rollback 后 post-rollback review gate recompute baseline 已由 Step 21 补齐，标准 `review-gate.json` replacement baseline 已由 Step 25 补齐；cross-run transaction commit / external delivery executor 仍未实现。
- Step 20 已在这个 transaction log 基础上补出 rollback executor dry-run / explicit-review-only baseline，Step 21 已补出 post-rollback review gate recompute baseline，Step 22 已补出 physical rollback dry-run diff，Step 25 已补出标准 review gate replacement baseline；真实跨运行物理 mutation、transaction commit 与 external delivery executor 仍未实现。

### Step 18：Auto-stitch conflict resolver baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_conflict_resolutions`、`auto_stitch_conflict_resolution_count` 和 `auto_stitch_conflict_resolution_summary`。
- `FlowTimelineManager`：基于 dry-run `conflict_reasons` 生成 review-only resolution 记录，包含 selected candidate、alternative candidates、unresolved conflicts 和 next action。
- `NativeWebRuntime`：explicit flow-timeline protection 与 recon artifact metadata 暴露 conflict resolution count / summary；新增 `virtual://workspace/auto-stitch-conflict-resolutions.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/auto-stitch-conflict-resolutions.json` indexed-only route，归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 resolver 记录、summary、ArtifactRef、metadata、workspace route，以及 `would_materialize=false` / `automatic_stitching=false` 边界。

边界：

- resolver 是冲突复核辅助，不是自动决策器；`resolved_conflicts` 当前保持空，冲突仍进入 `unresolved_conflicts` 等待 review。
- review-preferred candidate 只用于人工审查排序，不会自动 materialize。
- 仍不支持无需审批的自动全链路 stitching、真实 rollback executor 或 transaction log 聚合。
- 后续仍需把 conflict resolution 与 rollback executor、transaction log 和 physical rollback dry-run diff、标准 review gate 替换式重算串成完整状态机。

### Step 17：Materialization audit / rollback writer baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_materialization_audit_entries`、`auto_stitch_materialization_audit_count`、`auto_stitch_materialization_audit_summary`、`auto_stitch_materialization_rollback_plans`、`auto_stitch_materialization_rollback_plan_count` 和 `auto_stitch_materialization_rollback_summary`。
- `FlowTimelineManager`：只对 `status=materialized` 且 `materialized=true` 的 review-approved materialization result 生成审计记录和回滚计划；rejected / skipped_duplicate 不伪造写入审计。
- `NativeWebRuntime`：explicit flow-timeline protection 和 recon artifact metadata 暴露 audit / rollback count 与 summary；新增 `virtual://workspace/stitched-flow-materialization-audit.json` 和 `virtual://workspace/stitched-flow-rollback-plan.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/stitched-flow-materialization-audit.json` 与 `workspace/stitched-flow-rollback-plan.json` indexed-only route，仍归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 audit entry、rollback plan、ArtifactRef、metadata、workspace route，以及 `automatic_stitching=false` / `automatic_rollback=false` 边界。

边界：

- audit 是 materialization 写入行为的机器可读日志，不会把 plan-only / rejected 记录伪装成已写入。
- rollback 当前只生成人工复核计划，固定 `writes_artifact=false` / `would_revert=false` / `automatic_rollback=false`，不执行自动回滚。
- 仍不支持无需审批的自动全链路 stitching。
- 后续仍需更完整的 conflict resolver、真实 rollback executor、transaction log 聚合，以及 rollback 后 review gate 自动重算。

### Step 16：Review-approved auto-stitch materializer skeleton

交付物：

- `FlowTimelineSpec.auto_stitch_materialization_review_decisions`：支持 `auto_stitch_materialization_review_decisions` / `autoStitchMaterializationReviewDecisions` / `auto_stitch_materialization_plan_review_decisions` 等显式审批输入。
- `flow-timeline.json`：新增 `auto_stitch_materialization_review_decisions`、`auto_stitch_materialization_review_decision_count`、`auto_stitch_materialization_results`、`auto_stitch_materialization_result_count` 和 `auto_stitch_materialization_result_summary`。
- `FlowTimelineManager`：只在 materialization plan 获得显式 approval 后，生成 review-approved materialization result，并把它转成 `stitched_flows` baseline；rejected decision 不 materialize。
- `NativeWebRuntime`：explicit flow-timeline protection 和 recon artifact metadata 暴露 materialization review / result count 与 summary；新增 `virtual://workspace/auto-stitch-materialization-results.json` artifact ref。
- `workspace-contract.json`：新增 `workspace/auto-stitch-materialization-results.json` indexed-only route，仍归入 `/workspace/timeline/`。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`：覆盖 approved / rejected materialization review decision、ArtifactRef、metadata、workspace route，以及 `automatic_stitching=false` 边界。

边界：

- 无显式 `auto_stitch_materialization_review_decisions` approval 时，plan 仍保持 `writes_artifact=false` / `would_materialize=false`。
- 该路径不替代 `stitch_review_decisions`，也不绕过 review gate；它只是把 Step 15 的 plan-only 记录接入一个 explicit-review-only materializer skeleton。
- 生成的 stitched flow 仍标记 `automatic_stitching=false`，不能宣称已支持无需审批的自动全链路 stitching。
- 后续仍需更完整的 conflict resolver、真实 rollback executor、transaction log 聚合，以及真正自动化策略的默认关闭 gate。

### Step 15：Auto-stitch materialization plan baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_materialization_plans`、`auto_stitch_materialization_plan_count` 和 `auto_stitch_materialization_summary`。
- `FlowTimelineManager`：对 policy-eligible decision 生成 plan-only materialization record，包含 target artifact、entry sequences、path、review requirements、conflict resolution、rollback plan 和 blocking conditions。
- `NativeWebRuntime`：explicit flow-timeline protection 和 recon artifact metadata 暴露 materialization plan count / summary。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`：覆盖默认无 plan、显式 allow-conflicts 策略生成 plan-only 记录，以及 `writes_artifact=false` / `would_materialize=false` / `automatic_stitching=false` 边界。

边界：

- materialization plan 只描述未来如何写入，不实际写 `stitched-flow.json`。
- 不替代 `stitch_review_decisions` 审批路径。
- 后续仍需更完整的 conflict resolver、真实 rollback executor、transaction log 聚合，以及无需审批自动化策略的默认关闭 gate。

### Step 14：Auto-stitch policy decision gate baseline

交付物：

- `FlowTimelineSpec.auto_stitch_policy`：支持 `auto_stitch_policy` / `autoStitchPolicy` 等上下文输入。
- `flow-timeline.json`：新增 `auto_stitch_policy_decisions`、`auto_stitch_policy_decision_count` 和 `auto_stitch_policy_summary`。
- `NativeWebRuntime`：explicit flow-timeline protection 和 recon artifact metadata 暴露 policy decision count / summary。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`：覆盖默认保守阻断、显式 allow-conflicts 策略进入 review gate、automatic materialization request 被结构化标记为 not implemented，以及 `would_materialize=false` / `automatic_stitching=false` 边界。

边界：

- policy decision 只做 gate，不直接 materialize。
- `enable_automatic_materialization=true` 只会生成 `automatic_materialization_not_implemented` blocker，当前不会自动生成 `stitched-flow.json`。
- 真正自动全链路 materialization 仍需后续实现 materializer、conflict resolver 和 review / rollback policy。

### Step 13：Auto-stitch dry-run scoring baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_dry_runs` 与 `auto_stitch_dry_run_count`。
- `FlowTimelineManager`：对 manual-only `stitch_candidates` 做 deterministic dry-run scoring，输出 confidence、score reasons、conflict reasons 和 blockers。
- `NativeWebRuntime`：在 explicit `flow-timeline` protection 和 recon artifact metadata 中暴露 dry-run count。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`：覆盖 ready / reviewable candidate 的 dry-run 记录、conflict reason、blocking conditions，以及 `would_materialize=false` / `automatic_stitching=false` 边界。

边界：

- dry-run 只辅助 review，不自动 materialize。
- 不生成 `stitched-flow.json`。
- 不绕过 review gate。
- `automatic_stitching`、`stitching`、`would_materialize` 默认保持 false；真正自动全链路 materialization 仍是后续 capability-gated 工作。

### Step 12：BrowserProvider smoke matrix / lifecycle baseline

交付物：

- `src/reverse_deepagent/browser/smoke.py`：BrowserProvider smoke matrix 与 lifecycle normalization。
- `reverse-agent-doctor --browser-provider-matrix`：输出内置 provider 的 metadata-only matrix，不导入可选浏览器二进制、不探测 CDP endpoint、不启动浏览器、不依赖 MCP。
- `browser_provider.smoke_matrix`：单 provider doctor 输出保留旧字段，同时嵌入标准 lifecycle row。
- `workspace/browser-provider-smoke.json`：已在 workspace contract 中登记为未来 runtime artifact route，当前不迁移既有输出。

边界：

- metadata matrix 默认 side-effect-free。
- availability check 和真实 launch smoke 必须显式请求。
- `--launch-browser-smoke` 仍是唯一允许 doctor 打开真实 provider session 的路径。

### Step 11：DeepAgents workspace contract indexed-only baseline

交付物：

- `src/reverse_deepagent/workspace_contract.py`：纯 Python contract，覆盖 virtual folders、subagent roles、middleware chain 和 existing artifact route index。
- `workspace/workspace-contract.json`：Web pipeline 与 platform-neutral pipeline 均会输出。
- `workspace_workspace_contract` manifest key：进入 `workspace/backend-artifact-manifest.json`，category 为 `workspace`。
- `tests/test_workspace_contract.py`：覆盖 JSON 序列化、角色边界、中间件顺序、artifact route 和两条 pipeline 输出。

边界：

- indexed-only，不迁移既有 `workspace/*.json` 扁平路径。
- `future_path` 在 Step 11 只表示后续虚拟文件夹目标；Step 46 已补 backend manifest 的 manifest-only `workspace_alias`。
- 后续物理移动 / 重命名 artifact 或 dual-write 必须继续提供 compatibility alias、manifest 覆盖和回归测试。

### Step 10.1：Runtime backend entry-point discovery baseline

交付物：

- `RuntimeBackendRegistry.load_entry_points()`：加载 `reverse_deepagent.runtime_backends` Python entry-point group
- `RUNTIME_BACKEND_ENTRY_POINT_GROUP`：公开 entry-point group 常量
- `build_default_runtime_registry(include_entry_points=True, include_legacy_mcp=True)`：默认加载外部 backend registration，同时保留测试用确定性开关和不带 MCP backend 的 clean registry 开关
- registry 硬约束：`RuntimeBackendRegistration.backend_id` 必须与 `RuntimeBackendCapabilities.backend_id` 一致
- 单测覆盖：entry-point registration、callable 多 registration、invalid payload、load error、factory 不在 metadata listing 阶段调用

边界：

- legacy MCP factory、`JSReverserMcpConfig` 和 stdio bridge 实现已从 core fallback 移到 optional package；core 只保留 shim / warning / doctor proxy / install guidance
- entry-point loading 可以 import 插件 Python 代码，但不得启动浏览器、MCP、设备工具或网络会话
- backend factory 仍只在显式 `build_runtime(...)` / `registry.create(...)` 时调用
- `legacy-mcp` registration / factory / alias warning 已迁到 `reverse_deepagent.runtime.legacy_mcp`；coordinator 只消费 registration provider
- `packages/reverse-deepagent-legacy-mcp/` 已声明 optional plugin package 和 `legacy-mcp = reverse_deepagent_legacy_mcp:runtime_backend_registration` entry point，并拥有 legacy MCP registration / factory、config 和 stdio bridge 实现
- 外部 `legacy-mcp` entry point 是 legacy MCP backend 的支持安装路径，避免 core 重新耦合 MCP 实现
- core `reverse_deepagent.runtime.legacy_mcp` 现在提供 shim、默认命令常量、alias warning、doctor proxy、plugin delegation 和 structured install guidance；缺 optional package 时不会注册 legacy MCP backend，也不会启动 stdio MCP transport

### Step 5.1：完成 CloakBrowser provider skeleton

交付物：

- `src/reverse_deepagent/browser/providers/cloakbrowser.py`
- `tests/test_cloakbrowser_provider.py`
- `docs/runtime/cloakbrowser-provider.md`
- `pyproject.toml` optional extra：`.[cloak]`
- CLI 参数：`--browser-humanize`、`--browser-proxy`、`--browser-geoip`、`--browser-locale`、`--browser-timezone`

验收：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m compileall -q "src/reverse_deepagent" "tests"
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest \
  tests.test_browser_provider_contract \
  tests.test_browser_provider_registry \
  tests.test_playwright_session \
  tests.test_playwright_provider \
  tests.test_cloakbrowser_provider \
  tests.test_browser_collectors \
  tests.test_native_web_runtime \
  tests.test_runtime_registry \
  tests.test_run_demo_chrome_lifecycle \
  tests.test_console_script \
  -v
git diff --check
```

完成条件：review diff 后提交 `Add CloakBrowser provider skeleton`。

### Step 6：实现 browser-provider doctor mode

目标：把 MCP doctor 和 BrowserProvider doctor 拆开。

交付物：

- `reverse-agent-doctor --browser playwright-chromium`
- `reverse-agent-doctor --browser cloakbrowser`
- 可选 `--launch-browser-smoke`，默认不启动浏览器。

验收：

- 缺 Playwright / CloakBrowser 时返回结构化安装建议。
- provider metadata 检查不启动浏览器。
- proxy 等敏感配置不出现在输出里。
- browser-only doctor 不依赖 `jsreverser-mcp` 或 Chrome debug 静态检查。
- `--launch-browser-smoke` 是唯一会真实启动 provider 的路径。

### Step 7：补齐 native artifact parity

目标：让 native-web 输出的 evidence 能完整落盘。

交付物：

- `workspace/dom-snapshot.json`
- `workspace/console-messages.json`
- `workspace/script-inventory.json`
- `workspace/navigation-events.json`
- manifest 中标明 `producer_backend=native-web` 和 `browser_provider`。

验收：

- fake provider pipeline 能生成上述 artifact。
- legacy MCP 原有 artifact 不回退。
- README / runtime docs 更新 artifact 口径。

### Step 8：CDP-enhanced collectors

目标：补齐 MCP 之前最有价值的深采集能力。

交付物：

- request initiator collector
- response body metadata collector
- script source cache collector
- WebSocket frame collector
- script source inventory fallback
- WebSocket hook timeline fallback

验收：

- provider 支持 CDP 时输出增强 artifact。
- CDP event cache 缺失时，script source 和 hook-observed WebSocket frame 仍能尽量输出结构化 evidence。
- provider 不支持 CDP 时输出 `unsupported` evidence，不失败整个 recon。

### Step 9：Hook / breakpoint migration

目标：把常用注入、hook、breakpoint 能力从 MCP tool 迁到项目内。

交付物：

- fetch/xhr hook
- cookie write hook
- WebSocket send/message hook
- minimal anti-debug preload patches
- breakpoint manager with capability gate
- `virtual://workspace/breakpoints.json` protection artifact ref / evidence mapping

验收：

- hook 输出归一化 evidence。
- breakpoint 请求只在明确 protection/context 下触发，不作为默认 recon 副作用。
- patch 行为可审计、可关闭。
- 不把 target-specific hack 写死进通用 runtime。

### Step 10：MCP legacy downgrade

目标：MCP 从默认心智模型降级成兼容后端，并对旧 alias 给出明确迁移提示。

交付物：

- `legacy-mcp` backend id 文档化。
- `mcp` / `jsreverser-mcp` alias 标注 temporary compatibility，并在 CLI 中输出 deprecation warning。
- MCP smoke 文档移到 legacy section。
- public quickstart 默认推荐 `native-web` 或 `mock`，不推荐 MCP。
- 兼容 alias 仍可运行，但新文档 / 新脚本必须改用 `legacy-mcp`。

验收：

- 干净环境不装 MCP 也能跑 native quickstart / mock tests。
- 需要 MCP 的用户仍有清晰迁移说明。

### Step 97 execution record: Runtime context stability diff baseline

Status: implemented as a provider-neutral pure-Python analysis baseline, not a browser context collector or runtime executor.

`reverse_deepagent.strategies.runtime_context_diff` now exposes `RuntimeContextSample`, `diff_runtime_context_samples(...)`, and `diff_runtime_context_payload(...)`. The diff flattens captured runtime context samples, ignores sampling metadata such as `sample_index` / `collected_at_ms`, classifies fields as `stable`, `volatile`, `session_bound`, `missing_in_some_samples`, `type_drift`, or `object_drift`, and emits summary counts plus review hints for downstream rebuild / review consumers.

The legacy JSReverser runtime now delegates `workspace/runtime-context-diff.json` generation to this shared analyzer while preserving existing compatibility fields such as `status=multi_sample|single_sample`, `stable_keys`, `volatile_keys`, `missing_requirements`, and `changes`. Secret-like paths containing token / cookie / csrf / session / auth / key / password / credential markers are redacted in previews and legacy change values, keeping only type, length, and digest-style evidence.

Boundary: this baseline does not collect browser context, start BrowserProvider sessions, call MCP, write workspace artifacts by itself, execute replay, prove pure rebuild readiness, or touch Android / iOS / mini-program full runtime chains. Existing runtime collectors remain responsible for gathering samples; rebuild / review gates remain responsible for deciding whether volatile or session-bound inputs are acceptable.

Tests cover stable / volatile classification, session-bound secret redaction, volatile secret redaction in legacy change values, missing-field detection, type drift, object drift, payload-helper compatibility, and legacy runtime adapter compatibility.

### Step 98 execution record: Runtime-context-driven rebuild review hints baseline

Status: implemented as rebuild review metadata, not a rebuild readiness override, runtime collector, or delivery gate bypass.

`build_rebuild_bundle(...)` now builds a `runtime_context_diff` review surface from an explicit `runtime_context_diff` evidence item when present, or from the captured `runtime_context` payload through `diff_runtime_context_payload(...)` when no explicit diff evidence exists. The generated rebuild plan embeds this diff under `runtime_context_diff` so rebuild reviewers and subagents can inspect the exact stability classifications used for hints.

`review_hints` now consume runtime-context diff field classifications. The existing `volatile_runtime_context` hint is preserved and enriched with field-count evidence. New hints cover `session_bound_runtime_context`, `missing_runtime_context_field`, `runtime_context_type_drift`, and `runtime_context_object_drift`, giving generated rebuild artifacts explicit review guidance for session-bound constants, missing samples / requirements, type drift, and nested object / array shape drift.

Boundary: these hints do not change the authoritative `ready` calculation, do not mutate generated code, do not collect browser context, do not execute replay, do not bypass manual review or delivery gates, and do not touch Android / iOS / mini-program full runtime chains. They are review metadata for humans, CI gates, and rebuild / review subagents.

Tests cover session-bound hint generation from raw runtime-context samples, volatile hint generation from derived diff payloads, explicit diff evidence for missing / type-drift / object-drift hints, and existing rebuild artifact regressions.

### Step 99 execution record: Protected-flow triage hook planner baseline

Status: implemented as a plan-only strategy / rebuild guidance baseline, not a hook executor, anti-debug patcher, WASM binary inspector, VM semantics engine, or runtime collector.

`reverse_deepagent.strategies.protected_flow_planner` now exposes `ProtectedFlowTriagePlan` and `build_protected_flow_triage_plan(...)`. The existing `protected_flow_triage` detector attaches `triage_hook_plan` to triage-only strategies for WASM, VM / obfuscation, anti-debug, and dynamic-secret findings. The plan emits hook/debugger candidates, planned workspace artifacts, review hints, safe finding summaries, and an explicit side-effect policy showing that hooks are not installed, runtime is not patched, browsers are not started, MCP is not called, target code is not executed, and mobile full runtime chains are not touched.

Rebuild plans now carry this protected-flow `triage_hook_plan` inside `runtime_assisted`, and the not-ready rebuild README lists plan-only hook/debugger candidates plus planned artifacts for reviewer handoff. The workspace contract indexes `workspace/protection-triage-hooks.json`, `workspace/wasm-runtime-candidates.json`, and `workspace/vm-dispatcher-candidates.json` under their future virtual folders without changing existing canonical flat artifact paths.

Boundary: this is a reviewable planner only. It does not implement automatic WASM import/export inspection, execution-style custom loader traversal, async chunk loading / traversal, execution-style module federation analysis, closure wrapper replacement, JS heap mutation audit, automatic hook installation, automatic anti-debug neutralization, or Android / iOS / mini-program full runtime chains.

Tests cover protected-flow strategy hook-plan output, rebuild runtime-assisted plan / README propagation, workspace route indexing, and existing protected-flow / rebuild regressions.

### Step 100 execution record: Strategy evidence scoring baseline

Status: implemented as provider-neutral review metadata, not a readiness override, runtime collector, replay executor, or review-gate bypass.

`reverse_deepagent.strategies.evidence_scoring` now exposes `StrategyEvidenceScore` and `build_strategy_evidence_score(...)`. Detector strategies keep their existing `confidence` / `confidence_score` compatibility fields and additionally carry `evidence_score`. Rebuild plans also embed `evidence_score`, combining detector confidence, strategy support, validation readiness, replay URL availability, pure or context-aware extraction state, runtime-context diff classifications, protected-flow triage state, and final rebuild readiness into a compact score, label, signals, blockers, components, and recommended next action.

The scoring labels are intentionally review-facing: `strong_pure_candidate`, `reviewable_candidate`, `needs_more_evidence`, and `runtime_assisted_required`. Protected-flow strategies recommend reviewed runtime triage hooks before porting; volatile or missing runtime context recommends collecting or dynamically binding context; strong pure candidates recommend reviewing generated pure rebuild artifacts before delivery.

Boundary: this score is advisory only. It does not change the authoritative `ready` calculation, does not collect runtime context, does not execute replay, does not start BrowserProvider sessions, does not call MCP, does not install hooks, does not mutate generated code, and does not touch Android / iOS / mini-program full runtime chains.

Tests cover strong pure strategy scoring, runtime-context drift scoring, protected-flow runtime-assisted scoring, detector payload compatibility, and rebuild-plan propagation.

### Step 101 execution record: BrowserProvider compatibility rule catalog baseline

Status: implemented as metadata-only provider compatibility rule evolution, not a runtime smoke, browser launcher, or provider-specific integration.

`reverse_deepagent.browser.smoke` now exposes a serializable `BrowserProviderCompatibilityRule` catalog through `list_browser_provider_compatibility_rules()`. The existing `validate_browser_provider_capability_compatibility(...)` API keeps its compatibility fields while evaluating declarative rules and returning `rule_count`, `evaluated_rule_count`, and `evaluated_rules`. Browser provider matrix payloads now include `compatibility_rules` so doctor / CI output can show which metadata-only rules were used without invoking provider factories.

The catalog preserves existing checks for debugger/CDP, persistent-context lifecycle, response body / request initiator / WebSocket frame capture, runtime eval transport, script source acquisition, CDP lifecycle, managed-browser launch, and capabilities-without-lifecycle. It also adds baseline rules for newer provider flags: humanized input and mobile emulation should expose Playwright or CDP page-control transport, extensions should have launch or persistent-context control, and provider-level proxy configuration should have launch control or a managed-browser service.

Boundary: this is metadata validation only. It does not import optional browser SDKs, call provider factories for external plugins, probe CDP endpoints, start browsers, install hooks, collect Web artifacts, or touch Android / iOS / mini-program full runtime chains. Real third-party BrowserProvider plugins may still add provider-specific rules later when they introduce new capability flags.

Tests cover rule catalog serialization, metadata matrix rule export, legacy compatibility errors, new humanize / mobile emulation / extension / proxy warnings, and side-effect-free matrix behavior.

### Step 102 execution record: Functional external BrowserProvider fixture plugin baseline

Status: implemented as a functional optional BrowserProvider plugin package for CI / contract smoke, not a production anti-detect browser, hosted browser service, or real target browser runtime.

`packages/reverse-deepagent-browser-provider-fixture/` now declares the `reverse_deepagent.browser_providers` entry point `fixture-browser = reverse_deepagent_browser_provider_fixture:browser_provider_registration`. Its registration returns non-secret `BrowserProviderCapabilities`, aliases `fixture` and `ci-browser-fixture`, and a delayed provider factory. Registry metadata listing and metadata matrix construction do not call the factory.

Unlike the template package, the fixture provider is runtime-functional: `is_available()` returns true, `start()` and `connect()` return an in-memory provider-neutral `FixtureBrowserSession`, and the session exposes deterministic `BrowserPageRef`, `new_page`, `get_active_page`, `goto`, `title`, `content`, `evaluate`, `screenshot`, and `close` behavior. This proves that an external package can be discovered, compatibility-checked, factory-created, and launch-smoked through the same BrowserProvider contract without adding core runtime branches.

Boundary: this fixture provider does not launch a real browser, import Playwright, probe CDP, provide stealth / fingerprint behavior, capture network events, install hooks, call MCP, or touch Android / iOS / mini-program full runtime chains. Production third-party providers such as vendor anti-detect browsers or hosted browser services remain provider-specific follow-up packages.

Tests cover the pyproject entry point, dependency declaration, side-effect-free registration metadata, delayed factory invocation, registry alias resolution, metadata matrix compatibility, functional start / connect sessions, page operations, provider stop behavior, and launch smoke through `browser_provider_smoke_row(...)`.

### Step 103 execution record: Workspace artifact reader resolver baseline

Status: implemented as read-only resolver-backed artifact consumption, not physical path migration, default dual-write, or canonical path replacement.

`reverse_deepagent.tools.artifact_tools` now exposes `make_read_workspace_artifact_tool(...)`. The tool reads workspace artifacts by artifact key, legacy `workspace/*.json` path, future `/workspace/<area>/...` path, `virtual://workspace/...` URI, or artifact-root-relative fallback path. It uses `WorkspacePathResolver` to inspect legacy and future paths while keeping legacy flat paths authoritative.

The coordinator and read-only review/rebuild/timeline/hook/debugger subagents now include `read_workspace_artifact`, so subagents can fetch existing workspace artifacts before applying their specialized JSON review tools.

Boundary: this is read-only. It does not write artifacts, create directories, move files, enable dual-write, change canonical paths, start browsers, call MCP, or touch Android / iOS / mini-program full runtime chains. Physical folder migration remains deferred until broader resolver adoption and compatibility-informed migration planning are in place.

Tests cover key / legacy / future / virtual URI reads, dual-write future path fallback, direct relative fallback, missing path diagnostics, side-effect policy, and subagent tool exposure.

### Step 104 execution record: Review helper artifact-ref resolver adoption baseline

Status: implemented as read-only artifact-ref inputs for specialized review helpers, not delivery-path mutation, physical folder migration, or automatic artifact materialization.

`read_workspace_artifact_payload(...)`, `load_workspace_artifact_json_object(...)`, and `summarize_workspace_artifact_read(...)` now provide reusable resolver-backed loading for tools that need a JSON object from the workspace. The existing `read_workspace_artifact` tool delegates to the same helper, keeping key / legacy path / future path / `virtual://workspace/...` URI / artifact-root-relative behavior consistent.

The read-only `review_flow_timeline`, `review_hook_artifacts`, `review_debugger_artifacts`, `review_rebuild_artifacts`, and `evaluate_delivery_review_gate` tools now accept artifact-ref inputs in addition to their original JSON string inputs. Subagent builders pass the configured artifact root into these helpers, and review outputs include compact `artifact_input` diagnostics with resolved path, checked paths, content type, and resolution metadata.

Boundary: this does not change review decisions, execute delivery, write artifacts, enable dual-write, migrate workspace paths, start browsers, call MCP, install hooks, resume debuggers, run replay code, or touch Android / iOS / mini-program full runtime chains. Delivery apply paths and physical foldered-canonical migration remain separate follow-ups.

Tests cover artifact-ref reads for timeline, hook, debugger, rebuild, and review gate helpers while preserving existing JSON-input behavior and read-only side-effect policies.

### Step 105 execution record: Delivery artifact-list resolver adoption baseline

Status: implemented as delivery artifact list normalization for reviewed local delivery inputs, not a bypass of apply-mode side-effect gates or physical workspace migration.

`execute_local_delivery` now accepts an optional `artifact_root` and lets each artifact entry provide `source_artifact_ref` or `artifact_ref` instead of `source_path`. The tool resolves those refs through the same workspace resolver reader before constructing `DeliveryArtifact` objects, infers the artifact key from the route when omitted, and preserves compact resolver diagnostics under artifact metadata. Existing `source_path` inputs remain supported, and providing both `source_path` and `source_artifact_ref` is rejected.

The delivery subagent passes the configured artifact root into `make_local_delivery_executor_tool(...)`, so default agent wiring resolves workspace refs relative to the same artifact root used by the rest of the pipeline.

Boundary: this does not change `LocalDeliveryExecutor` apply semantics. Dry-run remains side-effect-free, apply still requires explicit `mode=apply` and all existing delivery / manifest / transaction / lock gates, and external delivery duplicate / review gates remain unchanged. It does not enable dual-write, migrate physical workspace paths, start browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

Tests cover dry-run and explicit apply delivery from `source_artifact_ref`, including metadata diagnostics and unchanged local delivery side-effect behavior.

### Step 106 execution record: Workspace resolver compatibility metrics baseline

Status: implemented as read-only resolver usage diagnostics attached to workspace artifact reads, not physical migration, default dual-write, migration automation, or delivery gate relaxation.

`read_workspace_artifact_payload(...)` now emits `resolver_metrics` for found, missing, and UTF-8 error reads. The metrics classify the requested ref shape, resolution status, resolved artifact key, checked path count, hit path kind, legacy / future path checks, future-path fallback usage, direct-path fallback usage, canonical-path authority, missing state, and read-only policy.

`summarize_workspace_artifact_read(...)` includes those metrics, so specialized review helper `artifact_input` diagnostics and delivery artifact metadata inherit the same compatibility evidence without exposing artifact content.

Boundary: metrics are local read diagnostics only. They do not write audit artifacts, create directories, enable dual-write, change canonical paths, migrate files, start browsers, call MCP, perform delivery, or touch Android / iOS / mini-program full runtime chains. They are intended to inform later alias adoption, opt-in dual-write expansion, and any future foldered-canonical migration pilot.

Tests cover legacy canonical hits, future foldered fallback hits, direct relative fallback hits, missing resolved artifacts, and compact summary propagation.

### Step 107 execution record: Workspace consumer adoption audit baseline

Status: implemented as a read-only consumer matrix for workspace artifact-ref adoption, not broader resolver adoption, path migration, dual-write expansion, or delivery gate relaxation.

`reverse_deepagent.tools.artifact_tools` now exposes `audit_workspace_artifact_consumers_payload(...)` and `make_audit_workspace_artifact_consumers_tool(...)`. The audit classifies known workspace and path consumers as `resolver-ready`, `partial`, `candidate`, `explicit-filesystem-boundary`, or `non-workspace-input`, with owner, tool, input names, current support, rationale, and next action.

The default coordinator toolset now includes `audit_workspace_artifact_consumers`, giving the agent a side-effect-free way to inspect remaining adoption candidates before proposing alias expansion. Current follow-up candidates include `execute_local_delivery` source path usage monitoring; `build_rebuild_delivery` artifact-ref inputs are closed by Step 108; delivery resume / transition / recovery / rollback backend-manifest paths and review approval roots are explicitly marked as filesystem safety boundaries.

Boundary: this is an audit surface only. It does not inspect files, write artifacts, create directories, enable dual-write, migrate paths, start browsers, call MCP, execute delivery, mutate manifests, record approvals, or touch Android / iOS / mini-program full runtime chains. It is intended to prevent accidental resolver expansion across apply-time safety gates while guiding later targeted adoption.

Tests cover the audit payload, side-effect policy, candidate / partial / explicit-boundary classification, and coordinator smoke compatibility.

### Step 108 execution record: Rebuild generation artifact-ref input adoption baseline

Status: implemented as resolver-backed input loading for rebuild generation, not delivery execution, manifest mutation, physical workspace migration, or review-gate bypass.

`build_rebuild_delivery(...)` now accepts `task_card_artifact_ref` and `final_result_artifact_ref` in addition to the existing `task_card_json` and `final_result_json` string inputs. The new artifact-ref inputs are mutually exclusive with their JSON-string counterparts and are loaded through the shared workspace resolver, so callers can pass `workspace_task_card`, `workspace_final`, legacy paths, future paths, or `virtual://workspace/...` URIs.

The tool still writes only the existing rebuild outputs under `artifact_root/rebuild` and `workspace/rebuild-plan.json`. Its return payload now includes compact `artifact_input` diagnostics for the task card and final result reads, including resolver metrics when artifact refs are used. The workspace consumer audit now marks `rebuild.build_rebuild_delivery` as `resolver-ready` instead of `candidate`.

Boundary: this does not execute local delivery, external delivery, replay scripts, Scrapy, backend manifest mutation, transaction commit, rollback, recovery, approval recording, dual-write expansion, physical migration, browser startup, MCP calls, or Android / iOS / mini-program full runtime chains.

Tests cover artifact-ref based rebuild generation, artifact input diagnostics, ambiguous JSON plus artifact-ref rejection, updated consumer audit classification, and existing rebuild / workspace regressions.

### Step 109 execution record: Delivery source path compatibility audit baseline

`execute_local_delivery` now emits a read-only `delivery_artifact_source_audit` summary and per-artifact `metadata.delivery_source_audit` records. The audit distinguishes resolver-backed `source_artifact_ref` / `artifact_ref` inputs from retained `source_path` inputs, classifies legacy workspace paths, future workspace paths, artifact-root-relative paths, relative filesystem paths, and external filesystem source paths, and reports source usage counts without changing delivery behavior.

`audit_workspace_artifact_consumers` still marks `delivery.execute_local_delivery.artifacts_json` as `partial` because explicit `source_path` remains supported for backward compatibility and non-workspace files, but its current support now includes source compatibility metrics. This is an audit / monitoring baseline only: it does not remove `source_path`, does not create directories, does not enable dual-write, does not migrate workspace paths, does not weaken delivery gates, does not start browsers, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains.

Tests cover resolver-backed artifact refs, legacy workspace `source_path`, external filesystem `source_path`, top-level source usage counts, per-artifact metadata classification, and the updated workspace consumer audit next action.

### Step 110 execution record: Workspace migration readiness report baseline

The coordinator now exposes `assess_workspace_migration_readiness`, a read-only workspace migration readiness report. It combines `audit_workspace_artifact_consumers`, registered workspace route counts, and optional `execute_local_delivery` `delivery_artifact_source_audit` JSON into a machine-readable `reverse-deepagent.workspace-migration-readiness.v1` payload.

The report deliberately separates `limited_dual_write_pilot` from `foldered_canonical_migration`. A limited dual-write pilot can be `ready_for_review` when no candidate consumers remain and legacy canonical paths stay authoritative. Foldered-canonical migration remains `blocked` while partial consumers exist, delivery source audit evidence is missing or malformed, retained `source_path` usage is observed, or external filesystem delivery sources remain explicit boundaries.

Boundary: this is audit / planning only. It does not inspect files, write artifacts, create directories, enable dual-write, migrate workspace paths, change canonical paths, start browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

Tests cover missing delivery source audit evidence, observed `source_path` / external filesystem source usage, side-effect policy, coordinator tool exposure, and existing workspace / rebuild regressions.

### Step 111 execution record: Limited workspace dual-write pilot plan baseline

The coordinator now exposes `plan_workspace_dual_write_pilot`, a read-only plan-only tool for narrowing the next dual-write action after migration readiness review. It uses the workspace migration readiness report, registered workspace routes, and optional explicit artifact keys to return a `reverse-deepagent.workspace-dual-write-pilot-plan.v1` payload.

Default selection is intentionally conservative: it only proposes low-risk `workspace`, `runtime-context`, `source`, `network`, and `evidence` routes, returns their legacy / future write paths through `WorkspacePathResolver(enable_dual_write=True)`, and keeps legacy canonical paths authoritative. Explicit medium-risk audit / triage artifact keys are allowed but flagged for extra review; explicit high-risk delivery / transaction / export / rebuild / hook / trace artifacts block the plan and require a separate manual review.

Boundary: this is not the actual dual-write writer. It does not inspect files, write artifacts, create directories, enable dual-write, migrate workspace paths, change canonical paths, start browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

Tests cover default low-risk candidate selection, unknown and high-risk explicit key blocking, side-effect policy, coordinator tool exposure, and existing workspace / rebuild regressions.


### Step 112 execution record: BrowserProvider production readiness metadata baseline

Status: implemented as metadata-only production seam hardening, not a runtime smoke, browser launch, CDP probe, or third-party vendor integration.

`BrowserProviderCapabilities` now exposes non-secret `production_readiness` metadata. Built-in providers and external template / fixture packages declare health-check mode, profile lifecycle, proxy policy, extension policy, humanize policy, session recovery, intended use, side-effect boundary, and a readiness tier. `reverse_deepagent.browser.smoke.browser_provider_production_readiness(...)` evaluates that serialized metadata into `production-ready`, `review-required`, or `metadata-incomplete` with checks, missing metadata, warnings, score, and an explicit side-effect policy.

`browser_provider_smoke_matrix` and metadata-only registry matrix rows now include `production_readiness`, the matrix top level exposes `production_readiness_version`, and summary output counts production-ready, review-required, and metadata-incomplete providers. Current built-in metadata classifies `cloakbrowser` as production-ready metadata, `playwright-chromium` and `remote-cdp` as review-required, `fixture-browser` as fixture-only / review-required, and `template-browser` as template-only / metadata-incomplete. Doctor inherits the matrix output without starting browsers or touching MCP.

Boundary: this does not call provider factories for external plugins, import optional browser SDKs, check availability, probe CDP endpoints, launch browsers, install hooks, run Web recon, call MCP, or touch Android / iOS / mini-program full runtime chains. Real third-party BrowserProvider implementations, additional provider-specific readiness rules for those providers, controlled proxy / geoip validation, and deeper native-web parity remain follow-up work.

Tests cover the readiness evaluator, metadata matrix output, doctor summary counts, built-in provider metadata, template / fixture plugin classifications, and existing BrowserProvider registry / contract regressions.


### Step 113 execution record: Hosted CDP BrowserProvider template package baseline

Status: implemented as an external BrowserProvider package seam for hosted browser services, vendor anti-detect browsers, enterprise browser pools, and remote CDP brokers; it is not a bundled vendor SDK, account allocator, proxy validator, or production anti-detect integration.

`packages/reverse-deepagent-browser-provider-hosted-cdp-template/` now declares the `reverse_deepagent.browser_providers` entry point `hosted-cdp-template = reverse_deepagent_browser_provider_hosted_cdp_template:browser_provider_registration`. Its registration returns non-secret `BrowserProviderCapabilities`, aliases `hosted-cdp`, `browser-service-template`, and `remote-browser-service`, and a delayed provider factory. Metadata-only registry listing and BrowserProvider matrix construction do not call the factory, allocate remote sessions, open sockets, probe CDP, import vendor SDKs, launch browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

The provider reports `review-required` production readiness metadata for hosted CDP service ownership boundaries. Explicit provider creation accepts `browser_url` / `cdp_browser_url`, redacts configured endpoint metadata, and delegates `connect()` / `start()` to the core `RemoteCDPProvider` adapter so integrators can smoke the BrowserProvider contract against an existing hosted CDP endpoint before replacing allocation / attach logic with a vendor SDK. Missing endpoints raise structured `BrowserProviderUnavailableError` guidance instead of pretending the hosted provider is available.

Tests cover the package entry point, dependency declaration, side-effect-free registration metadata, production readiness classification, delayed factory invocation, unavailable-without-endpoint behavior, URL redaction, and explicit Remote CDP delegation against the fake CDP server.

### Step 114 execution record: Workspace dual-write pilot result artifact baseline

Status: implemented as a read-mostly pilot result verifier and optional audit artifact writer, not scoped dual-write enforcement, foldered-canonical migration, or delivery gate relaxation.

The coordinator now exposes `record_workspace_dual_write_pilot_result`, backed by `record_workspace_dual_write_pilot_result_payload(...)`. The tool compares a reviewed `plan_workspace_dual_write_pilot` payload with an observed `workspace/workspace-dual-write-plan.json` payload, checks each planned candidate's legacy canonical file and future foldered file, records size / sha256 metadata, detects digest mismatches, missing legacy / future files, not-observed candidates, out-of-scope observed writes, and medium / high-risk observed artifacts.

By default the tool is read-only and only inspects files. When explicitly called with `write_result=true`, it writes the audit result to `workspace/workspace-dual-write-pilot-result.json`, which is registered as `workspace_dual_write_pilot_result` under `/workspace/delivery/`. The result keeps legacy paths authoritative and reports `verified`, `partial`, `blocked`, or `not_run` status with blocking reasons and next actions.

Boundary: this does not enable dual-write, does not limit the pipeline writer to a selected scope, does not migrate physical workspace paths, does not change canonical paths, does not execute delivery, does not start browsers, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Broader dual-write rollout and foldered-canonical migration remain follow-ups.

Tests cover missing observed dual-write plans, verified legacy / future digest matches, explicit audit artifact writing, route metadata, coordinator tool exposure, and existing workspace / rebuild regressions.

### Step 115 execution record: Scoped workspace dual-write writer baseline

Status: implemented as an explicit scope gate for opt-in dual-write runs, not foldered-canonical migration, physical artifact relocation, or delivery gate relaxation.

`WorkspacePathResolver` now accepts `dual_write_artifact_keys`. When `enable_dual_write=True` and no scope is provided, the previous behavior is preserved: every registered workspace artifact written by the pipeline gets both the legacy canonical path and the future foldered path. When a scope is provided, only artifact keys in that reviewed set receive the future foldered write path; out-of-scope registered artifacts remain legacy-only and are recorded with `dual_write_enabled=false`, `dual_write_scope_enabled=true`, `dual_write_in_scope=false`, and `migration_status=dual-write-out-of-scope`.

`write_outputs(...)`, `run_reverse_pipeline(...)`, `write_platform_outputs(...)`, and `run_platform_pipeline(...)` now accept `workspace_dual_write_artifact_keys`. The deterministic CLIs expose the same boundary with `--enable-workspace-dual-write` and comma-separated `--workspace-dual-write-artifact-keys`. The emitted `workspace/workspace-dual-write-plan.json` records `mode=scoped-opt-in-dual-write`, `dual_write_scope_enabled`, `dual_write_scope_artifact_keys`, `dual_written_count`, `out_of_scope_record_count`, and per-record scope metadata so `record_workspace_dual_write_pilot_result` can verify only actual dual-written out-of-scope artifacts instead of legacy-only scoped records.

Boundary: this does not make dual-write default, does not migrate canonical paths, does not move or delete legacy artifacts, does not relax delivery / transaction / review gates, does not start browsers, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Broader dual-write rollout and foldered-canonical migration remain follow-ups.

Tests cover scoped resolver planning, Web pipeline scoped dual-write output, scoped audit metadata, legacy-only out-of-scope record handling in pilot result verification, CLI compatibility, and existing workspace regressions.

### Step 116 execution record: Hosted CDP reference BrowserProvider package baseline

Status: implemented as an external BrowserProvider reference package for hosted browser services, not a bundled vendor SDK, production anti-detect integration, account manager, or automatic browser pool allocator.

`packages/reverse-deepagent-browser-provider-hosted-cdp-reference/` now declares the `reverse_deepagent.browser_providers` entry point `hosted-cdp-reference = reverse_deepagent_browser_provider_hosted_cdp_reference:browser_provider_registration`. Its registration returns non-secret `BrowserProviderCapabilities`, aliases `hosted-cdp-ref`, `browser-service-reference`, and `remote-browser-service-reference`, and a delayed provider factory. Metadata-only registry listing and BrowserProvider matrix construction do not call the factory, allocate hosted sessions, open sockets, probe CDP, import vendor SDKs, launch browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

The reference provider models a production-shaped lifecycle: `start()` performs an explicit reference allocation and attaches to the configured CDP endpoint through the core `RemoteCDPProvider`, `connect()` attaches to an existing endpoint or session, and `stop()` closes the delegate provider plus releases only owned allocations idempotently. The module exposes test-only factory invocation and allocation event logs so external provider authors can verify allocation / attach / release boundaries without embedding provider-specific details in the coordinator. URL and session metadata are redacted before they appear in capability summaries or lifecycle event logs.

Boundary: this is a reference implementation, not a real vendor integration. It does not manage accounts, provision proxies, validate geoip, own hosted browser infrastructure, ship anti-detect behavior, make metadata listing allocate sessions, make runtime smoke implicit, call MCP, or touch Android / iOS / mini-program full runtime chains. Real third-party BrowserProvider packages and provider-specific readiness rules remain follow-up work.

Tests cover the package entry point, dependency declaration, side-effect-free registration metadata, production readiness classification, delayed factory invocation, unavailable-without-endpoint guidance, URL / session metadata redaction, explicit endpoint attach without ownership, in-memory reference allocation / idempotent release, and launch smoke through `browser_provider_smoke_row(...)` against the fake CDP server.

### Step 117 execution record: Provider-specific BrowserProvider readiness rule scaffold

Status: implemented as metadata-only provider-specific production readiness rule infrastructure, not a runtime smoke, vendor SDK integration, endpoint probe, or coordinator-level provider special case.

`reverse_deepagent.browser.smoke` now exposes `BrowserProviderProductionReadinessRule` and `list_browser_provider_production_readiness_rules()`. BrowserProvider metadata matrices include `production_readiness_rules` alongside the existing compatibility rule catalog, and `browser_provider_production_readiness(...)` folds matching provider-specific rules into its read-only `checks`, `warnings`, score, and status. The evaluator still consumes only serialized capability metadata: it does not call provider factories, import optional SDKs, allocate hosted sessions, check availability, probe CDP endpoints, launch browsers, call MCP, or touch Android / iOS / mini-program full runtime chains.

The initial provider-specific readiness rule covers `hosted-cdp-reference`: it verifies that the reference provider keeps launch / connect / CDP / managed-browser lifecycle metadata and the reviewed allocation / attach / release readiness fields aligned with the external package contract. Step 119 extends the same metadata-only pattern to built-in Playwright Chromium, Remote CDP, and CloakBrowser provider declarations. Drift is reported as a review-required warning instead of blocking metadata inventory, so real vendor packages can add their own rules later without leaking provider-specific behavior into the coordinator.

Boundary: this remains a metadata-only scaffold. It does not implement real third-party vendor readiness rules, proxy / geoip validation, anti-detect behavior verification, hosted account allocation, runtime smoke automation, or broader BrowserProvider certification. Additional provider-specific compatibility / readiness rules remain follow-up work when real provider packages introduce new capability flags or lifecycle policies beyond the built-in baseline.

Tests cover production readiness rule catalog serialization, metadata matrix rule export, hosted-CDP reference rule pass behavior, provider-specific drift warning behavior, and existing BrowserProvider matrix / plugin regressions. Step 119 adds built-in provider rule pass coverage and doctor matrix version / rule export coverage.

### Step 118 execution record: Workspace dual-write pilot workflow review baseline

Status: implemented as a review-first workspace dual-write pilot workflow helper, not a pipeline runner, default dual-write rollout, foldered-canonical migration, or delivery gate relaxation.

The coordinator now exposes `review_workspace_dual_write_pilot_workflow`, backed by `review_workspace_dual_write_pilot_workflow_payload(...)`. The workflow composes `assess_workspace_migration_readiness`, `plan_workspace_dual_write_pilot`, and optional `record_workspace_dual_write_pilot_result` verification into a `reverse-deepagent.workspace-dual-write-pilot-workflow.v1` payload. It returns the readiness report, reviewed pilot plan, optional pilot result, aggregate blocking reasons / warnings, and a `review_workflow` section with explicit scoped dual-write pipeline and result-recording follow-up steps.

When no observed `workspace/workspace-dual-write-plan.json` is available, the workflow stays `ready_for_review` as long as readiness and plan checks pass, instead of pretending a pilot has already run. When observed scoped dual-write output is supplied or resolvable through `workspace_dual_write_plan_artifact_ref`, the workflow can report `verified`, `partial`, or `blocked` based on legacy / future file existence, sha256 equality, out-of-scope writes, and risk classification. `write_result=true` only delegates the existing audit writer to create `workspace/workspace-dual-write-pilot-result.json` after review.

Boundary: this does not run the pipeline, does not enable dual-write, does not migrate physical workspace paths, does not change canonical paths, does not execute delivery, does not start browsers, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Broader dual-write expansion and foldered-canonical migration remain follow-ups that must be informed by reviewed workflow evidence.

Tests cover review-plan output without file writes, verified observed scoped output, explicit audit-artifact writing, tool factory behavior, coordinator tool exposure, and existing workspace / rebuild regressions.

### Step 119 execution record: Built-in BrowserProvider readiness rules baseline

Status: implemented as metadata-only provider-specific readiness rule expansion for existing built-in BrowserProvider declarations, not runtime smoke, provider factory invocation, endpoint probing, browser launch, vendor SDK integration, or coordinator-level provider branching.

`BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION` is now `2026-06-01.production-readiness-v3`. The provider-specific readiness catalog now includes rules for `playwright-chromium`, `remote-cdp`, `cloakbrowser`, and `hosted-cdp-reference`. The new built-in rules validate only serialized capability flags and declared `production_readiness` fields: Playwright Chromium must keep its launch / connect / persistent-context / CDP / Playwright baseline aligned with explicit availability-or-launch-smoke metadata; Remote CDP must keep its attach-only CDP contract aligned with explicit endpoint-probe and external-browser-owned metadata; CloakBrowser must keep production lifecycle metadata aligned with launch, persistent-context, connect, stealth, humanize, proxy, extension, mobile-emulation, network, debugger, and runtime-eval capability declarations.

Boundary: these checks do not import optional browser SDKs, call provider factories, check availability, probe CDP endpoints, allocate hosted sessions, launch browsers, run Web recon, call MCP, or touch Android / iOS / mini-program full runtime chains. Drift is surfaced as provider-specific readiness warnings so real provider packages can evolve their own rules without leaking provider-specific behavior into the coordinator.

Tests cover catalog serialization for all four provider-specific rules, pass behavior for the three built-in provider metadata declarations, side-effect policy invariants, doctor matrix version / rule export, hosted-CDP reference drift warnings, and existing BrowserProvider matrix / doctor regressions.

### Step 120 execution record: Source Map richer local remap metadata baseline

Status: implemented as a local Source Map payload remap enhancement for source-logpoint routing, not external source-map fetching, section URL fetching, bundler-specific symbol scoping, or webpack module-internal hook discovery.

`SourceMapRemapper` now preserves Source Map `names` metadata for matched segments, matches URL-like source entries through normalized path / query / hash / `webpack://` equivalence, and resolves nested indexed Source Map sections recursively while recording `section_stack` and `indexed_section_depth` metadata. Source logpoint remap payloads inherit the generated location metadata so review / hook artifacts can show the matched symbol name, normalized source match, and nested indexed-section offset chain.

Boundary: this remains pure local remap over caller-supplied Source Map payloads. It does not fetch external `sourceMappingURL` targets, fetch indexed section `url` entries, execute bundler runtimes, infer webpack module-internal hook targets, start browsers, call MCP, or touch Android / iOS / mini-program full runtime chains. External URL fetching and full source-map consumer semantics remain capability-gated follow-ups.

Tests cover source-map `names` metadata, URL-like source equivalence, nested indexed-section stack metadata, source-logpoint metadata propagation, and existing exact / bias / sourceRoot / indexed-section remap regressions.

### Step 121 execution record: Read-only async chunk graph baseline

Status: implemented as a read-only module-discovery enhancement, not arbitrary custom loader execution, async chunk loading, deep webpack runtime traversal, or module federation `get/init` execution.

`ModuleDiscoveryResult` now includes `chunk_graph`. `ModuleDiscoveryManager` derives graph candidates from static script inventory edges such as `import("...")`, `importScripts("...")`, `new URL("...", import.meta.url)`, and webpack-like `require.e(chunkId)` calls. Runtime introspection records loader shape metadata such as `require.e`, `require.u`, `require.f` keys, and public path preview without invoking those functions. External callers may also provide runtime `chunkGraph` metadata, which is normalized into reviewable candidates. Native Web module discovery verification and module-registry artifact metadata now expose chunk graph status, candidate count, static edge count, and runtime loader count.

Boundary: this does not call custom loaders, does not request chunk URLs, does not execute module factories, does not execute module federation `get/init`, does not install hooks automatically, does not start browsers beyond the explicit runtime already in use, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Execution-style loader traversal and actual async chunk loading remain capability-gated follow-ups.

Tests cover script-inventory chunk edges, runtime chunk metadata normalization, side-effect policy invariants, native-web verification strings, module-registry artifact metadata, and existing module discovery / native-web regressions.

### Step 122 execution record: Workspace dual-write pilot smoke follow-through

Status: implemented as a pure-Python reviewed scoped dual-write pilot smoke CLI, not default dual-write rollout, foldered-canonical migration, browser startup, MCP usage, or high-risk delivery / transaction artifact migration.

`reverse-agent-workspace-dual-write-smoke` now runs the mock Web pipeline with explicit `enable_workspace_dual_write=True` and reviewed `--artifact-keys` scope, then feeds the observed `workspace/workspace-dual-write-plan.json` into `review_workspace_dual_write_pilot_workflow`. By default it writes the explicit audit result `workspace/workspace-dual-write-pilot-result.json`; `--no-write-result` keeps workflow verification read-only. The JSON payload reports selected artifact keys, pipeline status, workflow status, result artifact metadata, and a side-effect boundary showing `runtime=mock`, no browser startup, no MCP call, no canonical path change, and no path migration.

Boundary: this is a reproducible smoke / evidence generator for low-risk scoped pilots. It does not make dual-write default, does not expand scope automatically, does not migrate canonical paths, does not move or delete legacy artifacts, does not run delivery, does not start browsers, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Broader dual-write rollout and foldered-canonical migration remain follow-ups that must use reviewed smoke / workflow evidence.

Tests cover the direct Python helper writing a verified pilot result and the `python -m reverse_deepagent.workspace_dual_write_smoke --no-write-result` read-only verification path.

### Step 123 execution record: BrowserProvider smoke evidence CLI

Status: implemented as a workspace evidence capture CLI for BrowserProvider smoke, not an implicit browser launcher, provider certification system, vendor SDK integration, endpoint probe, or MCP path.

`reverse-agent-browser-provider-smoke` now writes `workspace/browser-provider-smoke.json` with schema `reverse-deepagent.browser-provider-smoke.v1`. Default mode resolves BrowserProvider registration metadata through `BrowserProviderRegistry` and `browser_provider_metadata_matrix_payload(...)`, so it does not invoke provider factories, import optional SDKs, check availability, launch browsers, probe CDP endpoints, or call MCP. Explicit `--include-availability` calls `provider.is_available()`, and explicit `--launch-browser-smoke` runs the existing normalized `browser_provider_smoke_row(...)` lifecycle and records the smoke page evidence under the same workspace artifact. The payload records requested / resolved provider id, mode, provider row, next action, artifact key/path, and side-effect policy.

Boundary: metadata-only smoke remains side-effect-free by default. Real launch smoke requires explicit `--launch-browser-smoke`; this still does not make BrowserProvider matrix listing allocate sessions, does not certify a vendor provider, does not manage proxy / geoip accounts, does not start MCP, and does not touch Android / iOS / mini-program full runtime chains. Real third-party provider packages and deeper provider-specific readiness evidence remain follow-ups.

Tests cover metadata-only artifact writing without invoking provider factory, explicit fake launch smoke evidence writing, module CLI JSON output, and existing BrowserProvider / doctor regressions.

### Step 124 execution record: BrowserProvider smoke evidence Web pipeline attachment

Status: implemented as an explicit reviewed-evidence attachment path for the Web pipeline, not an automatic smoke generator, provider certification system, browser launcher, CDP endpoint probe, or MCP bridge.

`reverse-agent-demo` now accepts `--browser-provider-smoke-json <path>`. The CLI reads the supplied UTF-8 JSON object and passes it to `run_reverse_pipeline(...)`; the coordinator writes it as `workspace/browser-provider-smoke.json`, includes `workspace_browser_provider_smoke` in the backend artifact manifest with the existing `/workspace/browser/browser-provider-smoke.json` alias metadata, and mirrors the payload in `exports/artifact-index.json` under `browser_provider_smoke`. The path is Web-pipeline only and does not change `reverse-agent-platform`.

Boundary: this only attaches existing reviewed smoke evidence. It does not call `reverse-agent-browser-provider-smoke`, invoke provider factories, import optional browser SDKs, check availability, launch browsers, probe CDP endpoints, start or call MCP, make BrowserProvider runtime smoke implicit, or touch Android / iOS / mini-program full runtime chains. Real provider smoke evidence is still generated only through explicit smoke commands such as `reverse-agent-browser-provider-smoke --launch-browser-smoke`.

Tests cover coordinator artifact / manifest / artifact-index attachment and console CLI JSON loading / parameter forwarding, alongside existing BrowserProvider smoke CLI and matrix regressions.

### Step 125 execution record: Review-gated webpack async chunk load baseline

Status: implemented as a review-gated async chunk loading baseline for webpack-style `require.e(chunkId)` candidates, not arbitrary custom loader traversal, dynamic `import()` execution, module factory invocation, module federation `get/init`, default recon behavior, browser-provider lifecycle management, or MCP integration.

`AsyncChunkLoadManager` now exposes a two-step workflow. By default an `async-chunk-load` request produces a plan with `review_required=true`, `requires_execute_chunk_load=true`, and `requires_review_approval=true`; it does not execute runtime loaders or request chunks. When both `execute_chunk_load=true` and `review_approved=true` are supplied for a supported webpack runtime candidate, native-web evaluates a controlled `require.e(chunkId)` loader expression, records registry/cache before/after counts and added keys, and reports `workspace/async-chunk-load-plan.json` plus `workspace/async-chunk-load-result.json` artifact refs. Unsupported custom-loader candidates remain blocked even with approval, so arbitrary loader traversal stays a follow-up.

The hook subagent review surface now consumes `async-chunk-load-plan.json` and `async-chunk-load-result.json` as read-only artifacts. It warns when a ready plan still needs review, blocks failed or blocked chunk-load evidence, and keeps the side-effect policy read-only: no JavaScript evaluation, hook installation, chunk loading, file mutation, runtime mutation, MCP call, or delivery.

Boundary: this baseline does not run during default module discovery or Web recon, does not execute dynamic `import()` because that would execute module bodies, does not call custom loader functions, does not invoke module factories, does not execute module federation `get/init`, does not perform deep chunk traversal, does not start browsers beyond the explicit runtime already in use, does not call MCP, and does not touch Android / iOS / mini-program full runtime chains. Broader async traversal, custom-loader execution, and federation execution remain capability-gated follow-ups.

Tests cover plan-only behavior, blocked execution without review approval, approved webpack loader execution with registry diff evidence, blocked custom-loader execution, native-web artifact refs / next actions, workspace artifact routes, coordinator artifact extraction categories, hook-subagent review of pending and executed async chunk evidence, and existing module-discovery / native-web regressions.


### Step 126：Review-gated external Source Map URL fetch baseline

- `SourceMapFetchManager` / `SourceMapFetchSpec`：新增外部 Source Map fetch plan / result baseline，可从显式 `source_map_url` 或脚本里的 `sourceMappingURL` 解析 root Source Map URL，默认只生成 plan，不打开网络。
- Review gate：只有显式 `fetch_source_map=true` 且 `review_approved=true` 时才执行 Python credentialless fetch；默认只允许 same-origin URL，cross-origin 必须显式 `allow_cross_origin_source_map=true` 或 host allowlist；不发送浏览器 cookie、Authorization header，不调用 MCP，不触碰 Android / iOS / 小程序完整链路。
- Indexed sections：显式 `fetch_indexed_section_urls=true` 时，会对 root Source Map 中 indexed section `url` 做同样的 URL policy 与 reviewed credentialless fetch，记录 digest / byte count / sources / names / section 摘要；默认不 fetch section URL，也不导出 raw Source Map payload。
- Native Web：`apply_minimal_protection("source-map-fetch", ...)` 会输出 `virtual://workspace/source-map-fetch-plan.json` 与 `virtual://workspace/source-map-fetch-result.json` artifact refs；workspace contract / coordinator payload extraction / artifact category 已登记。
- Boundary：这是 URL fetch metadata baseline，不是完整 source-map consumer；仍不做 bundler-specific symbol scoping、webpack module-internal hook discovery、凭据化浏览器 fetch 或自动 logpoint remap 重新安装。
- 验证：`tests.test_source_maps`、`tests.test_source_logpoints`、`tests.test_native_web_runtime`、`tests.test_workspace_contract`、`tests.test_coordinator` 定向通过。

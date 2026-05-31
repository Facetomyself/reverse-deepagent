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
| 9. Hook / breakpoint migration | 已完成（paused-session continuation preflight 与 durable paused-session snapshot inspect-only baseline 已补；跨进程 live CDP pause continuation、任意 custom loader / async chunk graph / 深层 module federation 执行式分析、任意闭包内部函数自动 wrapper hook、JS heap 级细粒度 mutation audit / object graph diff、manual stitch candidates 已补、auto-stitch dry-run scoring baseline 已补；自动全链路跨请求 timeline materialization 待后续） | fetch/xhr、cookie、WebSocket、anti-debug hook baseline 已实现；target-function wrapper baseline 已实现，可对 `window.buildSign` 这类全局可达路径安装 wrapper 并输出 `function-hooks.json` / `function-hook-timeline.json`；webpack-like module export hook baseline 已实现，可对显式 `module_id` / `export_name` 通过 `window.__webpack_require__` 解析出的导出函数安装 wrapper 并输出 `module-hooks.json` / `module-hook-timeline.json`；module discovery baseline 已实现，可从 script inventory 提取 webpack-like `module.exports` 导出候选，也可只读 introspect `require.c` / `require.m` runtime cache / registry，并支持显式 `module_runtime_paths` 下的 custom object runtime / module federation exposed-module function-path candidate，输出 `module-registry.json` / `module-candidates.json`；closure-scope function discovery baseline 已实现，可在显式 paused callframe 内用只读 `typeof` 证明候选闭包函数并输出 `closure-functions.json` / `closure-function-candidates.json`；page-level mutation audit baseline 已实现，可围绕显式触发表达式输出 `page-mutation-audit.json` 粗粒度 before/after diff；MutationObserver timeline baseline 已实现，可围绕显式 trigger 输出 `mutation-observer-timeline.json` 有限 DOM mutation records；source-level logpoint baseline 已实现，可对脚本 URL / 行号安装条件断点，支持 generated bundle offset、Source Map exact、GLB bias、sourceRoot 和 indexed sections 到 CDP generated line / column 的最小重映射，并输出 `source-logpoints.json` / `source-logpoint-timeline.json`；retained paused-session registry baseline 已实现，可用 `pause_session_id` 续用同进程内保留的 paused session 并执行 inspect / evaluate / step / resume，且 `continuation_preflight` 会标出 `source=registry`、requested action、pre-action lifecycle 与 live continuation 可用性；durable paused-session snapshot inspect-only baseline 已实现，可通过 `persist_paused_session` / `paused_session_store_dir` 落盘 debugger session、timeline、callframes、breakpoints 和 inspect-only `continuation_preflight` 供后续进程 inspect / audit，并在跨进程 resume / step / evaluate 时返回 `status=action_blocked` / `live_paused_session_required`；BreakpointManager 通过 CDP capability gate 接入 `apply_minimal_protection`，`breakpoints.json` / `debugger-paused.json` / `callframes.json` / 显式 `callframe-evaluations.json` / `mutation-audit.json` / `debugger-actions.json` / `debugger-session.json` / `debugger-timeline.json` artifact ref 与 evidence 映射已补齐；native-web runtime-eval 候选验证已作为迁移中的最小 replay baseline；native-web recon `flow-timeline.json` baseline 已实现，可把 navigation / network / hook / replay 片段落盘，并为 entry 增加 request id、URL path、method、initiator function、hook path、candidate id 等保守 `correlation` hints；同时会派生 request id、URL path + method、function name、candidate id、hook path 维度的 `correlation_groups`，所有 group 都带 `stitching=false` / `scope=correlation-hints-only`，并用 `verification.status=weak|reviewable|ready_for_manual_stitch_review`、evidence booleans 与 `missing_for_ready` 标注人工复核准备度；`reviewable` / `ready_for_manual_stitch_review` group 会进一步生成 `stitch_candidates`，作为 manual-only 候选链并固定 `automatic_stitching=false`；其中 `ready_for_manual_stitch_review` candidate 还会生成 `stitch_proposals`，列出 reviewer approval requirements、blocking conditions 和 pending review decision，作为 review-gated stitching proposal baseline；pending proposal 现在会进入 evidence promotion 的 `review_required_*` 摘要，并由 review gate 以 `review_stitch_proposals_before_delivery` 阻断自动交付；显式 `stitch_review_decisions` 审批通过后可生成 `stitched-flow.json` reviewer-approved baseline，`stitching=true` 但 `automatic_stitching=false`，未审批时仍固定 `approved=false` / `stitching=false`；显式 `flow-timeline` continuation baseline 可继续把上一轮 timeline 与 network / hook / debugger / replay 片段归一化为 `flow-timeline.json`；`stitch_candidates` 现在还会派生 `auto_stitch_dry_runs`，输出 `confidence_score`、`score_reasons`、`conflict_reasons`、`review_required=true`、`would_materialize=false` 和 `automatic_stitching=false`，仅作为 scoring / review aid，不生成 `stitched-flow.json`，也不绕过 review gate；这些 hints、groups、candidates、dry-runs、proposals 和 approved baseline 仍不是自动全链路 materialization |
| 10. MCP legacy downgrade | 已完成 | `legacy-mcp` canonical backend 已实现，`mcp` / `jsreverser-mcp` 保留 deprecated alias 并输出 CLI warning；doctor 支持 `--legacy-mcp`；README / runtime docs 默认推荐 `native-web` |
| 11. DeepAgents workspace contract | 已完成（indexed-only baseline） | `src/reverse_deepagent/workspace_contract.py`、`tests.test_workspace_contract`；Web 与 platform-neutral pipeline 均输出 `workspace/workspace-contract.json`，manifest 包含 `workspace_workspace_contract`；现有扁平 `workspace/*.json` 路径保持 canonical，不做迁移 |
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

## 阶段执行记录与剩余顺序

当前状态：Phase 0-36 已完成，`remote-cdp` smoke 路径已接入，Playwright system Chrome smoke、CloakBrowser fixture smoke、Playwright breakpoint paused/callframe smoke、显式 evaluateOnCallFrame baseline、callframe evaluation policy baseline、mutation audit baseline、page-level mutation audit baseline、MutationObserver timeline baseline、debugger step-control baseline、paused-session continuation preflight、durable paused-session snapshot inspect-only baseline、single-run debugger timeline baseline、target-function wrapper baseline、source-level logpoint baseline、source map / bundle offset remap baseline、source-map bias / sourceRoot / indexed section remap baseline、module export hook baseline、module discovery baseline、runtime module cache / registry introspection baseline、custom runtime / module federation function-path candidate baseline、closure-scope function discovery baseline、native-web recon flow timeline baseline、flow timeline correlation hints、conservative correlation groups、group verification readiness、manual stitch candidates、review-gated stitch proposals、pending stitch proposal evidence promotion / review gate blocking、reviewer-approved stitched-flow materialization baseline、explicit flow timeline continuation baseline、auto-stitch dry-run scoring baseline、auto-stitch policy decision gate baseline、auto-stitch materialization plan baseline、review-approved auto-stitch materializer skeleton、materialization audit / rollback writer baseline、auto-stitch conflict resolver baseline、materialization transaction log baseline、rollback execution dry-run / explicit-review-only baseline、post-rollback review gate recompute baseline、physical rollback dry-run diff baseline、explicit-review-only physical rollback mutation baseline、post-physical-rollback review gate rerun baseline、standard review gate replacement baseline、post-standard-review-gate-replacement delivery guard rerun baseline、final delivery package after delivery guard rerun baseline、final delivery transaction commit record baseline、local delivery executor contract baseline、local delivery manifest revision baseline、backend artifact manifest mutation policy baseline、backend manifest in-place mutation preflight baseline、explicit-review-only backend manifest in-place mutation executor baseline、backend manifest cross-run recovery preflight baseline、backend manifest cross-run transaction commit baseline、backend manifest recovery apply baseline，以及 retained paused-session registry baseline 均已验证，MCP alias deprecation warning 已接入，最终 code review 已完成并修复 module-hook 路由、module hook path quoting 和 page-mutation global snapshot 副作用风险；MCP 物理拆包前置步骤已完成：RuntimeBackendRegistry 支持 `reverse_deepagent.runtime_backends` entry-point discovery，加载外部 backend registration 时不调用 backend factory；`legacy-mcp` registration / factory / alias warning 已从 coordinator 内联逻辑挪到 `reverse_deepagent.runtime.legacy_mcp`，并支持 `build_default_runtime_registry(include_legacy_mcp=False)` 构建不带 MCP backend 的 clean registry；`packages/reverse-deepagent-legacy-mcp/` optional plugin package 已拥有 legacy MCP registration / factory、config 和 stdio bridge 实现，core 侧 `reverse_deepagent.runtime.legacy_mcp` 只保留兼容 shim、默认命令常量、alias warning、doctor 代理和 install guidance，不再内置 legacy MCP factory fallback 或 stdio MCP transport；默认 registry 会先加载外部 entry points，若未安装 optional package，`legacy-mcp` / `mcp` 会返回结构化安装建议且不会先启动受管 Chrome。DeepAgents workspace contract indexed-only baseline 已落地，当前输出 `workspace/workspace-contract.json`，覆盖虚拟文件夹、子智能体角色、middleware chain 和现有扁平 artifact route。BrowserProvider smoke matrix / lifecycle baseline 已落地，doctor 可输出 metadata-only provider matrix，真实启动仍需显式 `--launch-browser-smoke`。后续仍需跨进程 live CDP paused execution continuation、任意 custom loader / async chunk graph / 深层 module federation 执行式分析、任意闭包内部函数 automatic wrapper hook、JS heap 级细粒度 mutation audit / object graph diff、richer Source Map name / URL / complex indexed section semantics、DeepAgents 虚拟文件夹真实迁移，以及更完整的自动全链路跨请求 timeline conflict resolver / external delivery executor / 完整跨运行 manifest recovery state machine / cross-run rollback state machine / 更完整 transaction state machine / 无需审批 automatic materializer。Android / iOS / 小程序完整运行链路继续搁置，只保留 minimal probe / artifact export baseline。Step 5.1 到 Step 36 保留为已执行阶段记录，便于 review 和回溯。



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
- 后续仍需 manifest recovery state machine、transaction idempotency / duplicate-commit hardening 和外部交付执行器。

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
- 后续仍需 cross-run recovery state machine、transaction idempotency / duplicate-commit hardening 和外部交付执行器。

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
- 后续仍需 backend manifest in-place mutation policy、cross-run recovery state machine、transaction idempotency 和外部交付执行器。

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
- 后续仍需 backend manifest mutation policy、cross-run recovery state machine、transaction idempotency 和外部交付执行器。

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
- Step 22 已补出 physical rollback dry-run diff，Step 23 已补出 explicit-review-only artifact model mutation，Step 25 已补出标准 review gate replacement baseline；cross-run transaction commit / external delivery executor、跨运行 physical rollback transaction state machine，以及更完整 transaction state machine 仍未实现。

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
- `future_path` 只表示后续虚拟文件夹目标。
- 后续移动 / 重命名 artifact 必须先提供 compatibility alias、manifest 覆盖和回归测试。

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

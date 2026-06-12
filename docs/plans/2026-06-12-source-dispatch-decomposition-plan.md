# Rollout 8 `_dispatch_source(...)` staged decomposition plan

## 1. 任务卡与边界

task_card:

- task_description: 为 `src/reverse_deepagent/adapters/native_web.py` 中 `_dispatch_source(...)` 制定 staged decomposition plan。
- mode: planning。
- plan_target: `docs/plans/2026-06-12-source-dispatch-decomposition-plan.md`。
- constraints: 本轮只写计划文档；不改代码、不改 artifact schema、不改 workspace path、不碰 Rollout 8 其他 worker 文档。
- execution_flags: docs-only，后续代码迁移必须另起 PR。

本计划面向 Rollout 8 的 Worker S。当前输出是拆分方案，不是实现补丁。任何后续执行都必须继续遵守 `native-web + BrowserProvider + native collectors / hooks` 主线，并保持 Source Map follow-through 的 explicit-review-only / review-only / read-only 边界。

## 2. 当前 helper 尺寸和风险

当前 baseline：

- 文件：`src/reverse_deepagent/adapters/native_web.py`。
- helper：`_dispatch_source(self, protection_name: str, context: dict)`。
- 行号：2740-6591。
- 尺寸：3852 行。
- 分支形态：37 个顺序 `if self._is_*_request(protection_name, context)` 分支，最后 `return None`。
- 主要职责：Source Map lookup / source content / readiness / consumer action plan / materialization / typed payload preflight / follow-through review / selected executor review / approval / preflight / selected application / dispatcher review chain / debugger candidate / hook candidate / rebuild metadata / rebuild bundle / terminal review / Source Map fetch 等全部压在同一个 adapter helper 里。

`★ Insight ─────────────────────────────────────`
- 这个 helper 最大的问题不是“行数难看”，而是三类职责缠一起：route 匹配顺序、review descriptor 包装、少量 explicit apply 执行。拆错了就容易把 review-only gate 变成 executor。
- Source Map 链路里很多名字带 `dispatch` / `apply` / `executor`，但它们多数只是 descriptor / preflight / handoff / audit；不能按名字想当然迁移到会执行浏览器或 CDP 的模块里。
- 后续拆分应优先保持分支顺序和 `ProtectionResult` payload 等价，再考虑抽象复用；一上来搞“通用框架化”，十有八九把显式审批边界搅糊，嘎嘎危险。
`─────────────────────────────────────────────────`

### 2.1 37 个当前分支

| 顺序 | 行号 | 分支 predicate | 当前 manager / executor | 当前 artifact |
|---:|---:|---|---|---|
| 1 | 2741-2810 | `_is_source_map_hook_candidate_selection_request` | `SourceMapHookCandidateSelectionManager.review` | `virtual://workspace/source-map-hook-candidate-selection.json` |
| 2 | 2811-2882 | `_is_source_map_hook_candidate_refinement_request` | `SourceMapHookCandidateRefinementManager.review` | `virtual://workspace/source-map-hook-candidates.json` |
| 3 | 2883-2954 | `_is_source_map_debugger_candidate_selection_request` | `SourceMapDebuggerCandidateSelectionManager.review` | `virtual://workspace/source-map-debugger-candidate-selection.json` |
| 4 | 2955-3029 | `_is_source_map_debugger_candidate_review_request` | `SourceMapDebuggerCandidateReviewManager.review` | `virtual://workspace/source-map-debugger-candidates.json` |
| 5 | 3030-3295 | `_is_source_map_debugger_application_request` | `BreakpointManager.set_breakpoint` after explicit gates | `source-map-debugger-execution-result.json` plus debugger / breakpoint artifacts |
| 6 | 3296-3488 | `_is_source_map_hook_application_request` | `FunctionHookManager.install` / `ModuleHookManager.install` after explicit gates | `source-map-hook-install-result.json` plus hook inventory / timeline |
| 7 | 3489-3609 | `_is_source_map_rebuild_metadata_application_request` | digest-only metadata application | `source-map-rebuild-result.json` |
| 8 | 3610-3841 | `_is_source_map_rebuild_generation_request` | `write_rebuild_bundle(...)` after explicit gates | `source-map-rebuild-generation-result.json` |
| 9 | 3842-4000 | `_is_source_map_source_logpoint_application_request` | `SourceLogpointManager.install` after explicit gates | `source-map-source-logpoint-install-result.json`, `source-logpoints.json`, `source-logpoint-timeline.json` |
| 10 | 4001-4116 | `_is_source_map_followthrough_dispatcher_result_request` | `SourceMapFollowthroughDispatcherManager.dispatch` as explicit decision record | `source-map-followthrough-dispatcher-result.json` |
| 11 | 4117-4232 | `_is_source_map_followthrough_dispatcher_apply_preflight_request` | `SourceMapFollowthroughDispatcherApplyPreflightManager.review` | `source-map-followthrough-dispatcher-apply-preflight.json` |
| 12 | 4233-4345 | `_is_source_map_followthrough_dispatcher_handoff_request` | `SourceMapFollowthroughDispatcherHandoffManager.review` | `source-map-followthrough-dispatcher-handoff.json` |
| 13 | 4346-4453 | `_is_source_map_followthrough_dispatch_bounded_executor_gate_request` | `SourceMapFollowthroughDispatchBoundedExecutorGateManager.review` | `source-map-followthrough-dispatch-bounded-executor-gate.json` |
| 14 | 4454-4566 | `_is_source_map_followthrough_dispatch_transaction_preflight_request` | `SourceMapFollowthroughDispatchTransactionPreflightManager.review` | `source-map-followthrough-dispatch-transaction-preflight.json` |
| 15 | 4567-4672 | `_is_source_map_followthrough_dispatch_approval_plan_request` | `SourceMapFollowthroughDispatchApprovalPlanManager.review` | `source-map-followthrough-dispatch-approval-plan.json` |
| 16 | 4673-4779 | `_is_source_map_followthrough_dispatch_preflight_request` | `SourceMapFollowthroughDispatchPreflightManager.review` | `source-map-followthrough-dispatch-preflight.json` |
| 17 | 4780-4883 | `_is_source_map_followthrough_one_step_plan_request` | `SourceMapFollowthroughOneStepPlanManager.review` | `source-map-followthrough-one-step-plan.json` |
| 18 | 4884-4970 | `_is_source_map_followthrough_chain_readiness_request` | `SourceMapFollowthroughChainReadinessManager.review` | `source-map-followthrough-chain-readiness.json` |
| 19 | 4971-5066 | `_is_source_map_selected_executor_application_handoff_request` | `SourceMapSelectedExecutorApplicationHandoffManager.review` | `source-map-selected-executor-application-handoff.json` |
| 20 | 5067-5159 | `_is_source_map_selected_executor_result_checkpoint_request` | `SourceMapSelectedExecutorResultCheckpointManager.review` | `source-map-selected-executor-result-checkpoint.json` |
| 21 | 5160-5248 | `_is_source_map_followthrough_completion_checkpoint_request` | `SourceMapFollowthroughCompletionCheckpointManager.review` | `source-map-followthrough-completion-checkpoint.json` |
| 22 | 5249-5338 | `_is_source_map_terminal_review_final_audit_request` | `SourceMapTerminalReviewFinalAuditManager.review` | `source-map-terminal-review-final-audit.json` |
| 23 | 5339-5428 | `_is_source_map_terminal_review_closure_checkpoint_request` | `SourceMapTerminalReviewClosureCheckpointManager.review` | `source-map-terminal-review-closure-checkpoint.json` |
| 24 | 5429-5514 | `_is_source_map_terminal_review_package_request` | `SourceMapTerminalReviewPackageManager.review` | `source-map-terminal-review-package.json` |
| 25 | 5515-5625 | `_is_source_map_selected_executor_apply_preflight_request` | `SourceMapSelectedExecutorApplyPreflightManager.review` | `source-map-selected-executor-apply-preflight.json` |
| 26 | 5626-5723 | `_is_source_map_selected_executor_approval_plan_request` | `SourceMapSelectedExecutorApprovalPlanManager.review` | `source-map-selected-executor-approval-plan.json` |
| 27 | 5724-5818 | `_is_source_map_selected_executor_input_review_request` | `SourceMapSelectedExecutorInputReviewManager.review` | `source-map-selected-executor-input-review.json` |
| 28 | 5819-5903 | `_is_source_map_followthrough_surface_selection_request` | `SourceMapFollowthroughSurfaceSelectionManager.review` | `source-map-followthrough-surface-selection.json` |
| 29 | 5904-5989 | `_is_source_map_followthrough_review_request` | `SourceMapFollowthroughReviewManager.review` | `source-map-followthrough-review.json` |
| 30 | 5990-6073 | `_is_source_map_typed_payload_preflight_request` | `SourceMapTypedPayloadPreflightManager.review` | `source-map-typed-payload-preflight.json` |
| 31 | 6074-6169 | `_is_source_map_consumer_materialization_request` | `SourceMapConsumerMaterializationManager.review` | `source-map-consumer-materialization.json` |
| 32 | 6170-6248 | `_is_source_map_consumer_action_plan_request` | `SourceMapConsumerActionPlanManager.review` | `source-map-consumer-action-plan.json` |
| 33 | 6249-6325 | `_is_source_map_readiness_request` | `SourceMapReadinessManager.review` | `source-map-readiness.json` |
| 34 | 6326-6389 | `_is_source_map_lookup_request` | `SourceMapLookupManager.lookup` | `source-map-lookup.json` |
| 35 | 6390-6459 | `_is_source_map_source_content_request` | `SourceMapSourceContentManager.review` | `source-map-source-content.json` |
| 36 | 6460-6515 | `_is_bundler_symbol_scope_request` | `BundlerSymbolScopeManager.review` | `bundler-symbol-scope.json` |
| 37 | 6516-6590 | `_is_source_map_fetch_request` | `SourceMapFetchManager.plan_or_fetch` | `source-map-fetch-plan.json`, `source-map-fetch-result.json` |

### 2.2 风险清单

- **route 顺序风险**：candidate selection 必须在 candidate review / refinement 之前；follow-through dispatcher / selected-executor / terminal review 的顺序也带有兼容语义。拆分时如果改成 unordered registry，可能让宽松 predicate 抢走更具体的 request。
- **side-effect 语义风险**：`review`、`preflight`、`handoff`、`checkpoint`、`audit` 分支大多要求 `browser_started=false`、`cdp_command_sent=false`、`runtime_evaluated=false`、`hook_installed=false`、`calls_mcp=false`、`mobile_runtime_used=false`。迁移时不能因为“dispatch”二字就调用 executor。
- **artifact metadata 等价风险**：当前 `ArtifactRef` 的 `path`、`kind`、`description`、`metadata` 是外部 review / hook / debugger / workspace contract 的消费面。哪怕 JSON schema 不变，少一个 metadata key 都可能让 review subagent 的 blocker / warning 变味。
- **状态映射风险**：每个分支都有自己的 `result.status -> ExecutionStatus / applied_actions / next_action / confidence` 映射。抽公共函数时不能把 `blocked`、`ready_for_review`、`success`、`planned`、`failed` 的语义统一错。
- **session acquisition 风险**：只有少数 explicit application 分支会在 gates 通过后 `self._ensure_session()`；所有 review-only / preflight-only 路径必须继续在浏览器启动前返回。
- **rebuild 写盘风险**：rebuild generation 是 explicit-review-only 写入现有 rebuild bundle 的桥，不是 Source Map raw-source-aware 自动编译器，也不是 delivery executor。
- **fetch 风险**：`source-map-fetch` 是 review-gated credentialless metadata baseline，不能在 lookup / readiness / materialization 拆分时顺手自动 fetch。

## 3. 拆分原则：以 Source Map explicit-review-only 边界为核心

后续拆分不是把 `_dispatch_source(...)` 按行数随便剁开。主原则如下：

1. **predicate 顺序保持字节级可审计**：第一阶段可以保留一个 route list，但 list 顺序必须与当前 37 个分支一致。任何重排都必须单独 PR、单独说明兼容影响。
2. **review descriptor 仍是 descriptor**：`lookup`、`source-content`、`readiness`、`consumer-action-plan`、`materialization`、`typed-payload-preflight`、`followthrough-review`、`surface-selection`、`selected-executor-input-review`、`approval-plan`、`apply-preflight`、`checkpoint`、`terminal-review` 等不能被描述或实现成自动 executor。
3. **explicit-review-only application 单独隔离**：debugger application、hook application、source-logpoint application、rebuild metadata application、rebuild generation、dispatcher result 这类有写入或 runtime potential 的 surface 必须有独立 gate helper，保留 `mode=apply`、`review_approved=true`、对应 `approve_*`、reviewer、digest / preflight input 等检查。
4. **adapter 只做 runtime adapter 包装**：Source Map manager 的业务判断继续留在 `reverse_deepagent.browser.source_maps` / hook / debugger / rebuild 现有模块；`native-web` 的拆分模块只负责 request routing、side-effect gate、`ProtectionResult` 包装和 artifact metadata 桥接。
5. **不新增行为**：拆分 PR 不新增 browser / CDP / MCP / mobile 行为，不引入新 artifact schema，不改 workspace canonical / virtual path，不扩大 `source-map-fetch` 自动化。
6. **先机械迁移，再复用抽象**：第一批代码 PR 应优先把完整分支搬到新 helper，保持重复代码；等等价测试稳定后，再抽 `descriptor_policy(...)`、`artifact(...)`、`status mapping` 等通用 builder。

## 4. 候选 helper / module 边界

建议后续从一个轻量模块开始，别一口气搞成多层框架：

```text
src/reverse_deepagent/adapters/native_web_source_dispatch.py
```

或包化版本：

```text
src/reverse_deepagent/adapters/source_dispatch/
  __init__.py
  routing.py
  review_descriptors.py
  selected_executor.py
  applications.py
  terminal.py
```

若团队要降低冲突，优先单文件 `native_web_source_dispatch.py`，等行为稳定后再包化。

### 4.1 `SourceDispatchAdapter` / route shell

职责：

- 接收 `owner` / `runtime adapter`、`protection_name`、`context`。
- 以当前 37 个 predicate 的顺序分发。
- 返回 `ProtectionResult | None`。
- 只调用已经存在的 `_is_*_request(...)` predicate，第一阶段不搬 predicate，避免同时改 matcher 和 branch body。

禁区：

- 不自己启动浏览器。
- 不调用 MCP。
- 不修改 workspace path / schema。
- 不合并 review-only 和 apply executor 的 route。

### 4.2 lookup / source-content / readiness / action-plan / materialization

建议 helper：

- `dispatch_source_map_lookup(...)`。
- `dispatch_source_map_source_content(...)`。
- `dispatch_source_map_readiness(...)`。
- `dispatch_source_map_consumer_action_plan(...)`。
- `dispatch_source_map_consumer_materialization(...)`。
- `dispatch_source_map_typed_payload_preflight(...)`。

覆盖当前分支：30-35，以及 36 的 `bundler-symbol-scope` 可一起作为 source evidence review 层。

边界：

- 这些都是 evidence / review payload preparation，不执行 debugger / hook / rebuild。
- `source-content` 只输出 availability / digest / size / line-count metadata，不导出 raw source / preview。
- `readiness` 只 join 已有 descriptor，不 fetch Source Map、不 start browser。
- `materialization` 只把 reviewed action ids / consumers materialize 成 typed review payload，不执行 typed payload。

冲突点：

- 这批最靠近函数尾部，和其他 worker 改动冲突概率低。
- 但是它们是上游 evidence，任何 artifact metadata 变化都会影响 selected executor review 测试。

### 4.3 selected executor review / approval / preflight

建议 helper：

- `dispatch_source_map_selected_executor_input_review(...)`。
- `dispatch_source_map_selected_executor_approval_plan(...)`。
- `dispatch_source_map_selected_executor_apply_preflight(...)`。
- `dispatch_source_map_selected_executor_application_handoff(...)`。
- `dispatch_source_map_selected_executor_result_checkpoint(...)`。

覆盖当前分支：19、20、25、26、27。

边界：

- input review / approval plan / apply preflight 都是 review-only 或 read-only descriptor。
- approval plan 不写 approval record。
- apply preflight 固定 `ready_to_apply_now=false`、`future_executor_contract.implemented=false` 之类语义，不调用 selected executor。
- application handoff / result checkpoint 是对显式 application result 的审计 / 对账，不自己执行 application。

冲突点：

- 与 debugger / hook / rebuild application 分支强相关，建议在 evidence review 层迁移后、application 层迁移前落地。
- 容易和后续“自动 follow-through”想法冲突，PR 描述必须反复强调不是 automatic executor。

### 4.4 debugger candidate 与 debugger application

建议 helper：

- `dispatch_source_map_debugger_candidate_review(...)`。
- `dispatch_source_map_debugger_candidate_selection(...)`。
- `dispatch_source_map_debugger_application(...)`。

覆盖当前分支：3、4、5。

边界：

- candidate review / selection 是 read-only / review-only / plan-only / handoff-only descriptor。
- application 是 explicit-review-only MVP：只有 gates 通过才允许启动 BrowserProvider session、复用 native breakpoint manager，并输出 debugger artifacts。
- blocked application path 不启动浏览器。
- successful path 不自动 continue、不 live callFrame recovery、不 loop。

冲突点：

- debugger application 分支 266 行，是当前 `_dispatch_source` 中最长且 runtime side-effect 风险最高的片段。
- 建议先迁移 candidate review / selection，再迁移 application；如果同 PR 做，review 难度会明显上去。

### 4.5 hook candidate 与 hook application

建议 helper：

- `dispatch_source_map_hook_candidate_refinement(...)`。
- `dispatch_source_map_hook_candidate_selection(...)`。
- `dispatch_source_map_hook_application(...)`。

覆盖当前分支：1、2、6。

边界：

- candidate refinement / selection 只生成 reviewed hook candidate / handoff，不安装 hook。
- application 是 explicit-review-only：必须有 reviewed concrete `source_map_hook_install_input`，解析为 `FunctionHookSpec` 或 `ModuleHookSpec` 后复用现有 hook manager。
- 不从 Source Map symbol scope 自动推断并安装 hook。
- 不发送 CDP debugger command。

冲突点：

- 与 Worker R 的 fallback hook contract 同属 hook 语义，但写入文件不同。后续代码 PR 要避免同时改 final fallback hook 与 Source Map hook application。
- hook application artifact 连接 `function-hooks.json` / `module-hooks.json` timeline，等价测试要盯住 metadata。

### 4.6 rebuild metadata / bundle generation

建议 helper：

- `dispatch_source_map_rebuild_metadata_application(...)`。
- `dispatch_source_map_rebuild_generation(...)`。

覆盖当前分支：7、8。

边界：

- metadata application 是 digest-only / metadata-only application，固定 `rebuild_bundle_generated=false`、`rebuild_executed=false`。
- rebuild generation 是 explicit-review-only bridge 到已有 `write_rebuild_bundle(...)`，不是 Source Map raw-source-aware compiler。
- blocked generation 不创建目录、不写 bundle、不启动浏览器、不 evaluate JS、不 fetch Source Map。
- successful generation 只写现有 rebuild artifacts 与 audit result，不 delivery、不执行 replay。

冲突点：

- 分支 8 有 232 行，含 `artifact_root`、`task_card`、`final_result`、generated file metadata 等输入检查，容易被“抽通用 apply gate”误伤。
- 与 rebuild 模块后续增强可能冲突，建议单 PR 迁移并带 focused tests。

### 4.7 source-logpoint application

建议 helper：

- `dispatch_source_map_source_logpoint_application(...)`。

覆盖当前分支：9。

边界：

- explicit-review-only selected executor application。
- 只在 gates 通过后安装 reviewed source-level logpoint。
- 不做 automatic source-logpoint install。

冲突点：

- 与 debugger / hook application 同属 runtime side-effect class，但 artifact 不同。可作为 application batch 的小先导 PR。

### 4.8 follow-through dispatch chain

建议 helper：

- `dispatch_source_map_followthrough_chain_readiness(...)`。
- `dispatch_source_map_followthrough_one_step_plan(...)`。
- `dispatch_source_map_followthrough_dispatch_preflight(...)`。
- `dispatch_source_map_followthrough_dispatch_approval_plan(...)`。
- `dispatch_source_map_followthrough_dispatch_transaction_preflight(...)`。
- `dispatch_source_map_followthrough_dispatch_bounded_executor_gate(...)`。
- `dispatch_source_map_followthrough_dispatcher_handoff(...)`。
- `dispatch_source_map_followthrough_dispatcher_apply_preflight(...)`。
- `dispatch_source_map_followthrough_dispatcher_result(...)`。
- `dispatch_source_map_followthrough_review(...)`。
- `dispatch_source_map_followthrough_surface_selection(...)`。
- `dispatch_source_map_followthrough_completion_checkpoint(...)`。

覆盖当前分支：10-18、21、28、29。

边界：

- 大部分是 read-only / review-only / plan-only / handoff-only / transaction-preflight-only / bounded-gate-only。
- `dispatcher result` 是 explicit-review-only decision record，不调用 dispatch target，不执行 selected executor，不运行 selected-executor apply preflight。
- transaction preflight 不写 journal；journal writer 不在 `_dispatch_source(...)` 当前 37 分支里，不要顺手引入。
- bounded executor gate 固定 future dispatcher contract `implemented=false`，不能变成真实 dispatcher。

冲突点：

- 命名最容易误导 reviewers，以为 `dispatch` 就是执行。迁移 PR 应把 side-effect flags 放在测试里做等价断言。
- 与 docs/runtime 中 Step 294-299/302 等口径绑定紧，任何 wording / metadata 变化都要同步 docs，但本 decomposition PR 不改这些长期说明。

### 4.9 terminal review / audit

建议 helper：

- `dispatch_source_map_terminal_review_package(...)`。
- `dispatch_source_map_terminal_review_closure_checkpoint(...)`。
- `dispatch_source_map_terminal_review_final_audit(...)`。

覆盖当前分支：22、23、24。

边界：

- 只做 terminal review package / closure checkpoint / final audit descriptor。
- 不 commit、rollback、delivery、不执行 follow-through。
- 不改变 `workspace` canonical path 或 manifest metadata。

冲突点：

- 逻辑相对独立，适合作为后半程低风险 PR。
- 但 terminal 文档常被 ROADMAP/status 引用，后续如需改文档要避开 Worker T 的 audit triage 文档。

### 4.10 Source Map fetch

建议 helper：

- `dispatch_source_map_fetch(...)`。

覆盖当前分支：37。

边界：

- 保持 review-gated credentialless Source Map fetch metadata baseline。
- 不把 lookup / readiness 自动升级成 fetch。
- 不使用 browser credential，不调用 MCP。

冲突点：

- `SourceMapFetchManager.plan_or_fetch` 当前同时支持 planned / blocked / success。拆分时要保留 `source-map-fetch-plan.json` 与 `source-map-fetch-result.json` 双 artifact 行为。

## 5. 分批 PR / merge order

建议按“低副作用、低冲突、先 route shell 后 application”推进：

### PR S1：route shell 与纯 review evidence 尾部迁移

范围：

- 新增 `native_web_source_dispatch.py` 或同等 helper module。
- `_dispatch_source(...)` 改为委派 source dispatch adapter。
- 先迁移分支 30-37：typed payload preflight、consumer materialization、consumer action plan、readiness、lookup、source-content、bundler-symbol-scope、fetch。
- 保持原 predicate 留在 `NativeWebRuntime`，避免一次性搬 matcher。

容易冲突：

- 与任何改 `native_web.py` 尾部 Source Map 分支的 worker 冲突。
- 与 workspace artifact schema 变更冲突，但 Rollout 8 明确不应发生。

推荐 merge：第一批代码 PR，最好在 Worker R / S / T 文档 PR 全部合并后再开始。

### PR S2：selected executor review / approval / preflight 迁移

范围：

- 迁移分支 19、20、25、26、27。
- 可同时迁移通用 descriptor policy extraction，但不要改变 payload key。

容易冲突：

- 与 debugger / hook / rebuild application PR 冲突，因为这些 application 会消费 selected-executor preflight / handoff result。

推荐 merge：S1 后。

### PR S3：debugger / hook candidate review 与 selection 迁移

范围：

- 迁移分支 1、2、3、4。
- 不迁移 application。

容易冲突：

- 与 Worker R 的 fallback hook contract 后续实现冲突概率中等；避免同 PR 改 final fallback hook。
- 与 source-map ranking / candidate selection worker 的老分支可能冲突，合并前先 `git fetch origin` 并 rebase。

推荐 merge：S2 后。

### PR S4：explicit application split，小步迁移

范围建议拆成三个更小 PR：

- S4a：source-logpoint application，分支 9。
- S4b：debugger application，分支 5。
- S4c：hook application，分支 6。

容易冲突：

- 这些分支会碰 `self._ensure_session()`、Breakpoint / Hook manager imports、artifact metadata。它们最容易引入真实行为变化，必须小 PR。

推荐 merge：S3 后，且每个 PR 独立 validation。

### PR S5：rebuild metadata / generation 迁移

范围：

- 迁移分支 7、8。
- 保留 `write_rebuild_bundle(...)` 调用语义。

容易冲突：

- 与 rebuild artifact / delivery 相关 PR 冲突。
- `artifact_root` 与 generated file metadata 容易受路径策略 PR 影响。

推荐 merge：S4 后或与 S4 平行但不要同一 reviewer batch。

### PR S6：follow-through dispatch chain 迁移

范围：

- 迁移分支 10-18、28、29。
- 明确保留 review-only / preflight-only / gate-only / handoff-only / explicit decision record 边界。

容易冲突：

- 这批名称最像 executor，review 成本最高。
- 与任何 future automatic follow-through 实验冲突，必须等 S1-S5 稳定。

推荐 merge：S5 后。

### PR S7：terminal review / audit 迁移与清理

范围：

- 迁移分支 21-24。
- 删除 `_dispatch_source(...)` 里残留重复 body，仅保留 route adapter call。
- 如果前面还没做，再抽通用 `ProtectionResult` builder。

容易冲突：

- 与 docs/status / ROADMAP 收口 PR 冲突。代码 PR 自己不要更新 rollout status，交给 main agent 收口。

推荐 merge：最后。

## 6. 每批 validation 命令和等价性检查

### 6.1 文档-only PR validation

本 Worker S 当前文档 PR：

```bash
git diff --check
```

人工检查：

- 文档路径仅包含 `docs/plans/2026-06-12-source-dispatch-decomposition-plan.md`。
- 中文无乱码。
- 未把 review-only descriptor 写成 automatic executor。
- 未承诺本轮代码迁移。

### 6.2 所有后续代码 PR 的基础 validation

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
```

### 6.3 推荐 focused tests

后续代码迁移 PR 应优先跑与 Source Map / native-web / workspace / coordinator / hook / debugger 相关测试。测试文件名可能随分支演进变化，执行前先用 `ls tests | rg 'source|native_web|workspace|coordinator|hook|debugger|rebuild'` 确认。推荐命令形态：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest \
  tests.test_workspace_contract \
  tests.test_coordinator \
  tests.test_rebuild_artifacts \
  -v
```

如果存在专项 Source Map / native web 测试，追加：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -p '*source*map*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -p '*native*web*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -p '*hook*.py' -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -p '*debugger*.py' -v
```

S4 / S5 / S6 这类高风险 PR 合并前，建议跑全量：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
```

### 6.4 等价性检查清单

每个代码 PR 都要检查：

- `_dispatch_source(...)` 对不匹配 request 仍返回 `None`。
- 每个迁移分支的 `ArtifactRef.path`、`kind`、`description`、关键 `metadata` 与迁移前一致。
- `verification` 里的 side-effect flags 与迁移前一致，尤其是：
  - `browser_started=false`。
  - `cdp_command_sent=false`。
  - `runtime_evaluated=false`。
  - `hook_installed=false` 或仅在 explicit hook application success 后按现有语义记录。
  - `rebuild_executed=false`。
  - `calls_mcp=false`。
  - `mobile_runtime_used=false`。
- `result.status` 到 `ExecutionStatus`、`applied_actions`、`next_action`、`confidence` 的映射不变。
- blocked paths 不调用 `self._ensure_session()`。
- review-only / preflight-only / handoff-only routes 不写文件、不创建目录、不启动 browser。
- rebuild generation blocked paths 不创建 `artifact_root`；success paths 只走现有 `write_rebuild_bundle(...)`。
- source-map fetch 仍只输出 plan / result metadata，不被 lookup / readiness 自动触发。

可以为每个迁移分支补一个 “pre/post result snapshot” 单元测试：用固定 context 调旧 branch baseline 和新 helper，比较 `ProtectionResult` 的可序列化形状。若测试环境不方便同时保留旧实现，至少用 fixture expected dict 锁住 artifact path / metadata / status / next_action。

## 7. side-effect guards

后续 decomposition 过程中必须固定以下 guards：

- 不新增 browser 行为：review descriptor、candidate、preflight、handoff、checkpoint、terminal audit 不得启动 BrowserProvider session。
- 不新增 CDP 行为：除现有 explicit debugger / source-logpoint / hook application 已有语义外，不发送 CDP command。
- 不新增 MCP 行为：Source Map dispatch 拆分不得重新把 MCP 当抽象边界，也不得调用 legacy MCP。
- 不新增 mobile 行为：不触碰 Android / iOS / mini-program full runtime chains。
- 不改 artifact schema：不新增 / 重命名 `reverse-deepagent.*.v1` schema，不改现有 artifact key 的语义。
- 不改 workspace path：不移动 `workspace/*.json` canonical path，不改变 future alias / virtual URI 约定。
- 不扩大 fetch：不从 lookup / readiness / materialization 自动 fetch Source Map。
- 不自动审批：approval-plan 不是 approval-record；preflight 不是 executor；dispatcher result 不是 selected executor execution。
- 不自动 delivery：rebuild generation 不发布、不执行 replay、不触发 external delivery。

## 8. 后续 rollout 建议

1. **Rollout 9：Source dispatch shell extraction**
   只落 S1，迁移尾部 pure review / evidence 分支，建立 route adapter 和等价测试骨架。

2. **Rollout 10：Selected executor review chain extraction**
   落 S2 + S3，保持所有 candidate / selected-input / approval / preflight 为 review-only，不碰 runtime application。

3. **Rollout 11：Explicit application extraction**
   按 S4a / S4b / S4c 拆小 PR，重点验证 blocked paths 不启动 browser、success paths 等价。

4. **Rollout 12：Rebuild and follow-through extraction**
   分 S5 / S6 迁移 rebuild 与 follow-through dispatch chain；这批要严控“dispatch 名称误导 executor”的风险。

5. **Rollout 13：Terminal cleanup and native_web shrink audit**
   落 S7，清理 `_dispatch_source(...)` 残留，并重新统计 `native_web.py` 最大 helper，决定下一轮是否拆 `_dispatch_paused` / delivery / workspace review helper。

6. **长期收敛**
   等所有分支迁出后，再考虑包化 `source_dispatch/`，抽共享 `ProtectionResult` builder，并补一个 route-order regression test。不要在迁移过程中先做大抽象，老铁，这玩意儿越抽越容易把审批门禁抽没了。

## 9. 本计划的完成标准

本 Worker S 文档 PR 完成即满足：

- 只新增 `docs/plans/2026-06-12-source-dispatch-decomposition-plan.md`。
- 覆盖当前 helper 尺寸、风险、候选边界、PR 顺序、validation、side-effect guards 和后续 rollout。
- 明确 Source Map review-only / explicit-review-only 边界，不把 descriptor 说成 automatic executor。
- `git diff --check` 通过。

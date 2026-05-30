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

## 阶段执行记录与剩余顺序

当前下一步：Phase 0-16 已完成，`remote-cdp` smoke 路径已接入，Playwright system Chrome smoke、CloakBrowser fixture smoke、Playwright breakpoint paused/callframe smoke、显式 evaluateOnCallFrame baseline、callframe evaluation policy baseline、mutation audit baseline、page-level mutation audit baseline、MutationObserver timeline baseline、debugger step-control baseline、paused-session continuation preflight、durable paused-session snapshot inspect-only baseline、single-run debugger timeline baseline、target-function wrapper baseline、source-level logpoint baseline、source map / bundle offset remap baseline、source-map bias / sourceRoot / indexed section remap baseline、module export hook baseline、module discovery baseline、runtime module cache / registry introspection baseline、custom runtime / module federation function-path candidate baseline、closure-scope function discovery baseline、native-web recon flow timeline baseline、flow timeline correlation hints、conservative correlation groups、group verification readiness、manual stitch candidates、review-gated stitch proposals、pending stitch proposal evidence promotion / review gate blocking、reviewer-approved stitched-flow materialization baseline、explicit flow timeline continuation baseline、auto-stitch dry-run scoring baseline、auto-stitch policy decision gate baseline、auto-stitch materialization plan baseline、review-approved auto-stitch materializer skeleton，以及 retained paused-session registry baseline 均已验证，MCP alias deprecation warning 已接入，最终 code review 已完成并修复 module-hook 路由、module hook path quoting 和 page-mutation global snapshot 副作用风险；MCP 物理拆包前置步骤已完成：RuntimeBackendRegistry 支持 `reverse_deepagent.runtime_backends` entry-point discovery，加载外部 backend registration 时不调用 backend factory；`legacy-mcp` registration / factory / alias warning 已从 coordinator 内联逻辑挪到 `reverse_deepagent.runtime.legacy_mcp`，并支持 `build_default_runtime_registry(include_legacy_mcp=False)` 构建不带 MCP backend 的 clean registry；`packages/reverse-deepagent-legacy-mcp/` optional plugin package 已拥有 legacy MCP registration / factory、config 和 stdio bridge 实现，core 侧 `reverse_deepagent.runtime.legacy_mcp` 只保留兼容 shim、默认命令常量、alias warning、doctor 代理和 install guidance，不再内置 legacy MCP factory fallback 或 stdio MCP transport；默认 registry 会先加载外部 entry points，若未安装 optional package，`legacy-mcp` / `mcp` 会返回结构化安装建议且不会先启动受管 Chrome。DeepAgents workspace contract indexed-only baseline 已落地，当前输出 `workspace/workspace-contract.json`，覆盖虚拟文件夹、子智能体角色、middleware chain 和现有扁平 artifact route。BrowserProvider smoke matrix / lifecycle baseline 已落地，doctor 可输出 metadata-only provider matrix，真实启动仍需显式 `--launch-browser-smoke`。后续仍需跨进程 live CDP paused execution continuation、任意 custom loader / async chunk graph / 深层 module federation 执行式分析、任意闭包内部函数 automatic wrapper hook、JS heap 级细粒度 mutation audit / object graph diff、richer Source Map name / URL / complex indexed section semantics、DeepAgents 虚拟文件夹真实迁移，以及自动全链路跨请求 timeline conflict resolver / rollback-audit writer / 无需审批 automatic materializer。Android / iOS / 小程序完整运行链路继续搁置，只保留 minimal probe / artifact export baseline。Step 5.1 到 Step 16 保留为已执行阶段记录，便于 review 和回溯。

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
- 后续仍需更完整的 conflict resolver、rollback / audit writer、materialization transaction log，以及真正自动化策略的默认关闭 gate。

### Step 15：Auto-stitch materialization plan baseline

交付物：

- `flow-timeline.json`：新增 `auto_stitch_materialization_plans`、`auto_stitch_materialization_plan_count` 和 `auto_stitch_materialization_summary`。
- `FlowTimelineManager`：对 policy-eligible decision 生成 plan-only materialization record，包含 target artifact、entry sequences、path、review requirements、conflict resolution、rollback plan 和 blocking conditions。
- `NativeWebRuntime`：explicit flow-timeline protection 和 recon artifact metadata 暴露 materialization plan count / summary。
- `tests/test_flow_timeline.py`、`tests/test_native_web_runtime.py`：覆盖默认无 plan、显式 allow-conflicts 策略生成 plan-only 记录，以及 `writes_artifact=false` / `would_materialize=false` / `automatic_stitching=false` 边界。

边界：

- materialization plan 只描述未来如何写入，不实际写 `stitched-flow.json`。
- 不替代 `stitch_review_decisions` 审批路径。
- 后续仍需更完整的 conflict resolver、rollback / audit writer、materialization transaction log，以及无需审批自动化策略的默认关闭 gate。

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

# reverse-deepagent 项目级 AGENTS 强制规则

## 0. 适用范围与优先级

- 本文件适用于 `/Users/mengma/reverse/reverse_agent` 整个仓库及其所有子目录。
- 每次 AI 在本仓库执行开发、修复、重构、文档、测试、提交、推送或 PR 相关任务时，都必须先遵守本文件。
- 必须读取并遵循：
  - [`开发者AI开发与PR提交流程.md`](./开发者AI开发与PR提交流程.md)
  - [`项目开发规范（AI协作）.md`](./项目开发规范（AI协作）.md)
  - 与当前任务直接相关的仓库文档（至少包括 `README.md`、`CONTRIBUTING.md`、`docs/runtime/browser-provider-architecture.md`、`docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`；涉及 legacy MCP 时再补读 `docs/runtime/jsreverser-mcp-setup.md`、`docs/ci/self-hosted-mcp-smoke.md`、`docs/design/reverse-deepagent-architecture.md`）
- `开发者AI开发与PR提交流程.md` 作为 GitHub / PR / 合并动作流程基线直接使用；但本仓库当前默认基线分支是 `main`，其中提到的 `dev` 在本仓库默认映射为 `main`，除非维护者明确指定其他分支。
- `项目开发规范（AI协作）.md` 已做本仓库适配；其中原本面向别的 JS 项目所写的结构示例只保留为通用方法论，不能覆盖本仓库 Python / DeepAgents 架构规则。
- 如果流程文档、README、历史计划或旧对话口径冲突，以当前仓库真实代码、当前 `AGENTS.md`、用户本轮明确要求为准；不能靠记忆或猜测。

## 1. 任务开场白规则

- 仅在用户下达明确任务、要求产出或执行动作时触发。
- 任何命令或工具调用前，必须先用一段中文说明“我理解的任务”和“接下来怎么做”。
- 开场白后立刻执行，不等待用户确认，除非存在无法合理推断且会造成破坏性后果的关键问题。
- 闲聊、问候、情绪交流不触发。

## 2. 语言、编码与换行

- 默认语言：中文。
- 技术术语保留英文，中文与半角英数字之间保留半角空格。
- 新增文本文件默认 UTF-8 + LF。
- 修改已有文件时优先保持原有换行风格。
- 若原文件是 UTF-8 with BOM，必须保持 BOM；例如 `项目开发规范（AI协作）.md` 当前就是 UTF-8 with BOM + LF。
- Shell 路径必须显式确认，包含空格、中文或特殊字符时必须加引号。
- Python / Node 写文件必须显式指定编码。
- 出现乱码、异常解析错误、`Unterminated string constant` 时，优先检查编码和换行。

## 3. 每次开发前的强制检查

开始任何代码或文档改动前，至少执行或核对：

```bash
git status --short --branch
git remote -v
git branch --show-current
```

如果任务涉及 GitHub PR、PR 评论、PR 合并或远端分支管理，还必须按 `开发者AI开发与PR提交流程.md` 检查：

```bash
gh --version
gh auth status
git fetch origin
```

要求：

- 不得在没看当前分支、远端和工作区状态的情况下开始写代码。
- 如果发现无法确认归属的脏改动，必须先说明，不得偷偷带进本次提交，也不得擅自删除。
- 不得假装执行过 GitHub 操作；`gh` 不可用、未登录、账号错误或权限不足时，必须明确报告。

## 4. 分支、提交、推送与 PR

- 本仓库当前默认分支为 `main`。
- 如果用户没有要求 PR，且当前任务语境是直接维护本仓库，可在当前分支按要求开发、提交和推送。
- 如果用户明确要求创建或更新 PR：
  - PR base 默认为 `main`。
  - 必须先同步最新 `origin/main`，确认分支没有落后。
  - 必须使用 `gh pr create/view/edit/merge` 的真实输出作为依据。
- 不得把 PR 指向 `master`，除非维护者明确改了仓库策略。
- 未经明确授权，不得擅自合并 PR、关闭 PR、删除远端分支。
- 必须区分“同步 PR 分支”和“合并 PR 到主分支”：只有 GitHub PR merge 动作完成并验证远端主分支前进，才算合并完成。
- 提交信息必须描述真实改动，禁止 `update`、`fix bug`、`AI 修改`、`修改一下` 这类空泛信息。

## 5. 本仓库架构与文件边界

本仓库是 Python / DeepAgents / Web 逆向项目：

- 核心源码：`src/reverse_deepagent/`
- 测试：`tests/`
- 脚本：`scripts/`
- 长期文档：`README.md`、`CONTRIBUTING.md`、`docs/`
- 运行时产物：`artifacts/`、`artifacts-*`，不要提交。

关键架构方向：

- `native-web + BrowserProvider + native collectors / hooks` 是 Web 逆向主线。
- `legacy-mcp` 是兼容后端。
- `mcp` / `jsreverser-mcp` 只作为 legacy alias 保留。
- 浏览器实现应通过 `BrowserProviderRegistry` / `reverse_deepagent.browser_providers` entry point 可插拔，不要把 MCP 当成新的抽象边界。
- MCP stdio transport、`JSReverserMcpConfig` 和真实 legacy MCP factory 归属 `packages/reverse-deepagent-legacy-mcp/` optional package；core 只保留 `reverse_deepagent.runtime.legacy_mcp` shim、默认命令常量、alias warning、doctor proxy、plugin delegation 和 install guidance。
- coordinator 不应直接依赖 Playwright、CDP、CloakBrowser 或 MCP tool name。
- 新增 runtime / provider / collector / hook / artifact schema 时，必须同步测试和文档。
- DeepAgents workspace contract 由 `src/reverse_deepagent/workspace_contract.py` 维护；新增或改变 subagent role、middleware checkpoint、workspace artifact、manifest key 或虚拟文件夹规划时，必须同步 `tests/test_workspace_contract.py`、README / runtime docs，并保持 `workspace/workspace-contract.json` 输出。
- `workspace/workspace-contract.json` 当前保持 indexed-only contract；现有扁平 `workspace/*.json` artifact 路径仍为 canonical path。`workspace/backend-artifact-manifest.json` 的 entry metadata 会为已登记 workspace artifact 提供 manifest-only `workspace_alias`，指向 `/workspace/<area>/...` foldered future path / `virtual://workspace/<area>/...` URI；没有 manifest alias、兼容覆盖和回归测试时，不得移动或重命名既有 artifact 路径。
- `review_workspace_dual_write_pilot_workflow` 只是 review-first workflow helper：它可以串联 readiness、pilot plan 和 observed scoped dual-write result verification，但不得运行 pipeline、启用双写、迁移路径、改变 canonical path、启动浏览器、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路；`write_result=true` 只能写 `workspace/workspace-dual-write-pilot-result.json` 审计结果。

重点文件变更要求：

- 改 runtime registry / coordinator：检查 `tests/test_coordinator.py`、`tests/test_runtime_registry.py`、相关 pipeline 测试。
- 改 workspace contract / subagent / middleware / artifact route / workspace review workflow：检查 `tests/test_workspace_contract.py`、`tests/test_workspace_artifact_reader.py`、`tests/test_coordinator.py`、相关 subagent / coordinator tool 暴露测试、README 和 runtime docs。
- 改 delivery executor / transaction journal / external delivery / state machine：检查 `tests/test_delivery_executors.py`、`tests/test_delivery_tools.py`、`tests/test_delivery_state_machine.py`、README 和 plan 文档；状态机默认必须保持 read-only，不得在 evaluator / transition planner 中执行文件、网络、manifest mutation 或恢复动作。
- 改 BrowserProvider / BrowserProviderRegistry：检查 `tests/test_browser_provider_*`、`tests/test_browser_smoke_matrix.py`、`tests/test_browser_provider_smoke_cli.py`、`tests/test_playwright_provider.py`、`tests/test_cloakbrowser_provider.py`、`tests/test_remote_cdp_provider.py`、`tests/test_native_web_runtime.py`、`tests/test_doctor.py`、README 和 runtime docs。BrowserProvider metadata / matrix / registration listing / smoke artifact metadata-only 路径默认必须 side-effect-free，不得调用 provider factory、启动浏览器、探测 CDP 端点或依赖 MCP；只有显式 `--launch-browser-smoke` 或等价开关才允许启动真实浏览器。
- 改 native collectors / hooks：检查 `tests/test_browser_collectors.py`、`tests/test_cdp_collectors.py`、`tests/test_browser_hooks.py`、`tests/test_breakpoint_manager.py`、`tests/test_function_hooks.py`、`tests/test_module_hooks.py`、`tests/test_source_logpoints.py`；涉及 `module-discovery` / `hook-module` 还必须同步 `tests/test_native_web_runtime.py` 的 protection 集成断言；涉及 runtime module cache introspection 时必须覆盖 `require.c` / `require.m` 可用与不可用的结构化结果；涉及 `module_runtime_paths`、custom object runtime、module federation exposed-module baseline、review-only module federation traversal graph / workflow plan、review-gated module federation traversal workflow execution、review-only module federation recursive traversal follow-up planning、review-gated module federation recursive traversal follow-up checkpoint、review-gated module federation recursive traversal next-step execution、review-only module federation recursive continuation journal / multi-step checkpoint plan、review-gated module federation recursive continuation checkpoint execution、async chunk graph / loader metadata baseline、review-only async chunk traversal graph / queue、review-only async chunk traversal workflow plan、review-gated async chunk traversal workflow execution、review-only bounded async chunk traversal loop plan、review-gated bounded async chunk traversal loop execution、review-only async chunk recursive traversal follow-up planning、review-gated async chunk recursive traversal follow-up checkpoint、review-gated async chunk recursive traversal next-loop execution、reviewed custom-loader execution、bounded custom-loader traversal continuation、review-only custom-loader traversal graph / queue、review-only multi-step custom-loader traversal workflow plan、review-gated custom-loader traversal workflow execution、review-only bounded custom-loader traversal loop plan、review-gated bounded custom-loader traversal loop execution / review-only recursive custom-loader traversal follow-up planning / review-gated custom-loader recursive traversal follow-up checkpoint、review-gated custom-loader recursive traversal next-loop execution、review-only custom-loader continuation workflow planning、review-gated custom-loader continuation journal、review-approved one-step custom-loader continuation execution、custom-loader module diff / hook candidate refresh 或 reviewed custom-loader module hook follow-through 时，必须覆盖 `tests/test_module_hooks.py` 的 `hook_kind` / `function-path` candidate、chunk graph side-effect policy、async chunk traversal workflow side-effect policy、async chunk traversal workflow execution side-effect policy、async chunk traversal loop plan side-effect policy、async chunk traversal loop execution side-effect policy、async chunk recursive traversal execution side-effect policy、custom-loader execution side-effect policy、custom-loader traversal workflow execution side-effect policy、custom-loader traversal loop execution side-effect policy、custom-loader recursive traversal execution side-effect policy、custom-loader continuation execution side-effect policy、custom-loader module diff side-effect policy 或 reviewed custom-loader module hook side-effect policy，以及 `tests/test_native_web_runtime.py` 的 native-web artifact metadata；涉及 `closure-function-discovery` / `closure-scope` / `closure-wrapper-replacement-plan` / `closure-wrapper-replacement-execution` 时，必须覆盖 `tests/test_closure_scope.py` 的 paused-callframe 只读候选证明、review-only wrapper replacement plan 或 reviewed same-process execution、`tests/test_native_web_runtime.py` 的 `closure-functions.json` / `closure-function-candidates.json` / `closure-wrapper-replacement-plan.json` / `closure-wrapper-replacement-execution.json` / `closure-wrapper-restore-plan.json` artifact 断言、`tests/test_hook_subagent.py` 的 review / restore warning、workspace contract 和 coordinator payload/category 映射，并证明 plan-only 路径无 wrapper install / runtime mutation / CDP command / callframe evaluation，execution 路径必须 explicit review approval + same-process retained pause + mutation audit + restore plan，且不得宣称已支持任意闭包函数自动 wrapper hook；涉及 `page-mutation-audit` / `mutation-observer-timeline` 时必须覆盖独立 manager 单测和 native-web protection artifact 断言；`mutation-observer-timeline` 必须保持显式触发，不得进入默认 recon，且不得复用 `mutation-audit.json` 混淆 callframe side-effect audit；涉及 source-map remap 时必须覆盖 `tests/test_source_maps.py` 和 `tests/test_source_logpoints.py`，至少说明 exact / bias / sourceRoot / indexed sections / `names` metadata / URL-like source equivalence / nested indexed-section stack 的支持边界，以及不 fetch 外部 source-map URL / section URL 的限制；涉及 paused-session 持久化或 live-continuation preflight 时必须同时覆盖 `continuation_preflight`、同进程 registry live continuation、durable snapshot inspect-only、`paused-session-live-continuation-preflight.json` 只读 blocker artifact 和不发送 CDP / 不 resume / 不 step / 不 evaluate 边界，不得宣称跨进程 live resume / step / evaluate 已支持；涉及 `flow-timeline` / `cross-request-timeline` 时必须覆盖 `tests/test_flow_timeline.py` 的 previous timeline continuation / source normalization / correlation hints / conservative correlation groups / group verification readiness / manual-only `stitch_candidates` / `auto_stitch_dry_runs` dry-run scoring / `auto_stitch_policy_decisions` policy gate / `auto_stitch_materialization_plans` plan-only materialization baseline / review-approved `auto_stitch_materialization_results` baseline / `auto_stitch_materialization_audit_entries` / `auto_stitch_materialization_rollback_plans`，以及 `tests/test_native_web_runtime.py` 的 recon pipeline `workspace_flow_timeline`、manifest category、entry `correlation` 字段、`correlation_groups[].verification` 字段、`stitch_candidates[].automatic_stitching=false`、`auto_stitch_dry_runs[].would_materialize=false`、`auto_stitch_policy_decisions[].would_materialize=false`、未审批 `auto_stitch_materialization_plans[].writes_artifact=false`、已审批 `auto_stitch_materialization_results[].writes_artifact=true` 和 explicit `flow-timeline.json` / `auto-stitch-materialization-results.json` / `stitched-flow-materialization-audit.json` / `stitched-flow-rollback-plan.json` artifact 断言，且不得宣称已支持无需审批的自动全链路跨请求 materialization。
- 改 CLI / doctor / workflow：检查 `tests/test_doctor.py`、`tests/test_console_script.py`、`tests/test_run_demo*.py`、涉及 workspace dual-write smoke 时检查 `tests/test_workspace_dual_write_smoke.py`，并同步 README 和相关 docs。
- 改 rebuild / strategy：检查 `tests/test_rebuild_artifacts.py`、`tests/test_strategy_*`。

## 6. 规划与阶段化执行

- 用户提到 `plan`、`do-plan`、规划、继续推进、按顺序执行时，必须使用 `task-plan` 相关流程。
- 多步骤开发必须维护一个简洁计划，并随完成状态更新。
- 每个阶段完成后必须自检：
  - 相关代码是否都改到。
  - 文档是否同步。
  - 测试或静态检查是否覆盖关键路径。
  - 是否混入无关改动。
  - 是否引入乱码、错码、冲突标记或旧口径。
- 阶段自检未通过，不得进入下一阶段或提交。

## 7. 测试与验证

本仓库不是 npm / bun 项目。除非某个子任务明确涉及 Node 工具，否则不要套用 `npm test` / `bun test`。

代码改动最低验证：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m compileall -q "src/reverse_deepagent" "tests"
```

定向测试按改动范围选择，例如：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest tests.test_coordinator tests.test_doctor -v
```

跨模块、架构性、提交前全量回归：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest discover -s tests -v
```

文档-only 改动最低验证：

```bash
git diff --check
```

并人工检查：

- 中文无乱码。
- 链接路径正确。
- 命令示例符合当前仓库实际。
- 没有把旧 `mcp` 默认路径、旧分支名、旧执行方式写回新文档。

测试失败时不得提交，除非用户明确要求保留失败状态用于排查；这种情况必须在回复中说明失败命令和失败原因。

## 8. Diff review 与提交前检查

提交前必须至少执行：

```bash
git status --short
git diff --stat
git diff --check
```

并根据任务范围查看完整 diff。

检查重点：

- 只包含本次任务相关文件。
- 没有临时调试代码。
- 没有无关格式化、无关重命名、生成物、缓存、runtime artifacts。
- 没有冲突标记：`<<<<<<<`、`=======`、`>>>>>>>`。
- 没有敏感信息：API key、cookie 值、Authorization、proxy 密码、真实 token。
- 文档和代码口径一致。

## 9. 文档同步规则

以下变更必须同步文档：

- runtime / backend / provider / collector / hook 能力变化。
- CLI 参数、doctor 行为、workflow 行为变化。
- artifact schema、workspace 输出、manifest metadata 变化。
- BrowserProvider / CloakBrowser / legacy MCP 迁移口径变化。
- 新增或删除公开脚本、console entrypoint、重要测试命令。

常见同步位置：

- `README.md`
- `CONTRIBUTING.md`
- `docs/runtime/*.md`
- `docs/plans/*.md`
- `.codex/plans/*.md`
- `.github/workflows/*.yml`

不要只在临时计划或聊天里说明，长期行为变化必须落到仓库文档。

## 10. AGENTS 与规范维护硬性要求

`AGENTS.md` 不是一次性文件，是本仓库 AI 协作的强制入口。任何会改变长期开发方式、模块边界、验证命令、运行时能力或提交流程的改动，都必须同步维护它。

维护规范时，优先复用本机可复用 skill：

- `$project-agents-governance`
- 路径：`/Users/mengma/.codex/skills/project-agents-governance`

必须更新 `AGENTS.md` 或重新核对它的场景：

- 新增、删除、重命名顶层目录、核心源码目录、测试目录、文档目录、脚本目录或运行产物目录。
- 新增或改变 runtime / backend / provider / collector / hook / breakpoint / artifact schema。
- 改变 BrowserProvider / CloakBrowser / legacy MCP 迁移口径。
- 改变 CLI 参数、doctor 行为、workflow、CI、测试命令或 console entrypoint。
- 改变默认分支、PR base、提交、推送、合并策略。
- 新增 Android、iOS、小程序、桌面端、云端任务等平台扩展边界。
- 发现 `AGENTS.md`、`项目开发规范（AI协作）.md`、`README.md`、`CONTRIBUTING.md`、`docs/` 或 `.codex/plans/` 之间存在冲突。

维护方式必须按下面顺序执行：

1. 先读取当前 `AGENTS.md`、两份流程规范和任务相关长期文档。
2. 再核对真实仓库结构、真实入口、真实测试命令和真实分支策略。
3. 使用 `$project-agents-governance` 的模板或脚本生成/对照规范草案。
4. 只保留符合本仓库真实情况的规则，删除模板里不适用的项目。
5. 保持已有文件编码和换行风格；尤其不要破坏中文文件的 BOM / CRLF。
6. 运行 `git diff --check`，并人工 review diff，确认没有旧项目口径、错路径、错分支、错命令和乱码。

禁止事项：

- 不得只在聊天记录里宣布长期规则变更，必须落到仓库文档。
- 不得把别的项目目录、测试命令、分支策略直接复制进本仓库。
- 不得加入没有可执行验证方式的空泛规则。
- 不得为了省事把过时的 `mcp` 主线、旧浏览器抽象或旧测试基线写回规范。

## 11. 大项目自动触发规范治理

满足任一条件时，必须自动触发“规范确认 / 计划 / 适配”阶段，先处理规范和计划，再进入代码实现：

- 任务预计改动 3 个及以上顶层目录。
- diff 预计超过 8 个文件，且同时涉及代码、测试、文档、workflow / CI 中至少 2 类。
- 任务涉及架构迁移、运行时拆分、浏览器底座替换、MCP 去耦、DeepAgents 子智能体编排、artifact schema、平台扩展。
- 用户要求“重构”“迁移”“拆掉”“可插拔”“长期维护”“大项目规范化”“多 agent 协同”。
- 当前规范无法解释将要做的改动，或现有规范与真实代码冲突。

自动触发后的最低动作：

1. 维护一个阶段化计划。
2. 明确本次是否需要更新 `AGENTS.md` 和 `项目开发规范（AI协作）.md`。
3. 如需要，先完成规范更新并通过 `git diff --check`。
4. 再继续代码实现、测试和文档同步。
5. 最终回复必须说明规范是否更新、为什么更新或为什么不需要更新。

## 12. Insight 使用规则

复杂根因分析、架构决策、关键功能实现、复杂 bug 修复时，可以使用固定格式：

```text
`★ Insight ─────────────────────────────────────`
- 要点 1
- 要点 2
- 要点 3
`─────────────────────────────────────────────────`
```

简单确认、常规配置、纯格式化、小文档改动不需要 Insight。

## 13. 表达风格

- 默认中文，专业简洁。
- 可以直接指出风险和盲区，不要讨好式附和。
- 可以有一点东北味儿，但不能牺牲信息密度。
- 不要写固定机器人腔，例如“自动回复”“AI 分析结果如下”。
- 结论必须基于真实文件、真实命令输出、真实 diff、真实测试结果。

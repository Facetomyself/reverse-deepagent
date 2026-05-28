# Reverse DeepAgent 计划（按架构设计更新）

## 1. Plan Task Card

```text
task_card:
- task_description: 基于 deepagents 搭建一个高集成度的逆向专用 agent，统一整合本机 js-reverse skill、jsreverser-mcp 能力与可复用脚本/参考资产，首期聚焦 Web / JS 逆向，预留 Android / iOS / 小程序扩展空间。
- mode: planning
- plan_target: <repo-root>/docs/plans/2026-05-26-deepagents-js-reverse-agent-plan.md
- constraints: 当前阶段以规划文档和任务同步为主，不修改业务实现逻辑；后续执行必须遵守 docs/design/reverse-deepagent-architecture.md 的分层设计与输出契约。
- execution_flags: dry-run
```

## 2. 规划状态

当前规划状态：**已完成架构设计与 demo 落地验证，进入下一阶段深化**。

已完成输入依据：

- 架构设计文档：`<repo-root>/docs/design/reverse-deepagent-architecture.md`
- deepagents 学习资料：`<repo-root>/docs/reference/deepagents/`
- js-reverse 统一 skill：`~/.codex/skills/js-reverse/`

当前结论：

- 系统主结构采用：`方法层 + 编排层 + 执行层`
- `deepagents` 负责编排、规划、虚拟文件系统、子任务隔离
- `js-reverse` 负责 route / playbook / capability / protection / evidence 规范
- `jsreverser-mcp` 当前作为 **runtime backend** 使用，而不是主架构中心
- 首版目标收敛为：**Web Reverse Demo v0**
- 当前 demo 已完成真实 Chrome + MCP smoke，证明可在可调端口上稳定拉起、接入和收尾

## 3. 目标定义

### 3.1 核心目标

构建一个 **Reverse DeepAgent Demo**，验证以下闭环：

1. 接收逆向任务描述
2. 归一化为 `Reverse Task Card`
3. 进行 route 决策
4. 委派 Web Recon 子 Agent 执行基础侦察
5. 必要时委派 Protection 子 Agent 进行最小修补
6. 产出统一结构化结果 + artifacts

### 3.2 首阶段非目标

以下内容仍然排除在首版之外：

- Android / iOS / 小程序真实执行链落地
- 全自动 sign 重建与 replay 通杀
- 多租户平台化、服务化部署
- 大规模长期记忆系统
- 全量替换或废弃 MCP

## 4. 设计对齐结果

本计划已按设计文档收口为以下结构。

### 4.1 多 Agent 结构

首版采用 **1 个主 Agent + 3 个专用子 Agent**：

- `coordinator`：总控、规划、委派、证据收口
- `router`：route 决策
- `web_recon`：Web 侦察执行
- `protector`：阻塞修补

### 4.2 输出结构

最终输出固定为 3 层：

1. `Structured JSON`
2. `Markdown Report`
3. `Artifact Index`

### 4.3 虚拟文件系统结构

```text
/workspace/
  task-card.md
  route-decision.json
  todos.md
  recon-notes.md
  evidence-candidates.json
  evidence-validated.json
  protection-result.json
  final-result.json

/artifacts/
  reports/
  exports/
  screenshots/
  session/
  rebuild/

/memories/
  sites/
  protections/
  patterns/
```

### 4.4 Backend 策略

采用 `CompositeBackend`：

- `/workspace/` -> `StateBackend`
- `/artifacts/` -> `FilesystemBackend`
- `/memories/` -> `StoreBackend`（已启用，支持共享 store 与 namespace 隔离）

### 4.5 执行抽象策略

上层不直接绑定 MCP 原子工具名，而是通过 runtime adapter 调用高层动作：

- `ensure_browser_session()`
- `route_reverse_task(...)`
- `run_web_recon(...)`
- `apply_minimal_protection(...)`
- `export_reverse_artifacts()`

## 5. 当前目录与实现落点

当前项目目录已整理完成，后续实现以这些路径为准：

- 设计文档：`<repo-root>/docs/design/reverse-deepagent-architecture.md`
- 计划文档：`<repo-root>/docs/plans/2026-05-26-deepagents-js-reverse-agent-plan.md`
- 源码目录：`<repo-root>/src/reverse_deepagent/`
- 脚本目录：`<repo-root>/scripts/`
- 产物目录：`<repo-root>/artifacts/`
- 测试目录：`<repo-root>/tests/`

## 5.1 当前 execution 进度

当前已完成：

- Phase 1：Schema 与契约落地
- Phase 2：Runtime Adapter 抽象层
- Phase 3：Coordinator 与 Router 最小骨架
- Phase 4：Web Recon 子 Agent 骨架
- Phase 5：Protection 与 Artifact 导出骨架
- Phase 6：最小 Demo 脚本与自动化验证
- Phase 7：候选函数验证与 replay 闭环
- Phase 8：纯算导出与 replay delivery

当前验证结果：

- `schemas` 已通过导入与实例化验证
- `runtime adapter` 已通过 fake bridge 单元测试
- `route_tools` 已完成 manifests 驱动的最小路由验证
- `web_recon / protection / artifact` 工具包装已通过测试
- `scripts/run_demo.py` 可运行，并能生成 JSON / Markdown / artifact index
- `StdioMcpBridge` 已完成真实 `jsreverser-mcp` stdio 协议探测，`initialize -> tools/list` 已验证通过
- `scripts/run_demo.py --runtime mcp` 已能启动真实 MCP 后端；当 9222 Chrome 不可用时会结构化返回 `status=failed` 和 `next_action=ensure_browser_session`
- 已新增可调 Chrome debug 启停脚本，并接入 `run_demo.py --runtime mcp --ensure-chrome`
- 已完成真实 Chrome smoke：`--chrome-debug-port 9445` + `--chrome-user-data-dir /tmp/reverse-agent-chrome-9445` 可成功拉起、接入并自动收尾，端口不再残留监听
- 已补齐真实 MCP 返回形态归一化：适配层能解析 `check_browser_health` / `list_pages` 的 Markdown + fenced JSON 输出，并对页面列表去重
- 已修正 `build_reverse_agent()` 与当前 deepagents API 的版本偏差：不再向 `create_deep_agent()` 传入不存在的 `profile` 参数
- 已新增纯 Python `deepagents` invoke smoke：`scripts/run_deepagent_smoke.py` 可在不依赖外部模型与真实浏览器的情况下验证主 Agent -> route tool -> ToolMessage 闭环
- 已新增纯 Python 子 Agent 委派 smoke：`scripts/run_deepagent_subagent_smoke.py` 可验证主 Agent -> `task` tool -> general-purpose 子 Agent -> ToolMessage 闭环
- 已补 `pyproject.toml`，并通过 `uv pip install --python <repo-root>/.venv/bin/python -e .` 完成 editable 安装
- 当前测试已可在不设置 `PYTHONPATH` 的情况下通过
- 已将 `scripts/run_demo.py` 中的核心流程抽离到 `src/reverse_deepagent/coordinator.py`，形成包内稳定入口 `run_reverse_pipeline()`
- `scripts/run_demo.py` 已降级为薄 CLI，避免后续入口重复实现 task card、route、recon、artifact 输出逻辑
- 已在 `pyproject.toml` 中声明 console script：`reverse-agent-demo = reverse_deepagent.cli:main_demo`
- 已验证 `reverse-agent-demo --runtime mock` 可直接运行并生成标准 artifacts
- 已新增本地 Web sign fixture：`reverse-agent-fixture` 提供 `/app.js`、`buildSign()`、`x-sign` 和 `/api/search`
- 已新增 fixture smoke 命令：`reverse-agent-fixture-smoke`
- 已验证真实 MCP + 受管 Chrome 对 fixture smoke 可达到 `status=success`、`next_action=move_to_source_analysis`
- 已增强 `JSReverserRuntime` 对真实 MCP Markdown 输出的解析：支持 `network_request` 的 `reqid=...` 行和 `search_in_sources` 的 `[script] url:line` 行
- 已实现证据晋升：从目标请求自动调用 `get_request_initiator`，从源码命中自动调用 `get_script_source`
- 已验证真实 MCP fixture smoke 产出 `request-initiators.json` 与 `source-contexts.json` artifact 引用
- 已实现候选函数卡片：从 source context、source hit、related request、initiator 合并生成 `function-candidates.json`
- 已让 workspace 虚拟 artifact 真实落盘，当前会写入 network/source/initiator/context/function-candidates 等 JSON 文件
- 已实现候选函数 runtime validation：从候选函数卡片进入页面运行时，验证函数可定位、可调用、源码片段完整性与 sign 输出形态
- 已实现 replay 校验：对可计算出的 sign 复放 `/api/search`，并校验服务端 echo 的 `x-sign`
- 已新增验证类 workspace artifact：`function-validations.json` 与 `function-validation-summary.json`
- 已实现纯算导出：从已验证候选生成 `workspace/rebuild-plan.json` 与 `rebuild/sign_rebuild.py`
- 已实现浏览器外 replay delivery：生成 `rebuild/replay_demo.py`，可脱离 Chrome 直接复放 fixture API
- 已实现 Scrapy 接入草案：生成 `rebuild/scrapy_middleware.py`
- 已实现 deepagents rebuild delivery 子 Agent / 工具：`build_rebuild_delivery`，支持从 `FinalResult` 直接生成交付包
- 已新增 deepagents rebuild delivery smoke：可通过主 Agent 的工具调用生成 `RebuildResult`
- 已增强 pure extraction 策略字段：`pure_extractable`、`manual_port_required`、`runtime_context_required`、`dependencies`、`confidence_reason`
- 已扩展算法策略识别：`md5`、`sha1`、`sha256`、`hmac-sha256`、`base64`、`urlencode`
- 已实现 WASM / VM / 混淆 / 反调试 / 动态 secret 的保守 triage detector：优先于 hash / encoding 策略运行，命中后输出 runtime-assisted / partial 计划并阻断假纯算交付
- 已新增运行时上下文依赖识别：`cookie`、`localStorage`、`sessionStorage`、`navigator`、`timezone`、`canvas`
- 已完成 fixture profile 矩阵：`default`、`sha256`、`base64`、`context-localstorage`
- Phase 11 已验证真实 MCP profile smoke：`sha256` / `base64` 可纯算，`context-localstorage` 在未采集上下文时会正确阻断 pure extraction
- 当前全量验证结果：`python -m unittest discover -s <repo-root>/tests -v` 通过，36 个测试全部成功
- 已实现运行时上下文采集：`runtime-context.json`
- 已实现 context-aware delivery：`context-localstorage` profile 可采集 `localStorage.device_id` 并生成交付包
- 已验证真实 MCP profile smoke：`context-localstorage` 现在可生成 context-aware `sign_rebuild.py` 与 `replay_demo.py`
- 当前全量验证结果：`python -m unittest discover -s <repo-root>/tests -v` 通过，37 个测试全部成功

## 6. execution 模式实施计划

下面这部分是给后续 `do-plan` 直接执行用的，不再只是概念规划。

### Phase 1：Schema 与契约落地

目标：

- 明确数据结构边界
- 固定 Agent 间交接格式
- 固定最终输出格式

交付物：

- `src/reverse_deepagent/schemas/task_card.py`
- `src/reverse_deepagent/schemas/router_result.py`
- `src/reverse_deepagent/schemas/recon_result.py`
- `src/reverse_deepagent/schemas/protection_result.py`
- `src/reverse_deepagent/schemas/final_result.py`

验收标准：

- 所有 schema 可导入
- 字段覆盖设计文档中的输入 / 输出契约
- `facts / inferences / unknowns` 结构固定

### Phase 2：Runtime Adapter 抽象层

目标：

- 隔离 MCP 实现细节
- 提供稳定的执行语义接口

交付物：

- `src/reverse_deepagent/runtime/base.py`
- `src/reverse_deepagent/adapters/jsreverser.py`
- 统一接口定义：
  - `ensure_browser_session`
  - `run_web_recon`
  - `apply_minimal_protection`
  - `export_reverse_artifacts`

验收标准：

- 主 Agent 与子 Agent 不直接依赖 MCP tool name
- 适配层能返回标准化 Python 数据结构

### Phase 3：Coordinator 与 Router 子 Agent

目标：

- 组装 deepagents 主 Agent
- 打通 task card -> route 的最小闭环

交付物：

- `src/reverse_deepagent/agent.py`
- `src/reverse_deepagent/coordinator.py`
- `src/reverse_deepagent/subagents/router.py`
- `src/reverse_deepagent/tools/route_tools.py`
- `src/reverse_deepagent/prompts/coordinator.txt`
- `src/reverse_deepagent/prompts/router.txt`

验收标准：

- 能从自然语言任务生成 `Reverse Task Card`
- 能稳定输出 `mode / playbook / stage / next_action`

### Phase 4：Web Recon 子 Agent

目标：

- 打通基础 Web 侦察能力
- 完成候选证据落盘

交付物：

- `src/reverse_deepagent/subagents/web_recon.py`
- `src/reverse_deepagent/tools/browser_tools.py`
- `src/reverse_deepagent/tools/recon_tools.py`
- `src/reverse_deepagent/prompts/web_recon.txt`

验收标准：

- 能完成浏览器健康检查
- 能完成页面侦察 / request / source / initiator 基础取证
- 能生成 `/workspace/evidence-candidates.json`、`/workspace/evidence-validated.json` 与 `/workspace/evidence-promotion.json`

### Phase 5：Protection 与 Artifact 导出

目标：

- 打通最小 protection 链路
- 补齐报告与导出物

交付物：

- `src/reverse_deepagent/subagents/protector.py`
- `src/reverse_deepagent/tools/protection_tools.py`
- `src/reverse_deepagent/tools/artifact_tools.py`
- `src/reverse_deepagent/prompts/protector.txt`

验收标准：

- 至少支持 1~2 个最常见 protection
- 能生成 final JSON、Markdown 报告、artifact index

### Phase 6：Demo 脚本与验证

目标：

- 形成可直接运行的最小 Demo
- 完成样例任务验证

交付物：

- `scripts/run_demo.py`
- `scripts/run_deepagent_smoke.py`
- `scripts/run_deepagent_subagent_smoke.py`
- `scripts/run_fixture_server.py`
- `scripts/run_fixture_smoke.py`
- `pyproject.toml`
- console script：`reverse-agent-demo`
- console script：`reverse-agent-fixture`
- console script：`reverse-agent-fixture-smoke`
- 最小测试样例
- 一组 artifacts 示例

验收标准：

- `run_demo.py` 可运行
- `run_demo.py` 只负责 CLI 参数解析，核心流程由 `run_reverse_pipeline()` 负责
- editable 安装后可直接执行 `reverse-agent-demo`
- 能对一个 Web 测试目标产出结构化结果
- 输出包含 `facts / inferences / unknowns / next_action / confidence`
- 真实 MCP smoke 可在可调端口上完成 `ensure-chrome -> recon -> stop-chrome` 闭环
- 真实 MCP 返回的 Markdown 形态不会打穿适配层
- `build_reverse_agent()` 可成功构建当前版本 deepagents 图，并通过 mock tool-calling model 完成一次 `agent.invoke()`
- 主 Agent 可通过 deepagents 内置 `task` 工具委派 general-purpose 子 Agent，并把子 Agent 结果回收到主线程消息链
- 包可通过 uv editable 安装，测试命令不再依赖手动 `PYTHONPATH`
- 本地 sign fixture 可自检并可作为真实 MCP smoke 目标
- 真实 MCP fixture smoke 能同时产生网络请求证据与源码命中证据
- Web recon 能把网络/源码命中晋升为请求发起链路和源码上下文证据
- Web recon 能生成候选 sign 函数卡片，fixture 当前稳定生成 `buildSign` 和 `search`
- artifact 引用必须有对应真实文件，不能只停留在 `virtual://workspace/...`

### Phase 7：候选函数验证与 replay 闭环

目标：

- 把候选函数从“证据卡片”提升为“已验证候选”
- 验证函数是否能在 runtime scope 中定位、调用并产出 sign
- 用验证得到的 sign 做最小 replay，形成可用 / 不可用结论

交付物：

- `JSReverserRuntime._validate_function_candidates(...)`
- `JSReverserRuntime._summarize_function_validations(...)`
- `virtual://workspace/function-validations.json`
- `virtual://workspace/function-validation-summary.json`
- 真实落盘文件：
  - `workspace/function-validations.json`
  - `workspace/function-validation-summary.json`

验收标准：

- mock runtime 能返回 replay-ready 的验证结果
- fixture 中的 `buildSign` 候选能完成 runtime validation
- replay 成功时 `next_action` 推进为 `extract_pure_logic_and_build_replay`
- validation artifact 必须真实落盘，不能只保留虚拟引用
- 单元测试覆盖验证 evidence / artifact / next_action / review-gate

### Phase 8：纯算导出与 replay delivery

目标：

- 把已验证候选函数提升为可迁移的交付包
- 生成浏览器外可运行的纯 Python sign 计算脚本
- 生成可直接对 fixture API 做 HTTP replay 的 demo
- 生成 Scrapy middleware 草案，为后续采集框架集成预留位置

交付物：

- `src/reverse_deepagent/rebuild.py`
- `workspace/rebuild-plan.json`
- `rebuild/sign_rebuild.py`
- `rebuild/replay_demo.py`
- `rebuild/scrapy_middleware.py`
- artifact index 中的 `rebuild_artifacts`

验收标准：

- `rebuild-plan.json` 能描述候选函数、算法策略、验证状态、replay URL 和输出文件
- `sign_rebuild.py` 能独立完成 sample self-check
- `replay_demo.py` 能在不依赖浏览器的情况下复放 fixture `/api/search`
- `scrapy_middleware.py` 不强依赖 Scrapy import，可作为项目接入草案
- 单元测试覆盖“生成 replay demo 并脱离浏览器请求 fixture API”
- 真实 MCP fixture smoke 能产出 rebuild artifacts，并通过 `sign_rebuild.py` self-check

### Phase 9：deepagents rebuild delivery 编排增强

目标：

- 把 rebuild delivery 变成 deepagents 主编排中的正式能力
- 让主 Agent 能通过 `build_rebuild_delivery` 工具或 `rebuild_delivery` 子 Agent 委派交付任务
- 保持 delivery 与 recon / validation 的上下文隔离

交付物：

- `src/reverse_deepagent/schemas/rebuild_result.py`
- `src/reverse_deepagent/tools/rebuild_tools.py`
- `src/reverse_deepagent/subagents/delivery.py`
- `src/reverse_deepagent/prompts/delivery.txt`
- `scripts/run_deepagent_delivery_smoke.py`

验收标准：

- 主 Agent 可调用 `build_rebuild_delivery` 工具生成 `RebuildResult`
- delivery subagent 可独立接收已验证结果并生成交付包
- 交付结果包含 `rebuild_plan`、`generated_files`、`artifacts`、`next_action`
- build_reverse_agent 默认接入 delivery 能力，但不破坏原有 route / web_recon / protection 链路
- new smoke 和单元测试通过

### Phase 10：算法策略扩展与证据驱动 pure extraction

目标：

- 让 rebuild delivery 不只支持 fixture 算法，也能识别常见 Web sign 纯算模式
- 用证据字段明确区分“可纯算移植”和“需要运行时上下文 / 人工移植”
- 避免 Agent 在 cookie / localStorage / 指纹依赖场景里误报 ready

交付物：

- `rebuild-plan.json` 新增 `pure_extraction` 字段
- `algorithm_strategy` 新增 `dependencies`、`template`、`salt`、`confidence_reason`
- 策略识别覆盖：
  - `md5_keyword_timestamp`
  - `sha1_keyword_timestamp`
  - `sha256_keyword_timestamp`
  - `hmac_sha256_keyword_timestamp`
  - `base64_keyword_timestamp`
  - `urlencode_keyword_timestamp`
- `sign_rebuild.py` 支持 hash / hmac / base64 / urlencode 类纯算渲染

验收标准：

- md5 类 source context 可生成 self-check 通过的 `sign_rebuild.py`
- 带 `localStorage` 等运行时依赖的 source context 必须判定为 `pure_extractable=false`
- `manual_port_required` 与 `runtime_context_required` 字段必须明确给出
- 真实 fixture MCP smoke 不受策略扩展影响

### Phase 11：fixture 矩阵与多策略 smoke

目标：

- 让 fixture 能按 profile 模拟不同类型的逆向场景
- 为 hash、encoding、context-dependent 三类策略提供真实 smoke 验证面
- 让 smoke 命令能显式选择 profile，便于后续回归和扩展

交付物：

- `FixtureProfile` / `FIXTURE_PROFILE_VALUES`
- `reverse-agent-fixture --profile <name>`
- `reverse-agent-fixture-smoke --profile <name>`
- profile 覆盖：
  - `default`
  - `sha256`
  - `base64`
  - `context-localstorage`

验收标准：

- `app.js` 会按 profile 生成不同的 buildSign 逻辑
- `healthz` 会回传 profile 元数据
- `sha256` profile 的真实 MCP smoke 可生成 `sha256_keyword_timestamp` rebuild plan
- `context-localstorage` profile 在没有 runtime context artifact 时会阻断 pure extraction
- unit test / smoke / docs 都要同步更新

### Phase 12：运行时上下文采集与 context-aware delivery

目标：

- 将 runtime-dependent sign 场景从“阻断纯算”升级为“采集上下文后交付”
- 让 `runtime-context.json` 成为正式 workspace artifact
- 支持 localStorage / cookie / navigator 等上下文采集与回放注入

交付物：

- `runtime-context.json`
- `context-aware` rebuild-plan 字段
- `context-aware` `sign_rebuild.py` / `replay_demo.py`

验收标准：

- `context-localstorage` profile 能采集 `localStorage.device_id`
- `rebuild-plan.json` 可标记 `context_aware_extractable=true`
- 生成的 `sign_rebuild.py` 可使用采集到的上下文进行 self-check
- 生成的 `replay_demo.py` 可在不依赖 Chrome 的情况下重新复放请求
- `runtime-context.json` 必须真实落盘

### Phase 13：runtime context coverage 扩展与 context stability diff

目标：

- 将 context-aware delivery 从 `localStorage` 扩展到 `cookie` 与 `navigator`
- 让运行时上下文稳定性摘要成为正式 workspace artifact
- 验证 `base64 + cookie` 与 `sha256 + navigator.userAgent` 两条浏览器外 self-check 链路

交付物：

- fixture profile：`context-cookie`
- fixture profile：`context-navigator`
- `workspace/runtime-context-diff.json`
- cookie-aware `sign_rebuild.py` 渲染
- navigator-aware `sha256` `sign_rebuild.py` 渲染

验收标准：

- `context-cookie` profile 能采集 `cookie.device_id` 并生成 `base64_keyword_timestamp` context-aware delivery
- `context-navigator` profile 能采集 `navigator.userAgent` 并生成 `sha256_keyword_timestamp` context-aware delivery
- `runtime-context-diff.json` 会真实落盘，当前为 `single_sample` 稳定性摘要
- 受管 Chrome smoke 结束后 `chrome_stop.ok=true`，调试端口不残留
- 单元测试覆盖 fixture profile、context-aware renderer 与 runtime context diff

验证结果：

- `context-cookie` 真实 MCP smoke：`ready=true`，`context_aware_extractable=true`，`runtime_context_required=["cookie"]`，`captured_runtime_context=["cookie"]`，`sign_rebuild.py` self-check 通过
- `context-navigator` 真实 MCP smoke：`ready=true`，`context_aware_extractable=true`，`runtime_context_required=["navigator"]`，`captured_runtime_context=["navigator"]`，`sign_rebuild.py` self-check 通过
- 全量单测：`Ran 40 tests ... OK`

### 里程碑状态

- Phase 1：已完成
- Phase 2：已完成
- Phase 3：已完成
- Phase 4：已完成
- Phase 5：已完成
- Phase 6：已完成
- Phase 7：已完成
- Phase 8：已完成
- Phase 9：已完成
- Phase 10：已完成
- Phase 11：已完成
- Phase 12：已完成
- Phase 13：已完成

## 7. 当前推荐执行顺序

后续进入 `do-plan` 时，严格按下面顺序推进：

1. 完成 `schemas`
2. 完成 `runtime adapter`
3. 完成 `coordinator + router`
4. 完成 `web_recon`
5. 完成 `protector + artifacts`
6. 完成 `run_demo.py` 与最小验证
7. 完成候选函数验证与 replay 闭环
8. 完成纯算导出与 replay delivery
9. 完成 deepagents rebuild delivery 编排增强
10. 完成算法策略扩展与证据驱动 pure extraction
11. 完成 fixture 矩阵与多策略 smoke
12. 完成运行时上下文采集与 context-aware delivery
13. 完成 runtime context coverage 扩展与 context stability diff

当前这版执行结果说明：上述 13 个阶段已经全部落地到可运行状态，后续 do-plan 的重点应切到更真实的 Web 样例、更多算法策略库扩展、运行时上下文自动补全，以及 Android / iOS / 小程序 adapter 预留，而不是继续停在 demo 级脚手架上。

新增验证入口：

- `scripts/run_deepagent_smoke.py`：验证 `deepagents` 主 Agent invoke 与 route tool 闭环
- `scripts/run_deepagent_subagent_smoke.py`：验证 `deepagents` 子 Agent 委派闭环
- `scripts/run_demo.py --runtime mcp --ensure-chrome`：验证真实 Chrome + MCP runtime 闭环
- `reverse-agent-fixture-smoke --runtime mcp --ensure-chrome`：验证本地 sign fixture 的真实 Web 逆向闭环
- `reverse-agent-fixture-smoke --runtime mcp --ensure-chrome` 当前还验证 `get_request_initiator` / `get_script_source` 证据晋升链路
- `reverse-agent-fixture-smoke --runtime mcp --ensure-chrome` 当前还验证 `function-candidates.json` 候选函数卡片输出
- `reverse-agent-fixture-smoke --runtime mcp --ensure-chrome` 当前还验证 `function-validations.json` / `function-validation-summary.json` 候选验证与 replay 输出
- `reverse-agent-fixture-smoke --runtime mcp --ensure-chrome` 当前还验证 `rebuild-plan.json`、`sign_rebuild.py`、`replay_demo.py`、`scrapy_middleware.py` 纯算交付包输出
- `scripts/run_deepagent_delivery_smoke.py` 当前可验证主 Agent 的 `build_rebuild_delivery` 工具调用闭环
- `tests/test_rebuild_artifacts.py` 当前还验证 md5 策略 self-check 与 `localStorage` 运行时依赖阻断逻辑
- `reverse-agent-fixture --profile sha256/base64/context-localstorage` 当前可切换 fixture profile
- `reverse-agent-fixture-smoke --profile sha256` 当前可走真实 MCP + 受管 Chrome 的 hash 策略 smoke
- `reverse-agent-fixture-smoke --profile base64` 当前可走真实 MCP + 受管 Chrome 的 encoding 策略 smoke
- `reverse-agent-fixture-smoke --profile context-localstorage` 当前可采集 runtime context 并生成 context-aware delivery
- `reverse-agent-fixture-smoke --profile context-cookie` 当前可采集 cookie context 并生成 context-aware delivery
- `reverse-agent-fixture-smoke --profile context-navigator` 当前可采集 navigator context 并生成 context-aware delivery
- `workspace/runtime-context-diff.json` 当前可输出单样本稳定性摘要，后续可升级多采样 diff

## 8. 风险与控制项

### 8.1 主要风险

- 让主 Agent 直接依赖过多 MCP 原子工具
- 子 Agent 拆得过碎
- 中间结果不落文件，导致上下文爆炸
- 过早追求 Android / iOS / 小程序统一执行
- 输出格式漂移，后续难自动化

### 8.2 控制策略

- 坚持 runtime adapter 抽象
- 首版只保留 3 个专用子 Agent
- 大结果默认落 `/workspace/` 或 `/artifacts/`
- 执行阶段只做 Web Demo
- 所有结果统一走 schema 校验

## 9. 验收口径

满足以下条件时，认为本计划已从 `planning` 准备好进入 `execution`：

- 架构设计文档已落地
- 目录骨架已整理完毕
- execution 阶段拆分明确
- 交付物路径明确
- 验收标准明确

当前状态判断：**满足进入 `do-plan` 的前置条件**。

## 10. 下一步动作

下一步建议模式：`execution`

推荐执行入口：

- 直接进入 `do-plan`
- 从 `Phase 1：Schema 与契约落地` 开始

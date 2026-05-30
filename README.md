# reverse-deepagent

[![CI](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml)

面向 Web / JavaScript 逆向流程的 DeepAgents 演示项目。项目聚焦本地、授权场景：归一化逆向任务、通过运行时适配器采集 Web 证据、验证候选签名函数，并生成 replay / rebuild 交付物。

> 当前发布线：`v0.1.x` 公开演示版稳定期。详见 [`CHANGELOG.md`](CHANGELOG.md) 与 [`ROADMAP.md`](ROADMAP.md)。
> BrowserProvider 架构与 MCP legacy 迁移：[`docs/runtime/browser-provider-architecture.md`](docs/runtime/browser-provider-architecture.md)、[`docs/runtime/cloakbrowser-provider.md`](docs/runtime/cloakbrowser-provider.md)、[`docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`](docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md)。
> MCP 运行时与自托管冒烟测试目前保留为 legacy 兼容路径：[`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)、[`docs/ci/self-hosted-mcp-smoke.md`](docs/ci/self-hosted-mcp-smoke.md)。
> 运行时适配器契约：[`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## 快速开始

```bash
git clone https://github.com/Facetomyself/reverse-deepagent.git
cd reverse-deepagent
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

运行确定性的 mock 流水线：

```bash
reverse-agent-demo --runtime mock
```

如果 shell 提示 `reverse-agent-demo: command not found`，说明当前终端还没有激活项目虚拟环境。可以先执行：

```bash
source "<repo-root>/.venv/bin/activate"
```

或者直接使用绝对路径：

```bash
"<repo-root>/.venv/bin/reverse-agent-demo" --runtime mock
```

运行本地 sign fixture 冒烟测试：

```bash
reverse-agent-fixture --check
reverse-agent-fixture-smoke --runtime mock --profile sha256
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

当前真实浏览器链路正在从 MCP 迁移到 BrowserProvider 架构：长期目标是 `native-web + BrowserProvider + native collectors`，MCP 保留为 legacy 兼容路径。

Native Web 运行时示例：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser playwright-chromium \
  --task-text "https://example.com 找 sign 入口"
```

如果还没有下载 Playwright 自带的 Chromium，也可以临时把 `--browser-executable-path` 指向系统 Chrome 做真实 smoke：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser playwright-chromium \
  --browser-executable-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --task-text "https://example.com 找 sign 入口"
```

如果本机已经有可用的 Chrome DevTools 端点，但还没有装 Playwright 或 CloakBrowser，`remote-cdp` 可以直接作为 BrowserProvider smoke 路径使用；它和 `chrome-cdp` 轻量探测后端不是一回事：前者接入 `native-web` 的采集栈，后者只是做端点探测。

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser remote-cdp \
  --cdp-browser-url "http://127.0.0.1:9555" \
  --task-text "http://127.0.0.1:8000/ 找 buildSign 入口"
```

对应的 doctor smoke 也支持显式指定端点：

```bash
reverse-agent-doctor \
  --browser remote-cdp \
  --browser-url "http://127.0.0.1:9555" \
  --launch-browser-smoke \
  --browser-smoke-url "about:blank"
```

CloakBrowser 作为可选 BrowserProvider 使用，安装方式如下：

```bash
uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cloak]"
```

运行示例：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-profile-dir "./profiles/example" \
  --task-text "https://example.com 查看登录态和关键请求"
```

如果已经有 CloakBrowser / cloakserve 暴露的 CDP endpoint，也可以显式走 connect baseline，不再由 agent 启动本地浏览器进程：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-url "http://127.0.0.1:9222" \
  --task-text "https://example.com 复用已有 CloakBrowser 会话检查关键请求"
```

本机已经验证过 `reverse-agent-doctor --browser cloakbrowser --launch-browser-smoke` 和 `reverse-agent-demo --runtime native-web --browser cloakbrowser` 的真实 smoke；如果要复现到别的机器，优先保证 `.[cloak]` 安装和 CloakBrowser 二进制可用。

BrowserProvider doctor 示例，默认不启动真实浏览器，也不依赖 MCP：

```bash
reverse-agent-doctor --browser cloakbrowser
```

需要真实启动 smoke 时显式打开：

```bash
reverse-agent-doctor \
  --browser cloakbrowser \
  --launch-browser-smoke \
  --browser-smoke-url "about:blank"
```

legacy MCP 浏览器集成仍可用于真实 smoke，需要本机 JSReverser MCP 可执行文件和 Chrome 调试环境。环境假设与故障排查见 [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)。公开 CI 不默认运行 legacy MCP 链路，而是隔离在手动 `MCP Integration` 工作流中。本地建议优先使用受管 Chrome 启动器：

```bash
reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```

## DeepAgents `/memories/` 长期记忆

`build_reverse_agent(...)` 现在默认在 DeepAgents `CompositeBackend` 中启用 `/memories/` 路由：

- `/workspace/`：DeepAgents 默认 `StateBackend`，适合当前任务临时草稿。
- `/artifacts/`：`FilesystemBackend`，映射到本地 artifact root，适合人工检查的报告和交付物。
- `/memories/`：`StoreBackend`，适合跨 agent / 跨会话复用的长期逆向经验。

默认开发环境使用进程内 `InMemoryStore`；需要跨 agent 实例共享时，可以显式传入同一个 `memory_store` 和 `memory_namespace`：

```python
from langgraph.store.memory import InMemoryStore
from reverse_deepagent.agent import build_reverse_agent

memory_store = InMemoryStore()
agent = build_reverse_agent(
    model=model,
    artifact_root="artifacts/demo",
    memory_store=memory_store,
    memory_namespace=("reverse-deepagent", "project-a", "memories"),
)
```

`/memories/` 只应该保存可复用经验，例如：

- `/memories/sites/example.com.md`：站点级入口、路由、常见接口命名。
- `/memories/protections/debugger-loop.md`：已验证的 protection 处理经验。
- `/memories/patterns/x-sign.md`：参数命名、签名函数命名、上下文依赖模式。

不要把未验证的一次性抓包、候选源码、临时 todo 写入 `/memories/`；这些仍应留在 `/workspace/` 或 `/artifacts/`。

纯 Python 冒烟测试：

```bash
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_memory_smoke.py"
```

## 轻量 Web 运行时后端

除了 `mock`、`native-web` 和 `legacy-mcp`，默认 registry 还注册了 3 个轻量 Web 后端：

- `playwright-cli`（别名：`playwright`, `pw-cli`）：运行 `playwright --version` 这类轻副作用探测，并对目标 URL 做静态 HTML / 脚本源码拉取。
- `chrome-cdp`（别名：`cdp`, `devtools`）：只探测已经存在的 Chrome DevTools 端点，例如 `http://127.0.0.1:9222/json/version` 和 `/json/list`，不会主动启动 Chrome。
- `browser-cli`（别名：`cli-browser`, `browser-command`）：给本地浏览器 CLI 适配命令预留的轻量后端；默认不配置命令，因此会结构化返回不可用。

示例：

```bash
reverse-agent-demo \
  --runtime chrome-cdp \
  --cdp-browser-url "http://127.0.0.1:9222" \
  --task-text "https://example.com/search 找 sign"

reverse-agent-demo \
  --runtime playwright-cli \
  --playwright-command playwright \
  --task-text "https://example.com/search 找 sign"

reverse-agent-demo \
  --runtime browser-cli \
  --browser-cli-command "my-browser-shim" \
  --task-text "https://example.com/search 找 sign"
```

这 3 个后端复用 `WebReverseRuntime` / `JSReverserRuntime` 的 Web recon schema，但能力刻意保持保守：不捕获实时网络时间线，不执行页面内 JS 运行时验证，也不注入反调试预加载脚本。工具不可用时会输出 `status=failed`、`next_action=ensure_browser_session` 和会话导出 artifact，而不是假装完成。

## 环境重建

项目已经补了 `pyproject.toml`，可以用 `pip`、`uv` 或现成的 `.venv` 进行重建。

如果你想在本地重新安装依赖，可以直接执行：

```bash
cd "<repo-root>"
uv pip install --python "<repo-root>/.venv/bin/python" -e .
```

安装完成后，会生成正式命令：

```bash
reverse-agent-demo --runtime mock
```

同时还会生成平台中立 runtime pipeline 命令和本地 fixture 相关命令：

```bash
reverse-agent-platform --runtime mini-program-devtools
reverse-agent-fixture --check
reverse-agent-fixture-smoke --runtime mock
```

如果你只想沿用当前现成环境，也可以继续直接使用：

```bash
"<repo-root>/.venv/bin/python" ...
```

## 目录说明

- `docs/design/`：架构与设计文档
- `docs/plans/`：规划文档
- `docs/reference/deepagents/`：本地 deepagents 学习资料
- `src/reverse_deepagent/`：实现代码骨架与 runtime adapter
- `src/reverse_deepagent/coordinator.py`：包内协调入口，统一调度 task card、route、recon、artifact 输出
- `scripts/`：运行与开发脚本
- `artifacts/`：mock demo 产出物、报告、截图与导出文件
- `artifacts-mcp-smoke/`：legacy MCP 后端 smoke 产物
- `tests/`：测试目录

## 当前关键文档

- 设计文档：`<repo-root>/docs/design/reverse-deepagent-architecture.md`
- 规划文档：`<repo-root>/docs/plans/2026-05-26-deepagents-js-reverse-agent-plan.md`

## 配置真实 OpenAI API 验证

仓库默认测试仍走 mock 运行时，避免公开 CI 或本地单元测试误消耗 API 额度。要用真实 OpenAI API 验证 DeepAgents 编排，可以安装 `llm` 可选依赖并设置环境变量。

安装可选依赖：

```bash
cd "<repo-root>"
uv pip install --python "<repo-root>/.venv/bin/python" -e ".[llm]"
```

设置 API key。不要把 key 写进 `.env`、README、代码或 Git 历史里；推荐只放当前 shell、系统 keychain 或 CI secret：

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-5.5"
```

运行真实 OpenAI-backed DeepAgents 冒烟测试：

```bash
reverse-agent-openai-smoke \
  --task-text "http://localhost 找 sign 入口，并给出下一步建议。先调用 route_reverse_task 工具完成路由。" \
  --artifact-root "<repo-root>/artifacts/openai-smoke"
```

也可以不安装 console script，直接用模块入口：

```bash
"<repo-root>/.venv/bin/python" -m reverse_deepagent.openai_smoke \
  --model "${OPENAI_MODEL:-gpt-5.5}" \
  --artifact-root "<repo-root>/artifacts/openai-smoke"
```

这个 smoke 只验证真实模型能驱动 DeepAgents 主 Agent、调用 `route_reverse_task` 工具并返回结构化摘要；它不默认启动 Chrome，也不默认调用 MCP。真实 Web runtime 仍按后文 `reverse-agent-demo --runtime legacy-mcp --ensure-chrome` 或 `reverse-agent-fixture-smoke --runtime legacy-mcp --ensure-chrome` 配置。

如果你的账号暂时没有 `gpt-5.5` 权限，可以把 `OPENAI_MODEL` 改成账号可用的模型。

## 运行最小演示（mock 运行时）

mock 运行时不依赖真实浏览器，适合验证 schema、route、adapter、artifact 链路。

`scripts/run_demo.py` 现在只是薄 CLI；真正的协调逻辑在：

- `<repo-root>/src/reverse_deepagent/coordinator.py`
- 包内入口：`reverse_deepagent.run_reverse_pipeline`

也可以直接使用正式命令：

```bash
reverse-agent-demo --runtime mock
```

默认会在 `artifacts/` 下生成：

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/recon-result.json`
- `workspace/final-result.json`
- `workspace/evidence-candidates.json`（通用候选证据索引）
- `workspace/evidence-validated.json`（通用已验证证据索引）
- `workspace/evidence-promotion.json`（通用证据晋升摘要）
- `workspace/review-gate.json`（review_hints 自动 gate 结果）
- `workspace/function-candidates.json`（有候选时）
- `workspace/function-validations.json`（有验证结果时）
- `workspace/function-validation-summary.json`（有验证结果时）
- `workspace/runtime-context.json`（检测到并采集运行时上下文时）
- `workspace/runtime-context-diff.json`（运行时上下文稳定性摘要）
- `workspace/backend-artifact-manifest.json`（backend 输出 manifest）
- `workspace/rebuild-plan.json`
- `rebuild/sign_rebuild.py`（可生成纯算策略时）
- `rebuild/replay_demo.py`（可生成纯算策略时）
- `rebuild/scrapy_middleware.py`（兼容型单文件 middleware）
- `rebuild/scrapy_project/`（可运行 Scrapy replay 项目，含 settings / middleware / spider / runner）
- `rebuild/scrapy_export_manifest.json`（Scrapy 交付 manifest）
- `reports/demo-final-result.json`
- `reports/demo-final-report.md`
- `exports/artifact-index.json`

## 通用证据晋升

Web pipeline 与平台中立 pipeline 现在都会生成一组平台无关的证据晋升 artifact：

- `workspace/evidence-candidates.json`：所有规范化 `EvidenceItem` 的候选索引。
- `workspace/evidence-validated.json`：通过通用验证门槛的证据索引。
- `workspace/evidence-promotion.json`：candidate / validated / promoted / rejected 全量记录与摘要。

证据晋升不替代 `final-result.json`，也不改变现有 rebuild 所依赖的 `FinalResult.evidence`；它是给 review gate、后续自动门禁、自动交付阻断和人工代码审查使用的机器可读索引。

通用规则保持保守：

- 低置信、工具不可用、`available=false`、unsupported 等信号会阻断晋升。
- 高置信 source/callstack/runtime/context/function validation 证据更容易进入 `promoted`。
- `function_validation_summary.replay_ready=true` 和运行时验证成功会提高晋升分数。
- 非 Web runtime 也会生成同样结构的 promotion 文件，避免把证据规则写死在 Web recon 里。

这些文件会进入 `workspace/backend-artifact-manifest.json`，category 为 `evidence`。

## `review_hints` 自动门禁

Web rebuild 交付流程现在会在生成 `workspace/rebuild-plan.json` 后自动评估 `review_hints`，并输出：

- `workspace/review-gate.json`

门禁输入包括：

- `rebuild_plan.ready`
- `rebuild_plan.review_hints`
- `workspace/evidence-promotion.json` 的 validated / promoted / rejected 摘要

门禁结果字段包括：

- `status`: `pass` / `warn` / `block`
- `blocked`: 是否阻断自动交付
- `blocking_hint_codes`: 阻断交付的 `risk` hint code
- `warning_hint_codes`: 需要人工确认的 warning 提示码
- `evidence_counts`: candidate / validated / promoted / rejected 证据数量
- `next_action`: `delivery_allowed`、`manual_review_before_delivery` 或 `manual_review_or_expand_evidence`

自动 gate 的基本规则：

- 任意 `severity=risk` 的 `review_hints` 会阻断自动交付。
- `rebuild_plan.ready=false` 会阻断自动交付。
- 没有 validated evidence 会阻断自动交付。
- ready=true 但没有 promoted evidence 会阻断自动交付。
- warning hint 不阻断，但输出 `status=warn`，要求人工确认后再交付。
- 存在 rejected evidence 且没有阻断项时输出 `status=warn`，避免把有争议的证据静默放行。

`review-gate.json` 会进入 `workspace/backend-artifact-manifest.json`，category 为 `triage`。平台中立 pipeline 不生成 rebuild bundle，因此不生成 review gate；它继续只输出证据晋升结果。

## 运行平台中立运行时流水线

`run_reverse_pipeline(...)` 仍然是 Web 专用入口，会要求后端实现 `WebReverseRuntime` 并执行 Web recon；非 Web runtime 统一走 `run_platform_pipeline(...)` / `reverse-agent-platform`。这个入口只依赖平台中立的 `ReverseRuntime` 契约：任务归一化、路由、能力采集、运行时 artifact 导出，以及 manifest / index / report 落盘，不会调用 `ensure_browser_session()` 或 `run_web_recon()`。

最小冒烟测试：

```bash
reverse-agent-platform \
  --runtime mini-program-devtools \
  --task-text "mini-program://demo 找 sign"
```

Android / iOS 可以传本地工具链参数：

```bash
reverse-agent-platform \
  --runtime android-adb \
  --android-adb-command adb \
  --android-device-serial "<device-serial>" \
  --android-package-name "com.example.app"

reverse-agent-platform \
  --runtime ios-simulator \
  --ios-xcrun-command xcrun \
  --ios-device-id "<simulator-udid>" \
  --ios-bundle-id "com.example.app"
```

默认会在 artifact root 下生成：

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/runtime-capabilities.json`
- `workspace/runtime-export-bundle.json`
- `workspace/platform-tool-probe.json`（backend 暴露 tool probe 时）
- `workspace/final-result.json`
- `workspace/evidence-candidates.json`
- `workspace/evidence-validated.json`
- `workspace/evidence-promotion.json`
- `workspace/backend-artifact-manifest.json`
- `reports/platform-pipeline-result.json`
- `reports/platform-pipeline-report.md`
- `exports/artifact-index.json`

工具链不可用时不会伪装成功：pipeline 会结构化返回 `status=partial` 和 `next_action=install_or_configure_platform_tooling`，同时仍然保留 probe 证据，方便后续平台专用子流程接手。

## 运行最小 DeepAgents 调用冒烟测试

如果你想验证“主 Agent + route tool（并注册专用子 Agent）”这条深度编排链路，但又不想依赖外部模型或真实浏览器，可以直接跑纯 Python 冒烟测试：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-smoke"
```

这条冒烟测试会：

- 构建 `deepagents` 主 Agent
- 通过 `route_reverse_task` 工具完成一次真实 invoke
- 产生 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage` 的完整消息链
- 打印 route 结果和最终消息摘要

适合用来验证：

- `build_reverse_agent()` 是否和当前 deepagents 版本对齐
- 工具函数是否具备可包装成 LangChain tool 的元数据
- 主 Agent 到 route tool 的闭环是否可用

### 子 Agent 委派冒烟测试

如果你还想验证主 Agent 通过 `task` 工具委派给 general-purpose 子 Agent 的链路，可以再跑这个：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_subagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-subagent-smoke"
```

这条冒烟测试会验证：

- 主 Agent 生成 `task` tool call
- deepagents 启动 general-purpose 子 Agent
- 子 Agent 的单条结果被回收到主线程
- 消息链完整呈现为 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage`

### 重建交付冒烟测试

如果你想验证 deepagents 主 Agent 的 rebuild delivery 工具链路，可以跑：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_delivery_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-delivery-smoke"
```

这条冒烟测试会验证：

- 先用 mock 运行时准备一份已验证 `FinalResult`
- 主 Agent 调用 `build_rebuild_delivery`
- 生成结构化 `RebuildResult`
- 产出 `workspace/rebuild-plan.json`
- 产出 `rebuild/sign_rebuild.py`
- 产出 `rebuild/replay_demo.py`
- 产出 `rebuild/scrapy_middleware.py`
- 产出 `rebuild/scrapy_project/` 与 `rebuild/scrapy_export_manifest.json`

对应 deepagents 能力已接入：

- tool：`build_rebuild_delivery`
- subagent：`rebuild_delivery`
- schema：`RebuildResult`

## 本地 sign fixture 样例

项目内置了一个可重复的 `localhost` Web 逆向样例，用来验证 sign 入口、请求样本和源码命中链路。

相关入口：

- fixture 服务：`reverse-agent-fixture`
- fixture 冒烟测试：`reverse-agent-fixture-smoke`
- 服务实现：`<repo-root>/src/reverse_deepagent/fixtures/web_sign.py`

快速自检：

```bash
reverse-agent-fixture --check
```

启动阻塞式本地服务：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765
```

指定 fixture profile：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765 --profile sha256
```

当前支持：

- `default`：`charCodeAt` 求和取模，再输出 `sig_<hex>_<timestamp>`
- `md5`：fixture 内置纯 JS `md5(keyword:timestamp)`，用于验证 `md5_keyword_timestamp` rebuild
- `sha1`：浏览器 `crypto.subtle.digest('SHA-1', ...)`，用于验证 `sha1_keyword_timestamp` rebuild
- `sha256`：浏览器 `crypto.subtle.digest('SHA-256', ...)`
- `base64`：`btoa(keyword:timestamp)`
- `context-localstorage`：依赖 `localStorage.device_id`，用于验证 localStorage context-aware delivery
- `context-cookie`：依赖 `document.cookie` 中的 `device_id`，用于验证 cookie context-aware delivery
- `context-navigator`：依赖 `navigator.userAgent`，用于验证浏览器指纹上下文 context-aware delivery
- `webpack-minified`：模拟 webpack 模块包装器与压缩辅助函数，验证打包形态下的 SHA-256 sign 识别
- `token-chain`：先访问 `/api/bootstrap` 获取 token，再用 `sessionStorage.fixture_token` 参与 SHA-256 sign
- `hybrid-context`：同时依赖 `localStorage.fixture_nonce` 与 `cookie.csrf_token`，用于验证多上下文绑定 context-aware delivery

页面与脚本：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/app.js`
- `http://127.0.0.1:8765/api/bootstrap`（`token-chain` profile 使用）
- `http://127.0.0.1:8765/api/search`

`app.js` 中包含稳定的入口特征：

- `function buildSign(keyword, timestamp)`
- `x-sign`
- `window.reverseFixture.search(...)`

使用 mock 运行时跑 fixture 冒烟测试：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime mock \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mock"
```

使用 legacy MCP + 受管 Chrome 跑 fixture 冒烟测试：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime legacy-mcp \
  --ensure-chrome \
  --jsreverser-mcp-command "/opt/homebrew/bin/jsreverser-mcp" \
  --chrome-debug-port 9445 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-fixture-smoke" \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mcp"
```

多策略真实冒烟测试示例：

```bash
reverse-agent-fixture-smoke \
  --profile sha256 \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9456 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-sha256" \
  --artifact-root "<repo-root>/artifacts/fixture-sha256-mcp"
```

如果要验证运行时上下文采集与 context-aware delivery：

```bash
reverse-agent-fixture-smoke \
  --profile context-localstorage \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9457 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-context" \
  --artifact-root "<repo-root>/artifacts/fixture-context-mcp"
```

第 13 阶段还可以直接验证 cookie / navigator 两类上下文：

```bash
reverse-agent-fixture-smoke \
  --profile context-cookie \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9460 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-phase13-cookie-9460" \
  --artifact-root "<repo-root>/artifacts/phase13-cookie-mcp"

reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-phase13-navigator-9461" \
  --artifact-root "<repo-root>/artifacts/phase13-navigator-mcp"
```

预期 `context-localstorage` 会生成：

```json
{
  "ready": true,
  "pure_extraction": {
    "pure_extractable": false,
    "context_aware_extractable": true,
    "runtime_context_required": ["localStorage"],
    "captured_runtime_context": ["localStorage"]
  }
}
```

并落盘：

- `workspace/runtime-context.json`
- `workspace/runtime-context-diff.json`
- `rebuild/sign_rebuild.py`
- `rebuild/replay_demo.py`

`context-cookie` 的预期是 `runtime_context_required = ["cookie"]`，生成的 `sign_rebuild.py` 会固化 `COOKIE_DEVICE_ID`。

`context-navigator` 的预期是 `runtime_context_required = ["navigator"]`，生成的 `sign_rebuild.py` 会固化 `NAVIGATOR_USER_AGENT` 并完成 `sha256_keyword_timestamp` 自检。

当前已验证 legacy MCP 冒烟测试结果：

- `final_result.status = success`
- `final_result.next_action = extract_pure_logic_and_build_replay`
- 能观察到 `/api/search` 网络请求样本
- 能命中 `/app.js` 中的 `buildSign` / `x-sign` 源码位置
- 能自动晋升请求发起链路证据：
  - `source = get_request_initiator`
  - artifact：`virtual://workspace/request-initiators.json`
- 能自动晋升源码上下文证据：
  - `source = get_script_source`
  - artifact：`virtual://workspace/source-contexts.json`
- 能自动生成候选函数卡片：
  - `source = function_candidate_card`
  - artifact：`virtual://workspace/function-candidates.json`
  - 当前 fixture 可稳定生成 `buildSign` 与 `search` 两张函数卡片
- 能自动完成候选函数运行时验证与 replay 校验：
  - `source = function_validation_result`
  - `source = function_validation_summary`
  - artifact：`virtual://workspace/function-validations.json`
  - artifact：`virtual://workspace/function-validation-summary.json`
  - 当前 fixture 可稳定验证 `buildSign` 与 `search` 两张函数卡片，并完成 replay
- 能自动生成纯算交付包：
  - `workspace/rebuild-plan.json`：描述候选函数、算法策略、纯算提取状态、验证状态、replay URL 和输出文件
  - `rebuild/sign_rebuild.py`：浏览器外纯 Python sign 计算脚本
  - `rebuild/replay_demo.py`：浏览器外 HTTP replay 演示
  - `rebuild/scrapy_middleware.py`：兼容型 Scrapy 下载中间件单文件
  - `rebuild/scrapy_project/`：可运行 Scrapy replay 项目，包含 `scrapy.cfg`、settings、middleware、spider、runner 和 `sign_adapter.py`
  - `rebuild/scrapy_export_manifest.json`：Scrapy 项目入口、命令和文件索引
- workspace 虚拟 artifact 会同步写成真实 JSON 文件：
  - `workspace/network-requests.json`
  - `workspace/source-hits.json`
  - `workspace/request-initiators.json`
  - `workspace/source-contexts.json`
  - `workspace/runtime-context.json`
  - `workspace/runtime-context-diff.json`
  - `workspace/function-candidates.json`
  - `workspace/function-validations.json`
  - `workspace/function-validation-summary.json`
  - `workspace/backend-artifact-manifest.json`
  - `workspace/rebuild-plan.json`
- rebuild 交付文件会写入：
  - `rebuild/sign_rebuild.py`
  - `rebuild/replay_demo.py`
  - `rebuild/scrapy_middleware.py`
  - `rebuild/scrapy_project/`
  - `rebuild/scrapy_export_manifest.json`
- `chrome_launch.ok = true`
- `chrome_stop.ok = true`
- 结束后调试端口无残留监听

### 纯算 replay 交付包

legacy MCP fixture 冒烟测试完成后，可以先对生成的 sign 脚本做 sample 自检：

```bash
"<repo-root>/.venv/bin/python" \
  "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/sign_rebuild.py"
```

如果要验证 `replay_demo.py` 的浏览器外复放能力，需要让 fixture 服务保持运行，例如另开一个终端：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765
```

然后执行：

```bash
"<repo-root>/.venv/bin/python" \
  "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/replay_demo.py" \
  --base-url "http://127.0.0.1:8765" \
  --keyword "sign"
```

这一步不需要 Chrome，也不需要 MCP，证明已经进入“纯算 + HTTP replay”的交付形态。

### Scrapy replay 项目

第 10 项开始，ready rebuild 会额外生成完整 Scrapy 项目，而不只是 middleware 草案：

- `rebuild/scrapy_project/scrapy.cfg`
- `rebuild/scrapy_project/reverse_sign_project/settings.py`
- `rebuild/scrapy_project/reverse_sign_project/middlewares.py`
- `rebuild/scrapy_project/reverse_sign_project/spiders/replay_spider.py`
- `rebuild/scrapy_project/reverse_sign_project/sign_adapter.py`
- `rebuild/scrapy_project/runner.py`
- `rebuild/scrapy_export_manifest.json`

Scrapy 是可选依赖，按需安装：

```bash
pip install "reverse-deepagent[scrapy]"
# 或者在当前环境里手动安装
pip install scrapy
```

运行示例：

```bash
cd "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/scrapy_project"
scrapy crawl reverse_sign_replay -a base_url="http://127.0.0.1:8765"
# 或者
python runner.py --base-url "http://127.0.0.1:8765" --output result.json
```

生成项目通过 `reverse_sign_project.sign_adapter` 读取同级上层的 `../sign_rebuild.py`，middleware 会把请求改写为带 `keyword` / `timestamp` / `sign` JSON body 的 POST，并设置 `x-sign` 与 `x-fixture` headers。没有安装 Scrapy 时，middleware 和 adapter 仍可被普通 Python import / compile，用于离线验证签名注入逻辑。

### 纯算提取策略字段

`workspace/rebuild-plan.json` 现在会显式区分“能纯算”和“需要运行时上下文”：

```json
{
  "algorithm_strategy": {
    "id": "md5_keyword_timestamp",
    "supported": true,
    "confidence": "medium",
    "confidence_score": {
      "score": 0.65,
      "label": "medium",
      "positive_markers": ["md5", "keyword_colon_timestamp"],
      "caveats": []
    },
    "dependencies": ["python-stdlib:hashlib"],
    "confidence_reason": "Detected md5 hash marker in source context."
  },
  "pure_extraction": {
    "pure_extractable": true,
    "manual_port_required": false,
    "runtime_context_required": [],
    "dependencies": ["python-stdlib:hashlib"],
    "confidence_reason": "Detected md5 hash marker in source context."
  },
  "review_hints": [
    {
      "severity": "info",
      "category": "strategy",
      "code": "pure_strategy_detected",
      "message": "Supported pure-Python rebuild strategy detected; review generated sign_rebuild.py against the captured sample before reuse.",
      "evidence": ["strategy=md5_keyword_timestamp", "runtime_context_required=[]"]
    }
  ]
}
```

当前策略检测通过 `reverse_deepagent.strategies` 包里的 `AlgorithmStrategyRule` registry 管理；`rebuild.py` 只保留兼容代理。策略输出保留旧 `confidence` 字符串，同时新增 `confidence_score`，记录数值分数、positive markers 和 caveats。registry 元数据可由 `list_algorithm_strategy_registry()` 读取。当前默认顺序：

1. `protected_flow_triage`：发射 `triage_wasm_module`、`triage_vm_obfuscation`、`triage_anti_debug_runtime`、`triage_dynamic_secret`、`triage_wasm_vm_obfuscation`
2. `deterministic_fixture`：发射 `fixture_seed_mod100000`
3. `crypto_hash`：发射 `md5_keyword_timestamp`、`sha1_keyword_timestamp`、`sha256_keyword_timestamp`、`sha512_keyword_timestamp`、`hmac_md5_keyword_timestamp`、`hmac_sha1_keyword_timestamp`、`hmac_sha256_keyword_timestamp`、`hmac_sha512_keyword_timestamp`（HMAC 需要能提取 literal secret）
4. `sig_template`：发射 `sig_keyword_timestamp_template`
5. `encoding`：发射 `base64_keyword_timestamp`、`urlencode_keyword_timestamp`

`protected_flow_triage` 是阻断型前置检测器，必须保守：普通 `cookie` / `localStorage` / `navigator` / `nonce` / `csrf` 等上下文输入不会仅凭变量名进入仅分诊状态，除非同时出现 WASM / VM / anti-debug / 原生桥 / 强运行时挑战等强保护证据。

策略库还提供 `STRATEGY_SAMPLE_CORPUS` / `list_strategy_sample_corpus()`，覆盖 fixture reducer、MD5、SHA-1、SHA-256、SHA-512、HMAC-MD5、HMAC-SHA1、HMAC-SHA256、HMAC-SHA512、Base64 和 URL encoding 的确定性样本。测试会用这些样本同时验证检测器输出和生成的 `sign_rebuild.py` 自检。

WASM、JS VM、重混淆、反调试和动态 secret 这类流程不能被硬说成纯 Python 可移植。对应边界见 [`docs/strategy/wasm-vm-obfuscation-triage.md`](docs/strategy/wasm-vm-obfuscation-triage.md)：这类场景会优先命中 `protected_flow_triage` 检测器，输出仅分诊 / 运行时辅助 / 部分完成计划，并通过 `review_hints` 阻断误导性的纯算交付。

当前会阻断纯算提取的运行时上下文依赖：

- `document.cookie`
- `localStorage`
- `sessionStorage`
- `navigator`
- `timezone`
- `canvas`

如果出现这些依赖，`rebuild-plan.json` 会标记：

```json
{
  "ready": false,
  "pure_extraction": {
    "pure_extractable": false,
    "manual_port_required": true,
    "runtime_context_required": ["localStorage"]
  },
  "review_hints": [
    {
      "severity": "risk",
      "category": "manual_port",
      "code": "manual_port_required",
      "message": "No complete automatic rebuild is available; expand source/runtime evidence or keep a JS runtime backend for this flow.",
      "evidence": ["strategy=sha256_keyword_timestamp", "missing_runtime_context=localStorage"]
    }
  ]
}
```

如果运行时上下文没有采集到，这时候不会强行生成假的纯算交付脚本，而是生成 `rebuild/README.md`，提示需要继续补运行时上下文或人工移植。

如果上下文已经采集到，例如 `context-localstorage` profile 的：

```json
{
  "localStorage": {
    "device_id": "fixture-device"
  }
}
```

则 `rebuild-plan.json` 会升级为：

```json
{
  "ready": true,
  "pure_extraction": {
    "pure_extractable": false,
    "context_aware_extractable": true,
    "runtime_context_required": ["localStorage"],
    "captured_runtime_context": ["localStorage"],
    "runtime_context_binding": {
      "source": "localStorage.device_id",
      "key": "device_id",
      "constant": "LOCAL_STORAGE_DEVICE_ID",
      "value": "fixture-device"
    },
    "runtime_context_binding_required": true,
    "runtime_context_binding_candidates": ["localStorage.device_id"]
  },
  "review_hints": [
    {
      "severity": "warning",
      "category": "runtime_context",
      "code": "context_aware_rebuild",
      "message": "Generated rebuild depends on captured browser/runtime context; verify these values are stable before running at scale.",
      "evidence": ["runtime_context_required=localStorage", "captured_runtime_context=localStorage"]
    }
  ]
}
```

生成的 `sign_rebuild.py` 会把采集到的上下文写成默认常量，用于浏览器外 replay。renderer 会从源码自动识别 `localStorage.getItem('<key>')`、`localStorage['<key>']`、`localStorage.<key>`、`sessionStorage.getItem('<key>')`、`sessionStorage['<key>']`、`sessionStorage.<key>`、`document.cookie` 中的 cookie name、`navigator.<prop>` 和 `timezoneOffset`，再从 `runtime-context.json` 中提取对应值写入 `pure_extraction.runtime_context_binding`。

如果源码已经明确依赖某个具体上下文 key，例如 `localStorage.getItem('nonce')`，但采集结果里只有同 family 的其他值，例如 `localStorage.device_id`，则 `context_aware_extractable` 会保持 `false`，`review_hints` 会输出 `missing_runtime_context_binding=localStorage.nonce`，交付包只生成 `rebuild/README.md`，不会用空 salt 或错误兜底生成假成功脚本。

当前自动交付支持单个或多个运行时上下文 binding 写入生成脚本；如果源码同时依赖 `localStorage.nonce` 和 `cookie.csrf` 这类多个显式上下文值，只要都已采集并解析出来，就会把它们按源码顺序拼进生成脚本，继续保持 ready。缺失任一上下文值时才会标记 `multiple_runtime_context_bindings_unsupported=true` 并保持 not-ready，避免把半截多输入签名硬塞进单 salt renderer。HMAC 策略会区分 HMAC secret 与 message 里的运行时上下文：`CryptoJS.HmacSHA256(raw, 'secret')` 会把 `secret` 作为 HMAC key，把 `nonce` 作为 message binding。

`review_hints` 是给后续人工 review、CI gate 或子智能体复核使用的 机器可读提示，不替代 `ready` / `pure_extraction`。当前由 `reverse_deepagent.schemas.ReviewHint` 集中约束，固定字段为 `severity`、`category`、`code`、`message`、`evidence`，会覆盖 pure rebuild、context-aware rebuild、人工移植 / 部分 rebuild，以及易变运行时上下文等风险。

`workspace/runtime-context-diff.json` 会对运行时上下文做稳定性摘要。默认运行时会采集多次样本，字段包括 `status`（`multi_sample` 或 `single_sample` 兜底）、`sample_count`、`stable`、`stable_keys`、`volatile_keys`、`missing_requirements` 和 `changes`。其中 `sample_index` / `collected_at_ms` 只作为采样元数据，不参与稳定性判断；`volatile_keys` 应被视为 replay 时仍需要运行时绑定的输入。

## 运行时后端能力

运行时后端能力通过 `RuntimeBackendCapabilities` 描述，调用方可以用 `runtime.describe_capabilities()` 做能力发现，而不是在 coordinator 中硬猜 MCP、Chrome 或 mock 后端的行为。

示例：

```python
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends

print(list_runtime_backends())

runtime = build_runtime("mock")
capabilities = runtime.describe_capabilities()
print(capabilities.model_dump(mode="json"))
```

`build_runtime(...)` 现在通过 `RuntimeBackendRegistry` 创建后端。架构方向是新增 `native-web`，通过 BrowserProvider 切换 `playwright-chromium`、`cloakbrowser`、`chrome-cdp`、`remote-cdp` 等浏览器实现，并把 MCP 降级为 legacy 兼容后端。Registry 还会加载 `reverse_deepagent.runtime_backends` Python entry-point group 里的外部 backend registration，加载 metadata 时不会调用 backend factory；这为后续把 legacy MCP 物理拆成 optional package 留出迁移缝。当前内置注册：

- `mock`（别名：`in-process`）：公开 CI 和本地 deterministic demo 使用
- `native-web`（别名：`web`, `browser-native`）：BrowserProvider-backed native Web runtime，目标默认路径，当前支持 `playwright-chromium`、`cloakbrowser` 和 `remote-cdp` provider；真实二进制 smoke 需要显式触发
- `legacy-mcp`（别名：`mcp`, `jsreverser-mcp`）：legacy JSReverser MCP + Chrome DevTools 兼容运行时；`mcp` / `jsreverser-mcp` 仅作为旧命令 alias 保留，CLI 会输出 deprecation warning，新脚本应改用 `legacy-mcp`
- `playwright-cli`（别名：`playwright`, `pw-cli`）：轻量 Playwright CLI 探测与静态源码拉取，不主动启动浏览器
- `chrome-cdp`（别名：`cdp`, `devtools`）：连接既有 Chrome DevTools 端点，不主动启动 Chrome
- `browser-cli`（别名：`cli-browser`, `browser-command`）：通用浏览器 CLI 适配命令 backend，默认 command 未配置
- `android-adb`（别名：`adb`, `android-device`）：Android ADB 工具链探测与平台 artifact 导出
- `ios-simulator`（别名：`simctl`, `ios-sim`）：iOS Simulator / `xcrun simctl` 工具链探测与平台 artifact 导出
- `mini-program-devtools`（别名：`mp-devtools`, `wechat-devtools`）：小程序 vendor devtools CLI 配置探测与平台 artifact 导出

每次 pipeline 会额外写出 `workspace/backend-artifact-manifest.json`，用 `RuntimeArtifactManifest` / `RuntimeArtifactManifestEntry` 描述 artifact key、路径、类别、kind、producer backend、transport 和 target platforms。这个 manifest 是新增索引，不替换现有 `exports/artifact-index.json`。跨平台 artifact category 词表见 [`docs/runtime/platform-neutral-artifact-categories.md`](docs/runtime/platform-neutral-artifact-categories.md)。

非 Web 运行时会沿用同一套 capability / manifest 边界，但不能复用 Web 专属的浏览器会话语义。当前接口草案：

- Android: [`docs/runtime/android-adapter-interface.md`](docs/runtime/android-adapter-interface.md)
- iOS: [`docs/runtime/ios-adapter-interface.md`](docs/runtime/ios-adapter-interface.md)
- Mini-program: [`docs/runtime/mini-program-adapter-interface.md`](docs/runtime/mini-program-adapter-interface.md)

当前 Web 路径的浏览器会话、Chrome 调试端口、JSReverser MCP、Web 存储、URL replay 推导等假设统一收口在 [`docs/runtime/web-runtime-assumptions.md`](docs/runtime/web-runtime-assumptions.md)，后续平台适配器不应默认继承这些语义。BrowserProvider 新架构见 [`docs/runtime/browser-provider-architecture.md`](docs/runtime/browser-provider-architecture.md)。

JSReverser MCP 后端配置由 `JSReverserMcpConfig` 收束，字段包括 `command`、`browser_url`、`request_timeout`、`startup_timeout`、后端元数据和运行时采样参数。CLI 里的 `--jsreverser-mcp-command`、Chrome 调试端口等参数最终都会汇入这个配置，再创建 `legacy-mcp` 运行时。

兼容期内 `--runtime mcp` 和 `--runtime jsreverser-mcp` 仍可解析到 `legacy-mcp`，但会向 stderr 打印 deprecation warning；`reverse-agent-doctor --check-mcp` 也只作为 `--legacy-mcp` 的旧别名保留。后续新增文档、脚本和 workflow 不应继续使用旧 alias。

核心字段包括：

- `backend_id`：稳定后端标识，例如 `mock`、`native-web`、`legacy-mcp`
- `transport`：实现传输，例如 `in-process`、`mcp-stdio`
- `target_platforms`：当前目标平台，现阶段主要是 `web`
- `supports_web_recon` / `supports_runtime_context` / `supports_replay_validation`：能力开关
- `managed_chrome` / `mcp_backed`：运行时约束提示
- `evidence_kinds` / `artifact_kinds`：该后端常见输出类型

`native-web` / `remote-cdp` 现在会在 BrowserProvider 支持 runtime eval 时执行最小候选函数验证，并沿用既有 artifact 名称输出 `workspace/function-candidates.json`、`workspace/function-validations.json` 和 `workspace/function-validation-summary.json`。当传入显式 breakpoint 触发表达式时，它们还会输出 `workspace/debugger-paused.json`、`workspace/callframes.json`、`workspace/debugger-session.json` 和 `workspace/debugger-timeline.json`；显式传入 `callframe_evaluations` / `evaluate_on_callframe` 时补充 `workspace/callframe-evaluations.json` 和 `workspace/mutation-audit.json`；显式传入 `closure-function-discovery` / `closure-scope` protection，并提供 `closure_function_names` / `function_name`、断点位置和 trigger 时，会在 paused callframe 里用只读 `typeof <name>` 证明候选闭包绑定是否为函数，输出 `virtual://workspace/closure-functions.json` 和 `virtual://workspace/closure-function-candidates.json`；显式传入 `debugger_actions` / `pause_actions` 时还会输出 `workspace/debugger-actions.json`，用于最小 paused/callframe/evaluateOnCallFrame/step/session smoke。显式传入 `hook-function` / `function-hook` protection 和 `function_name` / `function_paths` 时，`native-web` 还可以对全局可达函数路径安装 wrapper，例如 `window.buildSign`，并返回 `virtual://workspace/function-hooks.json` 与 `virtual://workspace/function-hook-timeline.json`。显式传入 `hook-module` / `module-hook` protection、`module_id` 和 `export_name` 时，还可以对 `window.__webpack_require__(731).sign` 这类 webpack-like module export 安装 wrapper，并返回 `virtual://workspace/module-hooks.json` 与 `virtual://workspace/module-hook-timeline.json`。显式传入 `module-discovery` / `discover-modules` protection 或 `module_query` 时，`native-web` 会从项目自有 script inventory 中做 best-effort webpack-like module export discovery，并只读 introspect `window.__webpack_require__.c` / `.m` 这类 runtime module cache / registry；显式传入 `module_runtime_paths` / `moduleRuntimePaths` 时，还会对 custom object runtime 和带 `__reverseAgentExposes` 快照的 module federation container 做只读 baseline introspection。输出仍是 `virtual://workspace/module-registry.json` 与 `virtual://workspace/module-candidates.json`；webpack-like candidate 可继续喂给 `hook-module`，`hook_kind=function-path` 的 custom / federation candidate 应转给 `hook-function`。显式传入 `source-logpoint` / `logpoint` protection、`url_pattern` / `line_number` 和 `log_expression` 时，`native-web` 可以通过 CDP 条件断点安装 source-level logpoint，并返回 `virtual://workspace/source-logpoints.json` 与 `virtual://workspace/source-logpoint-timeline.json`；如果同时传入 `bundle_offset` + `bundle_source`，或 `source_map` + `original_source` + `original_line` / `original_column`，会先把 generated bundle offset 或 Source Map v3 mapping 重映射为 CDP generated line / column；Source Map baseline 现在支持 exact match、greatest-lower-bound bias fallback、`sourceRoot` 源路径归一化，以及 indexed source map `sections` 的最小 offset 合并，并把 `remap` 元数据写入 source-logpoint artifact。当前 baseline 覆盖目标函数路径观测、webpack-like module export 观测、webpack-like module export candidate 自动发现、webpack-like runtime module cache / registry 只读 introspection、custom object runtime / module federation 暴露模块的 function-path candidate baseline、显式候选名的 closure-scope function evidence baseline 和脚本 URL / 行号观测；它还不等于任意闭包内部函数自动 wrapper hook，也不是完整 source-map consumer、完整 webpack runtime analyzer 或会自动执行 federation `get/init` 的 deep analyzer；source-map name resolution、复杂 URL 语义、复杂 indexed sections 语义、任意 custom loader 遍历、异步 chunk graph 和更深 webpack runtime 解析仍是后续 capability-gated 工作。`pause_session_id` 现在还能把 retained paused session 续用到后续 `paused-session` 动作里；同进程 registry 支持 inspect / evaluate / step / resume 这类 live CDP 调试续作，并会在 `continuation_preflight` 里标出 `source=registry`、requested action、pre-action lifecycle、live continuation 可用性和 action 后 lifecycle。显式传入 `persist_paused_session` / `paused_session_store_dir` 时，会额外落盘 durable paused-session snapshot，后续进程可通过 `paused-session` inspect 读取 debugger session、timeline、callframes 和 breakpoints 做审计；durable snapshot 的 `continuation_preflight` 固定标记 `source=durable_snapshot` / `status=inspect_only`，resume / step / evaluate 会结构化变成 `status=action_blocked` 与 `live_paused_session_required`，仍不支持跨进程 resume / step / evaluate 原 CDP paused execution。callframe evaluation 默认走 `read_only` policy，会给 `Debugger.evaluateOnCallFrame` 加 `throwOnSideEffect` 并阻断明显高风险表达式；显式设置 `allow_callframe_side_effects` 才允许副作用表达式。当前 `workspace/mutation-audit.json` 会记录这些 callframe evaluation 的风险分类与审计摘要。显式传入 `page-mutation-audit` / `page-mutation` protection 时，`native-web` 还会围绕触发表达式采集页面 before / after 摘要，输出 `virtual://workspace/page-mutation-audit.json`，覆盖 DOM 尺寸、storage key、cookie name 与选定 global preview 的粗粒度 diff。显式传入 `mutation-observer-timeline` / `mutation-timeline` protection，或传入 `observer_wait_ms` / `mutation_record_limit` 这类 context key 时，`native-web` 会围绕显式 trigger 安装 `MutationObserver`，输出 `virtual://workspace/mutation-observer-timeline.json`，记录有限的 `childList` / `attributes` / `characterData` DOM mutation records；它仍不是 JS heap diff、object graph diff 或闭包内部状态审计。`debugger-timeline.json` 会把 breakpoint set、trigger、pause、callframe evaluation、debugger action 和 auto-resume/retained state 串成单次调试审计轨迹。常规 `native-web` recon 现在也会把 baseline collector 中的 navigation、network、request initiator、hook timeline 和 replay validation 片段归一化为 `virtual://workspace/flow-timeline.json`，并进入 `workspace/backend-artifact-manifest.json`；每个新增 timeline entry 会带保守的 `correlation` hints，来源包括 request id、URL path、method、initiator function、hook path、candidate id 和 validation function；artifact 顶层还会输出 `correlation_groups`，按共享 request id、URL path + method、function name、candidate id 或 hook path 归为候选证据桶，并固定标注 `stitching=false`；每个 group 还会带 `verification.status=weak|reviewable|ready_for_manual_stitch_review`、evidence booleans 和 `missing_for_ready`，供 review gate 或后续子智能体参考；`reviewable` / `ready_for_manual_stitch_review` 的 group 还会被提升为 `stitch_candidates`，输出人工复核路径、证据布尔值、缺失项和 `automatic_stitching=false`，但不会生成已拼接链路；显式传入 `flow-timeline` / `cross-request-timeline` protection，并提供 `previous_flow_timeline`、`flow_events`、`network_requests`、`hook_timeline`、`debugger_timeline`、`function_hook_timeline`、`module_hook_timeline`、`source_logpoint_timeline`、`mutation_observer_timeline` 或 `replay_validation` 这类已采集片段时，`native-web` 还会归一化并延续输出同一个 `flow-timeline.json` artifact，作为跨请求证据串联的 baseline；这些 hints / groups / readiness 不会自动订阅所有浏览器事件，也不等于完整自动 stitching。跨进程 live CDP paused execution continuation、任意闭包内部函数自动 wrapper hook、任意 custom loader / async chunk graph / 深层 module federation 执行式分析、超出当前 source-map baseline 的 name / URL / complex sections 语义、JS heap 级细粒度 mutation 审计、object graph diff 和自动全链路跨请求 timeline stitching 仍然是后续 capability-gated 工作。

当前 Android / iOS / 小程序后端已具备 registry / factory / 能力元数据 / 轻副作用工具探测 / artifact 导出基础层，并可通过平台中立 `reverse-agent-platform` pipeline 落盘 capabilities、probe、export bundle、manifest 与报告；但还不包含真实 hook、静态分析或 replay 验证。完整约定见 [`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## Chrome 调试会话约束

legacy MCP 运行时依赖 `http://127.0.0.1:9222` 这类 Chrome DevTools 端口。

约束：

- Agent 不应该假设 9222 Chrome 已经存在
- 真实 Web recon 前必须先完成 Chrome 调试会话检查
- 如果没有可用 Chrome：
  - 显式使用 `--ensure-chrome` 时，通过推荐脚本启动受管 Chrome
  - 未显式启用时，结构化返回 `status=failed`、`next_action=ensure_browser_session`
- 启动参数必须可调，不要把端口、profile、Chrome 路径硬写死在 Agent prompt 里

推荐启动脚本：

```bash
"<repo-root>/scripts/start_chrome_debug.sh"
```

可调环境变量：

- `CHROME_PATH`，默认 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- `DEBUG_PORT`，默认 `9222`
- `DEBUG_ADDRESS`，默认 `127.0.0.1`
- `USER_DATA_DIR`，默认 `~/.codex/browser-profiles/chrome-jsreverser`
- `STATE_DIR`，默认 `~/.codex/run/reverse-deepagent`
- `START_URL`，默认 `about:blank`
- `WAIT_SECONDS`，默认 `10`
- `EXTRA_CHROME_ARGS`，默认空

示例：

```bash
DEBUG_PORT=9333 \
USER_DATA_DIR="/tmp/reverse-agent-chrome" \
START_URL="http://localhost:3000" \
EXTRA_CHROME_ARGS="--disable-web-security" \
"<repo-root>/scripts/start_chrome_debug.sh"
```

停止受管 Chrome：

```bash
DEBUG_PORT=9333 \
USER_DATA_DIR="/tmp/reverse-agent-chrome" \
"<repo-root>/scripts/stop_chrome_debug.sh"
```

## 运行 legacy MCP 冒烟测试

完整前置条件和故障排查见 [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)。

推荐先运行浏览器 / legacy MCP doctor，确认本机 Chrome、调试端口、`jsreverser-mcp` 和 console script 入口是否就绪：

```bash
reverse-agent-doctor --ensure-chrome --legacy-mcp
```

如果当前 shell 没有激活虚拟环境，可以使用绝对路径：

```bash
"<repo-root>/.venv/bin/reverse-agent-doctor" --ensure-chrome --legacy-mcp
```

默认情况下，`reverse-agent-doctor --ensure-chrome` 会在检查后停止受管 Chrome；如果你需要保留调试会话，显式添加 `--keep-chrome`。

先探测真实 `jsreverser-mcp` stdio 协议和工具列表：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/probe_jsreverser_mcp.py"
```

已验证当前本机 `jsreverser-mcp`：

- 协议：stdio JSON-RPC newline framing
- 协商协议版本：`2025-03-26`
- tools/list 可返回 73 个工具

## 运行最小演示（legacy MCP 运行时）

legacy MCP 运行时会启动 `/opt/homebrew/bin/jsreverser-mcp --browserUrl http://127.0.0.1:9222`。

```bash
reverse-agent-demo \
  --runtime legacy-mcp \
  --ensure-chrome \
  --artifact-root "<repo-root>/artifacts-mcp-smoke"
```

常用可调参数：

```bash
--chrome-debug-port 9333 \
--chrome-user-data-dir "/tmp/reverse-agent-chrome" \
--chrome-start-url "http://localhost:3000" \
--chrome-extra-args "--disable-web-security"
```

如果 `127.0.0.1:9222` 没有可用 Chrome，会得到结构化失败结果：

- `status: failed`
- `next_action: ensure_browser_session`

这属于预期行为，不是脚本崩溃。

## 真实 Chrome 冒烟测试（可调端口）

已验证一条真实冒烟测试链路，可以在隔离端口上启动受管 Chrome，再交给 `jsreverser-mcp`：

```bash
reverse-agent-demo \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9445 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9445" \
  --chrome-start-url "about:blank" \
  --task-text "http://localhost 找 sign 入口，并给出下一步建议" \
  --artifact-root "<repo-root>/artifacts-managed-chrome-smoke"
```

实测结果：

- `chrome_launch.ok = true`
- `chrome_stop.ok = true`
- 端口 9445 在结束后不再保留监听
- `final_result.status = partial`
- `final_result.next_action = stabilize_page_and_expand_runtime_observation`
- `final_result.key_findings.facts` 会包含已连接浏览器、当前活动页面和导航动作

注意：

- `jsreverser-mcp` 的真实输出可能是 Markdown 与 fenced JSON 混合文本，适配层已经做了归一化
- 如果你改了 `--chrome-debug-port`，`reverse-agent-demo` 会把这个端口同步传给 MCP 后端，不会再傻乎乎地默认连 9222

## 测试

```bash
cd "<repo-root>"
"<repo-root>/.venv/bin/python" \
  -m unittest discover -s "<repo-root>/tests" -p "test_*.py"
```

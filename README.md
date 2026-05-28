# reverse-deepagent

[![CI](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml)

Reverse-engineering oriented DeepAgents demo for Web / JavaScript workflows. The project focuses on local, authorized analysis: route a reverse task, collect Web evidence through runtime adapters, validate candidate signing functions, and generate replay / rebuild artifacts.

> 当前发布线：`v0.1.x` public demo stabilization。详见 [`CHANGELOG.md`](CHANGELOG.md) 与 [`ROADMAP.md`](ROADMAP.md)。
> MCP runtime 与 self-hosted smoke：[`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)、[`docs/ci/self-hosted-mcp-smoke.md`](docs/ci/self-hosted-mcp-smoke.md)。
> Runtime adapter contract：[`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## Quickstart

```bash
git clone https://github.com/Facetomyself/reverse-deepagent.git
cd reverse-deepagent
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

Run the deterministic mock pipeline:

```bash
reverse-agent-demo --runtime mock
```

Run the local sign fixture smoke:

```bash
reverse-agent-fixture --check
reverse-agent-fixture-smoke --runtime mock --profile sha256
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

MCP-backed browser integration requires a local JSReverser MCP binary and Chrome debug environment. See [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md) for setup assumptions and troubleshooting. For public CI this is isolated in the manual `MCP Integration` workflow instead of the default CI workflow. Locally, prefer the managed Chrome launcher:

```bash
reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime mcp \
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

纯 Python smoke：

```bash
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_memory_smoke.py"
```

## 轻量 Web Runtime Backend

除了 `mock` 和 `mcp`，默认 registry 还注册了 3 个轻量 Web backend：

- `playwright-cli`（alias: `playwright`, `pw-cli`）：运行 `playwright --version` 这类 side-effect-light probe，并对目标 URL 做静态 HTML / script source fetch。
- `chrome-cdp`（alias: `cdp`, `devtools`）：只探测已经存在的 Chrome DevTools endpoint，例如 `http://127.0.0.1:9222/json/version` 和 `/json/list`，不会主动启动 Chrome。
- `browser-cli`（alias: `cli-browser`, `browser-command`）：给本地浏览器 CLI shim 预留的轻量命令 backend，默认不配置 command，因此会结构化返回不可用。

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

这 3 个 backend 复用 `WebReverseRuntime` / `JSReverserRuntime` 的 Web recon schema，但能力是刻意保守的：它们不捕获 live network timeline，不执行页面内 JS runtime validation，不注入 anti-debug preload。工具不可用时会输出 `status=failed`、`next_action=ensure_browser_session` 和 session export artifact，而不是假装完成。

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
- `artifacts-mcp-smoke/`：真实 MCP 后端 smoke 产物
- `tests/`：测试目录

## 当前关键文档

- 设计文档：`<repo-root>/docs/design/reverse-deepagent-architecture.md`
- 规划文档：`<repo-root>/docs/plans/2026-05-26-deepagents-js-reverse-agent-plan.md`

## 运行最小 Demo（mock runtime）

mock runtime 不依赖真实浏览器，适合验证 schema、route、adapter、artifacts 链路。

`scripts/run_demo.py` 现在只是薄 CLI；真正的协调逻辑在：

- `<repo-root>/src/reverse_deepagent/coordinator.py`
- 包内入口：`reverse_deepagent.run_reverse_pipeline`

正式命令也可以直接走：

```bash
reverse-agent-demo --runtime mock
```

默认会在 `artifacts/` 下生成：

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/recon-result.json`
- `workspace/final-result.json`
- `workspace/function-candidates.json`（有候选时）
- `workspace/function-validations.json`（有验证结果时）
- `workspace/function-validation-summary.json`（有验证结果时）
- `workspace/runtime-context.json`（检测到并采集运行时上下文时）
- `workspace/runtime-context-diff.json`（运行时上下文稳定性摘要）
- `workspace/backend-artifact-manifest.json`（backend 输出 manifest）
- `workspace/rebuild-plan.json`
- `rebuild/sign_rebuild.py`（可生成纯算策略时）
- `rebuild/replay_demo.py`（可生成纯算策略时）
- `rebuild/scrapy_middleware.py`（可生成纯算策略时）
- `reports/demo-final-result.json`
- `reports/demo-final-report.md`
- `exports/artifact-index.json`

## 运行平台中立 Runtime Pipeline

`run_reverse_pipeline(...)` 仍然是 Web 专用入口，会要求 backend 实现 `WebReverseRuntime` 并执行 Web recon；非 Web runtime 统一走 `run_platform_pipeline(...)` / `reverse-agent-platform`。这个入口只依赖平台中立的 `ReverseRuntime` contract：task normalize、route、capability capture、runtime artifact export、manifest/index/report 落盘，不会调用 `ensure_browser_session()` 或 `run_web_recon()`。

最小 smoke：

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
- `workspace/backend-artifact-manifest.json`
- `reports/platform-pipeline-result.json`
- `reports/platform-pipeline-report.md`
- `exports/artifact-index.json`

工具链不可用时不会伪装成功：pipeline 会结构化返回 `status=partial` 和 `next_action=install_or_configure_platform_tooling`，同时仍然保留 probe 证据，方便后续平台专用子流程接手。

## 运行最小 DeepAgents invoke smoke

如果你想验证“主 Agent + route tool（并注册专用子 Agent）”这条深度编排链路，但又不想依赖外部模型或真实浏览器，可以直接跑纯 Python smoke：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-smoke"
```

这条 smoke 会：

- 构建 `deepagents` 主 Agent
- 通过 `route_reverse_task` 工具完成一次真实 invoke
- 产生 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage` 的完整消息链
- 打印 route 结果和最终消息摘要

适合用来验证：

- `build_reverse_agent()` 是否和当前 deepagents 版本对齐
- 工具函数是否具备可包装成 LangChain tool 的元数据
- 主 Agent 到 route tool 的闭环是否可用

### 子 Agent 委派 smoke

如果你还想验证主 Agent 通过 `task` 工具委派给 general-purpose 子 Agent 的链路，可以再跑这个：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_subagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-subagent-smoke"
```

这条 smoke 会验证：

- 主 Agent 生成 `task` tool call
- deepagents 启动 general-purpose 子 Agent
- 子 Agent 的单条结果被回收到主线程
- 消息链完整呈现为 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage`

### Rebuild Delivery smoke

如果你想验证 deepagents 主 Agent 的 rebuild delivery 工具链路，可以跑：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_delivery_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-delivery-smoke"
```

这条 smoke 会验证：

- 先用 mock runtime 准备一份已验证 `FinalResult`
- 主 Agent 调用 `build_rebuild_delivery`
- 生成结构化 `RebuildResult`
- 产出 `workspace/rebuild-plan.json`
- 产出 `rebuild/sign_rebuild.py`
- 产出 `rebuild/replay_demo.py`
- 产出 `rebuild/scrapy_middleware.py`

对应 deepagents 能力已接入：

- tool：`build_rebuild_delivery`
- subagent：`rebuild_delivery`
- schema：`RebuildResult`

## 本地 sign fixture 样例

项目内置了一个可重复的 `localhost` Web 逆向样例，用来验证 sign 入口、请求样本和源码命中链路。

相关入口：

- fixture 服务：`reverse-agent-fixture`
- fixture smoke：`reverse-agent-fixture-smoke`
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

页面与脚本：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/app.js`
- `http://127.0.0.1:8765/api/search`

`app.js` 中包含稳定的入口特征：

- `function buildSign(keyword, timestamp)`
- `x-sign`
- `window.reverseFixture.search(...)`

使用 mock runtime 跑 fixture smoke：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime mock \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mock"
```

使用真实 MCP + 受管 Chrome 跑 fixture smoke：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime mcp \
  --ensure-chrome \
  --jsreverser-mcp-command "/opt/homebrew/bin/jsreverser-mcp" \
  --chrome-debug-port 9445 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-fixture-smoke" \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mcp"
```

多策略真实 smoke 示例：

```bash
reverse-agent-fixture-smoke \
  --profile sha256 \
  --runtime mcp \
  --ensure-chrome \
  --chrome-debug-port 9456 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-sha256" \
  --artifact-root "<repo-root>/artifacts/fixture-sha256-mcp"
```

如果要验证运行时上下文采集与 context-aware delivery：

```bash
reverse-agent-fixture-smoke \
  --profile context-localstorage \
  --runtime mcp \
  --ensure-chrome \
  --chrome-debug-port 9457 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-context" \
  --artifact-root "<repo-root>/artifacts/fixture-context-mcp"
```

Phase 13 还可以直接验证 cookie / navigator 两类上下文：

```bash
reverse-agent-fixture-smoke \
  --profile context-cookie \
  --runtime mcp \
  --ensure-chrome \
  --chrome-debug-port 9460 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-phase13-cookie-9460" \
  --artifact-root "<repo-root>/artifacts/phase13-cookie-mcp"

reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime mcp \
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

`context-navigator` 的预期是 `runtime_context_required = ["navigator"]`，生成的 `sign_rebuild.py` 会固化 `NAVIGATOR_USER_AGENT` 并完成 `sha256_keyword_timestamp` self-check。

当前已验证真实 MCP smoke 结果：

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
- 能自动完成候选函数 runtime validation 与 replay 校验：
  - `source = function_validation_result`
  - `source = function_validation_summary`
  - artifact：`virtual://workspace/function-validations.json`
  - artifact：`virtual://workspace/function-validation-summary.json`
  - 当前 fixture 可稳定验证 `buildSign` 与 `search` 两张函数卡片，并完成 replay
- 能自动生成纯算交付包：
  - `workspace/rebuild-plan.json`：描述候选函数、算法策略、pure extraction 状态、验证状态、replay URL 和输出文件
  - `rebuild/sign_rebuild.py`：浏览器外纯 Python sign 计算脚本
  - `rebuild/replay_demo.py`：浏览器外 HTTP replay demo
  - `rebuild/scrapy_middleware.py`：Scrapy downloader middleware 接入草案
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
- `chrome_launch.ok = true`
- `chrome_stop.ok = true`
- 结束后调试端口无残留监听

### 纯算 replay 交付包

真实 MCP fixture smoke 完成后，可以先对生成的 sign 脚本做 sample self-check：

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

### Pure extraction 策略字段

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

当前 strategy detection 通过 `reverse_deepagent.strategies` 包里的 `AlgorithmStrategyRule` registry 管理；`rebuild.py` 只保留兼容代理。strategy 输出保留旧 `confidence` 字符串，同时新增 `confidence_score`，记录数值分数、positive markers 和 caveats。registry metadata 可由 `list_algorithm_strategy_registry()` 读取。当前默认顺序：

1. `deterministic_fixture`：发射 `fixture_seed_mod100000`
2. `sig_template`：发射 `sig_keyword_timestamp_template`
3. `crypto_hash`：发射 `md5_keyword_timestamp`、`sha1_keyword_timestamp`、`sha256_keyword_timestamp`、`hmac_sha256_keyword_timestamp`（需要能提取 literal secret）
4. `encoding`：发射 `base64_keyword_timestamp`、`urlencode_keyword_timestamp`

策略库还提供 `STRATEGY_SAMPLE_CORPUS` / `list_strategy_sample_corpus()`，覆盖 fixture reducer、MD5、SHA-1、SHA-256、HMAC-SHA256、Base64 和 URL encoding 的 deterministic samples。测试会用这些样本同时验证 detector 输出和生成的 `sign_rebuild.py` self-check。

WASM、JS VM、重混淆、反调试和动态 secret 这类流程不能被硬说成 pure-Python 可移植。对应边界见 [`docs/strategy/wasm-vm-obfuscation-triage.md`](docs/strategy/wasm-vm-obfuscation-triage.md)：这类场景应输出 triage-only / runtime-assisted / partial 计划，并通过 `review_hints` 阻断误导性的纯算交付。

当前会阻断 pure extraction 的运行时上下文依赖：

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
    "captured_runtime_context": ["localStorage"]
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

生成的 `sign_rebuild.py` 会把采集到的上下文写成默认常量，用于浏览器外 replay。当前 renderer 已覆盖 `localStorage.device_id`、`cookie.device_id` 和 `navigator.userAgent` 三类上下文。

`review_hints` 是给后续人工 review、CI gate 或子智能体复核使用的 machine-readable 提示，不替代 `ready` / `pure_extraction`。当前由 `reverse_deepagent.schemas.ReviewHint` 集中约束，固定字段为 `severity`、`category`、`code`、`message`、`evidence`，会覆盖 pure rebuild、context-aware rebuild、manual port / partial rebuild，以及 volatile runtime context 等风险。

`workspace/runtime-context-diff.json` 会对运行时上下文做稳定性摘要。默认 runtime 会采集多次样本，字段包括 `status`（`multi_sample` 或 `single_sample` fallback）、`sample_count`、`stable`、`stable_keys`、`volatile_keys`、`missing_requirements` 和 `changes`。其中 `sample_index` / `collected_at_ms` 只作为采样元数据，不参与稳定性判断；`volatile_keys` 应被视为 replay 时仍需要运行时绑定的输入。

## Runtime backend capabilities

Runtime backend 能力通过 `RuntimeBackendCapabilities` 描述，调用方可以用 `runtime.describe_capabilities()` 做能力发现，而不是在 coordinator 里硬猜 MCP、Chrome 或 mock backend 的行为。

示例：

```python
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends

print(list_runtime_backends())

runtime = build_runtime("mock")
capabilities = runtime.describe_capabilities()
print(capabilities.model_dump(mode="json"))
```

`build_runtime(...)` 现在通过 `RuntimeBackendRegistry` 创建 backend，当前默认注册：

- `mock`（alias: `in-process`）：公开 CI 和本地 deterministic demo 使用
- `mcp`（alias: `jsreverser-mcp`）：真实 JSReverser MCP + Chrome DevTools runtime
- `playwright-cli`（alias: `playwright`, `pw-cli`）：轻量 Playwright CLI probe + static source fetch，不主动启动浏览器
- `chrome-cdp`（alias: `cdp`, `devtools`）：连接既有 Chrome DevTools endpoint，不主动启动 Chrome
- `browser-cli`（alias: `cli-browser`, `browser-command`）：通用浏览器 CLI shim backend，默认 command 未配置
- `android-adb`（alias: `adb`, `android-device`）：Android ADB 工具链探测与平台 artifact export
- `ios-simulator`（alias: `simctl`, `ios-sim`）：iOS Simulator / `xcrun simctl` 工具链探测与平台 artifact export
- `mini-program-devtools`（alias: `mp-devtools`, `wechat-devtools`）：小程序 vendor devtools CLI 配置探测与平台 artifact export

每次 pipeline 会额外写出 `workspace/backend-artifact-manifest.json`，用 `RuntimeArtifactManifest` / `RuntimeArtifactManifestEntry` 描述 artifact key、路径、类别、kind、producer backend、transport 和 target platforms。这个 manifest 是新增索引，不替换现有 `exports/artifact-index.json`。跨平台 artifact category 词表见 [`docs/runtime/platform-neutral-artifact-categories.md`](docs/runtime/platform-neutral-artifact-categories.md)。

非 Web 运行时会沿用同一套 capability / manifest 边界，但不能复用 Web-only 的 browser session 语义。当前接口草案：

- Android: [`docs/runtime/android-adapter-interface.md`](docs/runtime/android-adapter-interface.md)
- iOS: [`docs/runtime/ios-adapter-interface.md`](docs/runtime/ios-adapter-interface.md)
- Mini-program: [`docs/runtime/mini-program-adapter-interface.md`](docs/runtime/mini-program-adapter-interface.md)

当前 Web 路径的浏览器会话、Chrome debug port、JSReverser MCP、Web storage、URL replay 推导等假设统一收口在 [`docs/runtime/web-runtime-assumptions.md`](docs/runtime/web-runtime-assumptions.md)，后续平台 adapter 不应默认继承这些语义。

JSReverser MCP 后端配置由 `JSReverserMcpConfig` 收束，字段包括 `command`、`browser_url`、`request_timeout`、`startup_timeout`、backend metadata 和 runtime sampling 参数。CLI 里的 `--jsreverser-mcp-command`、Chrome debug port 等参数最终都会汇入这个 config，再创建 MCP runtime。

核心字段包括：

- `backend_id`：稳定后端标识，例如 `mock`、`jsreverser-mcp`
- `transport`：实现传输，例如 `in-process`、`mcp-stdio`
- `target_platforms`：当前目标平台，现阶段主要是 `web`
- `supports_web_recon` / `supports_runtime_context` / `supports_replay_validation`：能力开关
- `managed_chrome` / `mcp_backed`：运行时约束提示
- `evidence_kinds` / `artifact_kinds`：该 backend 常见输出类型

当前 Android / iOS / 小程序 backend 已具备 registry / factory / capability metadata / side-effect-light tool probe / artifact export 基础层，并可通过平台中立 `reverse-agent-platform` pipeline 落盘 capabilities、probe、export bundle、manifest 与报告；但还不包含真实 hook、静态分析或 replay validation。完整约定见 [`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## Chrome Debug Session 约束

真实 MCP runtime 依赖 `http://127.0.0.1:9222` 这类 Chrome DevTools 端口。

约束：

- Agent 不应该假设 9222 Chrome 已经存在
- 真实 Web recon 前必须先完成 Chrome debug session 检查
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

## 运行真实 MCP smoke

完整前置条件和故障排查见 [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)。

先探测真实 `jsreverser-mcp` stdio 协议和工具列表：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/probe_jsreverser_mcp.py"
```

已验证当前本机 `jsreverser-mcp`：

- 协议：stdio JSON-RPC newline framing
- negotiated protocol version：`2025-03-26`
- tools/list 可返回 73 个工具

## 运行最小 Demo（真实 MCP runtime）

真实 MCP runtime 会启动 `/opt/homebrew/bin/jsreverser-mcp --browserUrl http://127.0.0.1:9222`。

```bash
reverse-agent-demo \
  --runtime mcp \
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

## 真实 Chrome smoke（可调端口）

已验证一条真实 smoke 链路，可以在隔离端口上启动受管 Chrome，再交给 `jsreverser-mcp`：

```bash
reverse-agent-demo \
  --runtime mcp \
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

- `jsreverser-mcp` 的真实输出可能是 Markdown + fenced JSON 的混合文本，适配层已经做了归一化
- 如果你改了 `--chrome-debug-port`，`reverse-agent-demo` 会把这个端口同步传给 MCP 后端，不会再傻乎乎地默认连 9222

## 测试

```bash
cd "<repo-root>"
"<repo-root>/.venv/bin/python" \
  -m unittest discover -s "<repo-root>/tests" -p "test_*.py"
```

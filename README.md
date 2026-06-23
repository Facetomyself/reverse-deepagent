# reverse-deepagent

[![CI](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml)

Web / JavaScript 逆向流程的 DeepAgents 演示项目。聚焦本地授权场景：归一化逆向任务、通过运行时适配器采集 Web 证据、验证候选签名函数，并生成 replay / rebuild 交付物。

> 发布线：`v0.1.x`。详见 [CHANGELOG.md](CHANGELOG.md) 与 [ROADMAP.md](ROADMAP.md)。
> BrowserProvider 架构：[docs/runtime/browser-provider-architecture.md](docs/runtime/browser-provider-architecture.md)
> Runtime adapter 契约：[docs/runtime/adapter-pluginization-contract.md](docs/runtime/adapter-pluginization-contract.md)

## Quick Start

```bash
git clone https://github.com/Facetomyself/reverse-deepagent.git
cd reverse-deepagent
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

运行 mock 运行时（无需浏览器）：

```bash
reverse-agent-demo --runtime mock
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

真实浏览器链路（native-web + Playwright）：

```bash
reverse-agent-demo --runtime native-web --browser playwright-chromium --task-text "https://example.com 找 sign 入口"
```

环境重建：

```bash
uv pip install --python ".venv/bin/python" -e .
```

安装可选依赖：

```bash
uv pip install --python ".venv/bin/python" -e ".[llm]"    # OpenAI/LLM 支持
uv pip install --python ".venv/bin/python" -e ".[cloak]"  # CloakBrowser
pip install reverse-deepagent[scrapy]                      # Scrapy replay
```

更多运行时选项见 [docs/runtime/browser-provider-operations.md](docs/runtime/browser-provider-operations.md)。

## Architecture Overview

项目采用分层架构：

- **Agent 层**：DeepAgents（LangGraph）编排 coordinator、router、web_recon、rebuild、delivery 等子智能体。
- **Runtime 层**：`RuntimeBackendRegistry` 管理 mock / native-web / chrome-cdp / playwright-cli 等后端，通过 `RuntimeBackendCapabilities` 做能力发现。
- **BrowserProvider 层**：`BrowserProviderRegistry` 切换 playwright-chromium / cloakbrowser / remote-cdp 及外部插件。
- **Strategy 层**：`StrategyDetectorRegistry` 管理算法策略检测器；不启动 detector 时不启动浏览器或调用 MCP。
- **Evidence 层**：标准化 `EvidenceItem` → validated → promoted 管线 + review gate 阻断机制。
- **Delivery 层**：local delivery、external delivery（webhook / presigned / GH Release）、transaction lock provider + 审计 journal。

详细设计：[docs/design/reverse-deepagent-architecture.md](docs/design/reverse-deepagent-architecture.md)

## DeepAgents Memories

`build_reverse_agent(...)` 在 `CompositeBackend` 中启用三个路由：

- `/workspace/`：`StateBackend`，当前任务临时草稿
- `/artifacts/`：`FilesystemBackend`，人工检查的报告和交付物
- `/memories/`：`StoreBackend`，跨 agent / 跨会话复用的长期逆向经验

`/memories/` 只保存可复用经验（站点入口、protection 处理、签名模式），不保存未验证的一次性数据。

## Documentation Index

### Runtime (`docs/runtime/`)

| Doc | Covers |
|-----|--------|
| [browser-provider-architecture.md](docs/runtime/browser-provider-architecture.md) | BrowserProvider registry 整体架构 |
| [browser-provider-operations.md](docs/runtime/browser-provider-operations.md) | doctor/smoke CLI、provider matrix、runtime backend registry |
| [cloakbrowser-provider.md](docs/runtime/cloakbrowser-provider.md) | CloakBrowser 集成指南 |
| [jsreverser-mcp-setup.md](docs/runtime/jsreverser-mcp-setup.md) | Legacy MCP 安装与故障排查 |
| [workspace-and-delivery.md](docs/runtime/workspace-and-delivery.md) | Workspace contract、evidence promotion、review gate、delivery transaction |
| [native-web-capabilities.md](docs/runtime/native-web-capabilities.md) | native-web 能力详述（paused session、source map、heap、hook、module discovery） |
| [sign-fixtures.md](docs/runtime/sign-fixtures.md) | 本地 sign fixture 样例与 context-aware delivery |
| [web-runtime-assumptions.md](docs/runtime/web-runtime-assumptions.md) | Web 路径浏览器会话、CDP、存储假设 |
| [platform-neutral-artifact-categories.md](docs/runtime/platform-neutral-artifact-categories.md) | 跨平台 artifact category 词表 |
| [adapter-pluginization-contract.md](docs/runtime/adapter-pluginization-contract.md) | 平台 adapter 插件化契约 |
| [android-adapter-interface.md](docs/runtime/android-adapter-interface.md) | Android ADB 适配器接口 |
| [ios-adapter-interface.md](docs/runtime/ios-adapter-interface.md) | iOS Simulator 适配器接口 |
| [mini-program-adapter-interface.md](docs/runtime/mini-program-adapter-interface.md) | 小程序适配器接口 |

### Design, Plans, CI, Strategy

| Area | Doc |
|------|-----|
| Architecture | [docs/design/reverse-deepagent-architecture.md](docs/design/reverse-deepagent-architecture.md) |
| MCP deprecation plan | [docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md](docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md) |
| CI: MCP smoke | [docs/ci/self-hosted-mcp-smoke.md](docs/ci/self-hosted-mcp-smoke.md) |
| WASM/VM triage | [docs/strategy/wasm-vm-obfuscation-triage.md](docs/strategy/wasm-vm-obfuscation-triage.md) |

### Status Reports (`docs/status/`)

参见 `docs/status/` 目录下的 rollout 阶段状态评估文档。

### Reference (`docs/reference/deepagents/`)

DeepAgents 学习资料，参见 `docs/reference/deepagents/` 目录。

## CLI Entry Points

| Command | Purpose |
|---------|---------|
| `reverse-agent-demo` | 运行 demo pipeline（mock / native-web / legacy-mcp） |
| `reverse-agent-platform` | 平台中立 pipeline（Android / iOS / 小程序） |
| `reverse-agent-fixture` | 启动本地 sign fixture 服务 |
| `reverse-agent-fixture-smoke` | fixture 冒烟测试 |
| `reverse-agent-doctor` | 环境检查（browser / runtime / delivery） |
| `reverse-agent-browser-provider-smoke` | BrowserProvider smoke 证据生成与审阅 |
| `reverse-agent-browser-provider-smoke-policy` | CI PR gate |
| `reverse-agent-openai-smoke` | OpenAI-backed DeepAgents 冒烟 |
| `reverse-agent-workspace-dual-write-smoke` | Workspace dual-write smoke |

## Project Structure

```
src/reverse_deepagent/   # 源码骨架与 runtime adapter
  coordinator.py         # 包内协调入口
scripts/                 # 运行与开发脚本
tests/                   # 测试（unittest）
docs/                    # 文档
  design/                # 架构与设计
  plans/                 # 规划
  runtime/               # 运行时契约与适配器
  ci/                    # CI 相关
  strategy/              # 策略文档
  status/                # 阶段状态报告
artifacts/               # mock demo 产出物
packages/                # 外部插件模板包
```

## DeepAgents Smoke Tests

纯 Python 冒烟（不依赖外部模型或浏览器）：

```bash
PYTHONPATH="src" .venv/bin/python scripts/run_deepagent_smoke.py
PYTHONPATH="src" .venv/bin/python scripts/run_deepagent_subagent_smoke.py
PYTHONPATH="src" .venv/bin/python scripts/run_deepagent_delivery_smoke.py
PYTHONPATH="src" .venv/bin/python scripts/run_deepagent_memory_smoke.py
```

## OpenAI API Setup

```bash
uv pip install --python ".venv/bin/python" -e ".[llm]"
read -rsp "OPENAI_API_KEY: " OPENAI_API_KEY && export OPENAI_API_KEY
export OPENAI_MODEL="gpt-5.5"
reverse-agent-openai-smoke --task-text "http://localhost 找 sign 入口" --artifact-root "artifacts/openai-smoke"
```

## Chrome Debugging (Legacy MCP)

`legacy-mcp` 运行时依赖 Chrome DevTools 端口。

约束：Agent 不假设 Chrome 已存在；`--ensure-chrome` 时启动受管 Chrome，否则结构化返回失败。启动参数通过环境变量调整（`CHROME_PATH`、`DEBUG_PORT`、`USER_DATA_DIR` 等）。

```bash
DEBUG_PORT=9333 USER_DATA_DIR="/tmp/reverse-agent-chrome" scripts/start_chrome_debug.sh
```

完整故障排查：[docs/runtime/jsreverser-mcp-setup.md](docs/runtime/jsreverser-mcp-setup.md)

## Contributing

1. 从 `main` 创建分支，命名 `type/short-description`。
2. 新增 runtime adapter 或 BrowserProvider 遵循 [adapter-pluginization-contract.md](docs/runtime/adapter-pluginization-contract.md)。
3. 修改 workspace artifact 路由时同步更新 workspace-contract.json 生成逻辑与 manifest。
4. 运行测试：`python -m unittest discover -s tests -v`。
5. 提交 message 遵循常规 commit convention。
6. API key 不写入代码或文档，使用环境变量或 keychain。

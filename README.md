# reverse-deepagent

[![CI](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml)

Web / JS 前端逆向工程框架。归一化逆向任务 → 通过 BrowserProvider 适配层采集 Web 运行时证据 → 验证候选签名函数 → 生成 replay / rebuild 交付物。支持 mock / native-web（Playwright CDP） / Remote CDP 等多种运行时后端。

> **当前状态**：`v0.1.x`，1765 tests OK，9/12 审计 finding 已闭合。详见 [ROADMAP.md](ROADMAP.md) 和 [CHANGELOG.md](CHANGELOG.md)。

## Quick Start

```bash
git clone https://github.com/Facetomyself/reverse-deepagent.git
cd reverse-deepagent
python -m venv .venv && . .venv/bin/activate
python -m pip install -U pip && python -m pip install -e .
```

Mock 运行时（无需浏览器，快速验证管线）：

```bash
reverse-agent-demo --runtime mock
```

真实浏览器（native-web + Playwright Chromium CDP）：

```bash
reverse-agent-demo --runtime native-web --browser playwright-chromium \
  --task-text "https://example.com 找 sign 入口"
```

运行测试：

```bash
python -m unittest discover -s tests -v    # 1765 tests
```

可选依赖：

```bash
uv pip install --python ".venv/bin/python" -e ".[llm]"   # OpenAI/LLM
uv pip install --python ".venv/bin/python" -e ".[cloak]" # CloakBrowser
```

更多运行时选项见 [docs/runtime/browser-provider-operations.md](docs/runtime/browser-provider-operations.md)。

## Architecture

```
Agent (LangGraph DeepAgents)
  ├─ Router → Web Recon → Rebuild → Delivery
  │
Runtime Layer (RuntimeBackendRegistry)
  ├─ mock / native-web / chrome-cdp / playwright-cli
  ├─ RuntimeBackendCapabilities (side-effect-free discovery)
  │
BrowserProvider Layer (BrowserProviderRegistry)
  ├─ playwright-chromium / cloakbrowser / remote-cdp
  ├─ 外部插件包: S3-compatible / GitLab Release / Internal Registry
  │
Evidence Pipeline
  ├─ EvidenceItem → validate → promote
  ├─ Review gate + delivery transaction lock
  │
Strategy Layer
  ├─ StrategyDetectorRegistry (不启动浏览器，不调用 MCP)
  ├─ Runtime context stability diff + WASM/VM triage planner
```

核心模块：

| 模块 | 大小 | 职责 |
|---|---|---|
| `coordinator.py` | 1,163 行 | Pipeline 入口、输出写入、artifact 路由 |
| `native_web.py` | ~11,834 行 | 主 Web 运行时：dispatch、collectors、hooks |
| `artifact_tools.py` | 13,468 行 | Workspace artifact 读写、journal loader |
| `runtime/factories.py` | 151 行 | 9 个运行时工厂函数 |
| `runtime/registry.py` | 431 行 | 运行时注册表、后端发现 |
| `runtime/manifest.py` | 376 行 | 后端 artifact manifest、分类目录 |

详细设计：[docs/design/reverse-deepagent-architecture.md](docs/design/reverse-deepagent-architecture.md)

## Documentation

### 运行时 (`docs/runtime/`)

| 文档 | 内容 |
|---|---|
| [browser-provider-architecture.md](docs/runtime/browser-provider-architecture.md) | BrowserProvider registry 架构 |
| [browser-provider-operations.md](docs/runtime/browser-provider-operations.md) | Doctor/smoke CLI、provider matrix、registry |
| [native-web-capabilities.md](docs/runtime/native-web-capabilities.md) | Paused session、source map、heap、hook、module discovery |
| [workspace-and-delivery.md](docs/runtime/workspace-and-delivery.md) | Workspace contract、evidence、review gate、delivery |
| [sign-fixtures.md](docs/runtime/sign-fixtures.md) | Sign fixture 样例与 context-aware delivery |
| [adapter-pluginization-contract.md](docs/runtime/adapter-pluginization-contract.md) | 平台 adapter 插件化契约 |
| [web-runtime-assumptions.md](docs/runtime/web-runtime-assumptions.md) | Web 路径的浏览器/CDP/存储假设 |
| [platform-neutral-artifact-categories.md](docs/runtime/platform-neutral-artifact-categories.md) | 跨平台 artifact category 词表 |

另有 cloakbrowser-provider、legacy MCP setup、Android/iOS/小程序 adapter 接口文档。

### 设计、规划、策略

| 文档 |
|---|
| [MCP deprecation plan](docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md) |
| [Source dispatch decomposition plan](docs/plans/2026-06-12-source-dispatch-decomposition-plan.md) |
| [Native web fallback dispatch contract](docs/runtime/native-web-fallback-dispatch-contract.md) |
| [WASM/VM triage strategy](docs/strategy/wasm-vm-obfuscation-triage.md) |
| [CI: self-hosted MCP smoke](docs/ci/self-hosted-mcp-smoke.md) |

进展报告见 [`docs/status/`](docs/status/)。

## CLI Entry Points

| 命令 | 用途 |
|---|---|
| `reverse-agent-demo` | Web demo pipeline（mock / native-web / legacy-mcp） |
| `reverse-agent-platform` | 平台中立 pipeline（Android / iOS / 小程序） |
| `reverse-agent-fixture` | 启动本地 sign fixture 服务 |
| `reverse-agent-fixture-smoke` | Fixture 冒烟测试 |
| `reverse-agent-doctor` | 环境检查（browser / runtime / delivery） |
| `reverse-agent-browser-provider-smoke` | BrowserProvider smoke 证据生成与审阅 |
| `reverse-agent-browser-provider-smoke-policy` | CI/PR gate |
| `reverse-agent-openai-smoke` | OpenAI DeepAgents 冒烟 |
| `reverse-agent-workspace-dual-write-smoke` | Workspace dual-write 冒烟 |

## Project Structure

```
src/reverse_deepagent/
  coordinator.py               Pipeline 入口
  adapters/                     Runtime adapter（native_web, jsreverser, lightweight_web）
  runtime/                      Registry、factories、manifest、lifecycle、mock bridge
  browser/                      Collectors、hooks、providers、source_maps、redaction
  delivery/                     Transaction、lock provider、rollback、resume
  tools/                        Artifact tools、route tools
  subagents/                    DeepAgents subagent 定义
  prompts/                      Subagent 提示模板
scripts/                        运行与开发脚本
tests/                          unittest（1765 cases）
docs/
  design/                       架构设计
  plans/                        规划文档
  runtime/                      运行时契约与适配器
  ci/                           CI 策略
  strategy/                     逆向策略
  status/                       阶段进展报告
artifacts/                      Mock demo 产出物
packages/                       外部 BrowserProvider / delivery 插件包
```

## Chrome Debugging (Legacy MCP)

`legacy-mcp` 依赖 Chrome DevTools 端口。Agent 不假设 Chrome 已存在——`--ensure-chrome` 时启动受管 Chrome，否则返回结构化失败。

```bash
DEBUG_PORT=9333 USER_DATA_DIR="/tmp/reverse-agent-chrome" scripts/start_chrome_debug.sh
```

完整文档：[docs/runtime/jsreverser-mcp-setup.md](docs/runtime/jsreverser-mcp-setup.md)

## OpenAI / LLM

```bash
uv pip install --python ".venv/bin/python" -e ".[llm]"
export OPENAI_API_KEY="sk-..." OPENAI_MODEL="gpt-5.5"
reverse-agent-openai-smoke --task-text "http://localhost 找 sign 入口" \
  --artifact-root "artifacts/openai-smoke"
```

## Contributing

1. 从 `main` 分支创建 `type/short-description` 分支
2. 新增 runtime adapter 或 BrowserProvider 遵循 [adapter-pluginization-contract.md](docs/runtime/adapter-pluginization-contract.md)
3. 修改 artifact 路由时同步更新 workspace contract 与 manifest
4. 运行 `python -m unittest discover -s tests -v`，确保 1765 tests 全通过
5. Commit message 遵循常规 commit convention
6. API key 不写入代码或文档，使用环境变量

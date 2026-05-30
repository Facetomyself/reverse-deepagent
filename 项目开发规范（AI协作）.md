# 项目开发规范（AI协作）

本文档是面向 AI 与开发者的 `reverse-deepagent` 项目开发规范。

本文档已经适配到 `reverse-deepagent` 仓库。后续 AI 开发必须同时遵守根目录 [`AGENTS.md`](./AGENTS.md)，其中的仓库级规则优先解释本文里的通用规则。

## 阅读顺序要求

任何涉及代码、流程、配置、测试、文档、提交、合并、发布的任务，开始前必须实际阅读或重新核对：

1. [AGENTS.md](./AGENTS.md)
2. [开发者AI开发与PR提交流程.md](./开发者AI开发与PR提交流程.md)
3. 当前文件
4. [README.md](./README.md)
5. [CONTRIBUTING.md](./CONTRIBUTING.md)
6. [docs/runtime/browser-provider-architecture.md](./docs/runtime/browser-provider-architecture.md)
7. [docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md](./docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md)
8. 涉及 legacy MCP 时，再补读 [docs/runtime/jsreverser-mcp-setup.md](./docs/runtime/jsreverser-mcp-setup.md)、[docs/ci/self-hosted-mcp-smoke.md](./docs/ci/self-hosted-mcp-smoke.md) 和 [docs/design/reverse-deepagent-architecture.md](./docs/design/reverse-deepagent-architecture.md)。

不能只凭历史记忆、上一次会话摘要或“看起来知道项目”直接开发。

## 0. AI 协作执行协议

### 0.1 开发前必须确认仓库现状

开始任何开发前，至少确认：

```bash
git status --short --branch
git remote -v
git branch --show-current
```

如果任务涉及 GitHub PR、PR 评论、PR 合并或远端分支管理，还必须确认：

```bash
gh --version
gh auth status
git fetch origin
```

要求：

- 不能在没看当前分支、远端和工作区状态的情况下开始写代码。
- 如果当前工作区有无法确认归属的脏改动，必须先停下来说明，不能偷偷带进本次提交，也不能擅自删除。
- 如果 `gh` 不可用、未登录、账号错误或权限不足，必须明确告诉开发者，不准假装已经完成 GitHub 操作。

### 0.2 分析与实现不能脱节

- 先读相关源码链路，再改代码。
- 分析中确认“不应该出现”的兼容分支、旧路径或旧口径，开发时就应清理，不要继续堆“保险式兼容”。
- 如果需求是升级主线架构，不要为了表面兼容把逻辑重新堆回旧抽象。
- 如果为了防御未知边界保留分支，必须说明它属于哪个真实 runtime、provider、collector、hook 或 CLI 场景。
- 不能把某个层不该处理的事情偷偷塞到后续层里收尾。

### 0.3 开发方案与开发清单

用户要求写开发方案时，方案必须至少包含：

1. 需求理解与真实目标。
2. 现有源码链路分析。
3. 是否符合要求、是否完善、是否完整、是否正确。
4. 是否符合本开发规范、现有架构和现有命名。
5. 方案自身是否有缺陷、边界遗漏或上下游设计冲突。
6. 与本功能没有直接代码关系但有文档、测试、workflow 或 artifact 关联的模块检查。
7. 分阶段开发清单。
8. 每个阶段完成后的自检项。
9. 最终全量审查项。

进入开发后，必须按开发清单一个阶段一个阶段完成。阶段自检未通过时，不能进入下一阶段。

## 1. 项目架构原则

本仓库是 Python / DeepAgents / Web 逆向项目。

核心目录：

- `src/reverse_deepagent/`：核心源码。
- `tests/`：单元测试与 smoke 测试。
- `scripts/`：本地辅助脚本。
- `docs/`：长期设计、runtime、CI、迁移计划文档。
- `README.md`、`CONTRIBUTING.md`：对外说明与贡献入口。

### 1.1 Runtime / BrowserProvider 主线

- `native-web + BrowserProvider + native collectors / hooks` 是 Web 逆向主线。
- `legacy-mcp` 是兼容后端。
- `mcp` / `jsreverser-mcp` 只作为 legacy alias 保留。
- 浏览器实现应通过 `BrowserProvider` 可插拔，不要把 MCP 当成新的抽象边界。
- coordinator 不应直接依赖 Playwright、CDP、CloakBrowser 或 MCP tool name。
- 新增 runtime / provider / collector / hook / artifact schema 时，必须同步测试和文档。

### 1.2 模块边界

- `src/reverse_deepagent/coordinator.py` 应保持编排层和装配层职责，不要无限堆业务细节。
- `src/reverse_deepagent/adapters/` 放 runtime adapter。
- `src/reverse_deepagent/browser/` 放 BrowserProvider、collector、hook、session adapter。
- `src/reverse_deepagent/runtime/` 放 runtime base、registry、Chrome / MCP transport 辅助能力。
- `src/reverse_deepagent/subagents/` 放 DeepAgents 子 agent 语义层。
- `src/reverse_deepagent/tools/` 放 agent 工具封装。
- `src/reverse_deepagent/rebuild.py`、`src/reverse_deepagent/strategies/` 放 pure extraction、rebuild、strategy 相关逻辑。

新增功能必须先判断应落在哪一层，禁止把 provider、runtime、collector、hook、CLI、doctor、rebuild 逻辑混在一个文件里。

### 1.3 平台扩展边界

本项目当前重点是 Web / JS 逆向，但要保留 Android、iOS、小程序扩展空间：

- 平台能力应通过 runtime adapter 和 capability metadata 接入。
- 不要把 Web 专属 browser session、Chrome debug port、MCP 语义强行套给移动端或小程序端。
- 平台 artifact 类别应遵守 `docs/runtime/platform-neutral-artifact-categories.md`。
- 平台接口变化应同步 `docs/runtime/android-adapter-interface.md`、`docs/runtime/ios-adapter-interface.md`、`docs/runtime/mini-program-adapter-interface.md` 中对应文档。

## 2. 新增功能接入规范

### 2.1 新增 runtime backend

必须同步检查：

1. `RuntimeBackendCapabilities` 是否准确。
2. `RuntimeBackendRegistry` 是否注册 canonical id 和 alias。
3. backend 是否能在 metadata listing 中保持 side-effect-free。
4. artifact manifest 是否能正确标记 producer backend / transport / target platforms。
5. `tests/test_runtime_registry.py`、`tests/test_coordinator.py`、相关 pipeline 测试是否覆盖。
6. README 与相关 `docs/runtime/` 是否同步。

### 2.2 新增 BrowserProvider

必须同步检查：

1. provider contract 是否符合 `src/reverse_deepagent/browser/base.py`。
2. capabilities 是否 JSON serializable，不能泄漏 proxy 密码、cookie、token。
3. provider listing 不能启动浏览器、下载二进制或连接外部服务。
4. CLI / doctor 参数是否需要暴露。
5. `tests/test_browser_provider_*`、provider 专项测试、doctor 测试是否覆盖。
6. `docs/runtime/browser-provider-architecture.md` 与 provider 专题文档是否同步。

### 2.3 新增 collector / hook / breakpoint 能力

必须同步检查：

1. provider 不支持能力时是否结构化 `unsupported`，不能让 recon 整体崩掉。
2. evidence / artifact payload 是否归一化。
3. 是否避免泄漏 raw cookie value、Authorization、proxy 密码、request body 中的敏感 token。
4. 是否只在明确 protection / debug 请求下触发 breakpoint，不作为默认 recon 副作用。
5. 对应测试是否覆盖成功、unsupported、失败路径。

### 2.4 新增 CLI / doctor / workflow 参数

必须同步检查：

1. console entrypoint 是否仍可通过 `pyproject.toml` 暴露。
2. help 文案是否符合当前 canonical runtime 口径。
3. doctor 默认行为是否 side-effect-free。
4. workflow 是否仍不依赖本地私有二进制，除非是明确 self-hosted 任务。
5. README、CONTRIBUTING、CI 文档是否同步。
6. `tests/test_doctor.py`、`tests/test_console_script.py`、`tests/test_run_demo*.py` 是否覆盖。

### 2.5 新增 pure extraction / rebuild / strategy

必须同步检查：

1. rebuild plan 是否基于 validated evidence，不靠猜。
2. runtime context 依赖是否明确阻断或显式注入。
3. generated `sign_rebuild.py`、`replay_demo.py`、Scrapy middleware / project 是否自检。
4. review gate 是否能阻断低证据或高风险输出。
5. `tests/test_rebuild_artifacts.py`、`tests/test_strategy_*` 是否覆盖。

## 3. 测试规范

### 3.1 最低验证

代码改动最低执行：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m compileall -q "src/reverse_deepagent" "tests"
```

定向测试按改动范围选择，例如：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest tests.test_coordinator tests.test_doctor -v
```

跨模块、架构性、提交前全量回归执行：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest discover -s tests -v
```

### 3.2 文档-only 改动

如果只修文档，可不运行全量代码测试，但必须至少执行：

```bash
git diff --check
```

并人工检查：

- 中文无乱码。
- 链接路径真实存在或明确是外部 URL。
- 命令示例符合当前仓库实际。
- 没有把旧 `mcp` 默认路径、旧分支名、旧执行方式写回新文档。

### 3.3 测试失败处理

- 测试失败时不得提交。
- 如果用户明确要求保留失败状态用于排查，必须在回复中说明失败命令、失败原因和下一步建议。
- 不能只删断言或降低测试强度来让测试变绿。

## 4. 文档更新规范

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

不能只在聊天或临时计划里说明长期行为变化。

## 5. Git / PR 规范

- 本仓库当前默认基线分支为 `main`。
- 通用 PR 流程文档里的 `dev`，在本仓库默认映射为 `main`。
- 如果用户没有要求 PR，且当前任务是直接维护本仓库，可以在当前分支按要求提交和推送。
- 如果用户要求创建或更新 PR，必须用 `gh` 的真实输出确认 PR base、head、state、mergeable 等信息。
- 未经明确授权，不得擅自合并 PR、关闭 PR、删除远端分支。
- 不允许把“同步 PR 分支”说成“已经合并到主分支”。

提交前至少执行：

```bash
git status --short
git diff --stat
git diff --check
```

提交信息必须描述真实改动，不得写 `update`、`fix bug`、`AI 修改`、`修改一下`。

## 6. 编码、换行与乱码

- 文件默认 UTF-8。
- 已有 UTF-8 with BOM 文件必须保留 BOM；当前文件就是 UTF-8 with BOM + LF。
- 修改已有文件时优先保持原换行风格。
- 新增文本文件默认 LF。
- 修改任何包含中文的文件时，必须检查是否出现乱码、错码、异常替换字符。
- 不允许在未确认编码的情况下批量重写中文文件。

## 7. AI 开发自检清单

每次修改后至少自问：

1. 我开发前是否重新核对了 `AGENTS.md`、两份流程文档、README 和相关 `docs/`？
2. 我是否先看了真实代码链路，而不是靠记忆或猜测？
3. 我有没有把别的项目旧示例误当成本仓库真实文件边界？
4. 我这次新增逻辑是否应该进入 `src/reverse_deepagent/` 下已有模块，而不是散落到临时脚本或大杂烩文件？
5. 如果改动 runtime / BrowserProvider / collector / hook，我有没有同步检查对应测试和 docs？
6. 如果改动 CLI / doctor / workflow，我有没有同步更新 README、workflow 文档和测试？
7. 如果改动 legacy MCP，我有没有保持 `legacy-mcp` canonical id 与 `mcp` alias 的边界？
8. 如果改动 native-web，我有没有避免重新把 MCP 当核心抽象？
9. 我有没有补或迁移测试，并运行适合本次范围的 `compileall` / unittest？
10. 我有没有执行 `git diff --check`？
11. 我新增或修改的文件是否有可见乱码、BOM 丢失、CRLF/LF 异常或异常替换字符？
12. 我有没有检查本次改动是否混入 `artifacts/`、`.venv/`、`*.egg-info`、`__pycache__/` 等生成物？
13. 我有没有逐项检查 diff，确认没有敏感信息、token、cookie、Authorization、proxy 密码？
14. 如果创建或更新 PR，我有没有真实检查 `gh auth status`、PR base、head 分支和远端状态？
15. 如果用户要求提交或推送，我有没有在提交前确认工作区只包含本次任务文件？

## 8. 完成标准

当满足以下条件时，可以视为一次合格开发完成：

- 代码职责边界清晰，符合本仓库 Python / DeepAgents / BrowserProvider 架构。
- 新旧功能链路完整，没有为了“保险”堆无意义旧分支。
- 开发清单各阶段已逐项完成并自检。
- native-web、BrowserProvider、legacy MCP、artifact schema 等核心口径没有倒退。
- 相关定向测试通过；跨模块改动全量 `unittest discover` 通过。
- README、CONTRIBUTING、`docs/runtime/`、`docs/plans/`、workflow 文档已按需同步。
- 没有可见乱码，BOM / 换行风格符合原文件要求。
- 提交前 `git diff --check` 通过。
- 提交前工作区范围已确认，没有误提交忽略目录、草稿、密钥或无关文件。

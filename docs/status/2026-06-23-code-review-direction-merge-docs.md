# Code Review：方向、合并与文档一致性审查（2026-06-23）

## 1. 审查目标

本次审查面向当前仓库 `/Users/mengma/reverse/reverse_agent`，重点不是做逐行 lint，而是确认三件事：

1. 项目方向是否仍符合 `native-web + BrowserProvider + native collectors / hooks` 主线，legacy MCP 是否仍被限制在兼容边界内。
2. 近期多分支 rollout 合并后，Git 历史、代码实际状态与状态文档是否一致，是否存在“文档宣布完成但代码没合进来”的问题。
3. README、CONTRIBUTING、runtime docs、plan/status docs 是否仍能正确指导后续修复。

## 2. 审查基线与命令证据

### 2.1 仓库状态

```text
$ git status --short --branch
## rollout15-b5-internal-registry

$ git remote -v
origin  https://github.com/Facetomyself/reverse-deepagent.git (fetch)
origin  https://github.com/Facetomyself/reverse-deepagent.git (push)

$ git branch --show-current
rollout15-b5-internal-registry

$ git rev-parse origin/main HEAD
79925731cf827b4dc4c32fac67fddab70d5cb0a7
79925731cf827b4dc4c32fac67fddab70d5cb0a7
```

结论：当前工作区干净，当前分支 `rollout15-b5-internal-registry` 与 `origin/main` 指向同一提交 `79925731`。

### 2.2 验证命令

```text
$ /Users/mengma/reverse/reverse_agent/.venv/bin/python -m compileall -q src/reverse_deepagent tests
compileall_exit=0

$ /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest tests.test_runtime_registry tests.test_workspace_contract tests.test_browser_provider_registry tests.test_doctor -v
Ran 51 tests in 2.749s
OK

$ /Users/mengma/reverse/reverse_agent/.venv/bin/python -m unittest discover -s tests -v
Ran 1765 tests in 66.913s
OK (skipped=2)
```

测试层面没有红灯；下面的问题主要是合并事实、架构债和文档一致性问题。

## 3. 总体结论

### 3.1 可以确认的健康点

- `origin/main` 当前全量测试通过，说明现有主干在 Python 语法、核心 registry、workspace contract、BrowserProvider registry、doctor 和大部分 artifact/review workflow 上没有明显断裂。
- `RuntimeBackendRegistry` / `BrowserProviderRegistry` 的方向是对的：metadata listing 保持 side-effect-free，provider / runtime 通过 entry point 可插拔，legacy MCP 通过 optional package 和 shim 隔离。
- README 已经被收敛到 176 行，入口文档明显比之前健康。
- `coordinator.py` 已降到 1163 行，职责越界问题相比早期版本有实质缓解。
- internal-registry provider 的 `approve_internal_registry_delivery` 已从危险的 `bool(kwargs.get(...))` 转为字符串白名单解析：

```python
approve_internal_registry_delivery=str(kwargs.get("approve_internal_registry_delivery", "false")).lower() in ("true", "1", "yes")
```

这说明 `docs/status/2026-06-23-rollout-15-final-closure.md` 里列出的 “Security review：`bool(kwargs.get(...))` 需修复” 已经是过期遗留项。

### 3.2 需要重点修复的问题

| 编号 | 级别 | 类型 | 结论 |
| --- | --- | --- | --- |
| CR-1 | P0 | 合并事实错误 | `docs/status/2026-06-23-rollout-15-final-closure.md` 宣称 S5 已合并，但 `rollout15-source-dispatch-s5` 并不是 `HEAD` 祖先，S5 两个提交未进入 `origin/main`。 |
| CR-2 | P1 | 代码实际状态与收尾报告不一致 | `native_web.py` 当前仍是 11837 行，不是收尾报告宣称的 10679 行；`native_web_source_dispatch.py` 当前 1655 行，不是报告宣称的 2846 行。 |
| CR-3 | P1 | source dispatch 最终拆分未完成 | 当前 `native_web.py` 只接入 gateway A-D，没有 `dispatch_source_map_gateway_e`；S5 分支才包含 gateway E。 |
| CR-4 | P1 | 文档重复/半截合并 | `docs/runtime/browser-provider-architecture.md` 中 `## 5.2` 到 `## 5.9` 出现重复标题块，后半段是较旧、较短版本，容易覆盖读者认知。 |
| CR-5 | P2 | 流程文档与项目级规则冲突 | `开发者AI开发与PR提交流程.md` 仍大量写 `dev` / `origin/dev` / “PR 只能指向 dev”；虽然项目 AGENTS 说映射到 `main`，但文档本身仍会误导后续执行。 |
| CR-6 | P2 | CONTRIBUTING 旧 runtime 示例 | `CONTRIBUTING.md` 仍用 `--runtime mcp` 作为示例，和当前 “新命令用 `legacy-mcp`，`mcp` 只是 deprecated alias” 的口径冲突。 |
| CR-7 | P2 | 文档链接完整性 | `docs/reference/deepagents/*.md` 有 14 个本地图片链接不存在，虽然是 reference docs，但会影响文档可信度。 |
| CR-8 | P2 | 代码体量风险仍高 | `source_maps.py` 14313 行、`artifact_tools.py` 13468 行、`native_web.py` 11837 行、`tests/test_native_web_runtime.py` 13467 行，虽然测试绿，但后续合并冲突风险很高。 |

## 4. 详细发现

## CR-1：S5 分支未进入 main，但状态文档宣称已合并

### 级别

P0。

### 证据

```text
$ git merge-base --is-ancestor rollout15-source-dispatch-s5 HEAD && echo merged || echo not-merged
not-merged

$ git rev-list --left-right --count origin/main...rollout15-source-dispatch-s5
2    2

$ git log --oneline origin/main..rollout15-source-dispatch-s5
9efd7503 Fix S5 gateway_e browser session access
7c60410e Extract source dispatch S5 final application branches

$ git log --oneline rollout15-source-dispatch-s5..origin/main
79925731 Add rollout 15 final closure progress report
acbc4bae Fix internal registry provider: explicit field extraction instead of kwargs passthrough
```

`docs/status/2026-06-23-rollout-15-final-closure.md` 写道：

- S5：提取最后 7 个 explicit application 分支，✅ 316 tests。
- Fix：gateway_e matcher 排除集修复，✅ 13→0 failures。
- 全部已合并到 `main`。

但 Git 事实是：S5 分支有两个提交没有进入 `origin/main`，而 `origin/main` 有两个提交没有进入 S5 分支。

### 影响

这是当前最高优先级问题。后续修复如果基于“rollout 15 已完全合并”这个前提，会直接误判代码基线。尤其是 source dispatch 拆分是否完成、A-2 是否闭合、native_web.py 是否已经降到目标行数，这些结论目前都不成立。

### 建议修复

1. 不要继续在状态文档里称 S5 已合并。
2. 先在单独分支上把 `rollout15-source-dispatch-s5` 与 `origin/main` 重新合流，明确处理 `acbc4bae` internal-registry 修复和 S5 gateway E 的冲突。
3. 合流后至少跑：
   - `python -m compileall -q src/reverse_deepagent tests`
   - `python -m unittest tests.test_native_web_runtime tests.test_source_maps tests.test_breakpoint_manager -v`
   - `python -m unittest discover -s tests -v`
4. 合流成功后再更新收尾文档，不要先写胜利宣言。

## CR-2：收尾报告的代码指标与 main 不一致

### 级别

P1。

### 证据

当前 `origin/main` / `HEAD`：

```text
$ wc -l src/reverse_deepagent/adapters/native_web.py src/reverse_deepagent/adapters/native_web_source_dispatch.py
11837 src/reverse_deepagent/adapters/native_web.py
 1655 src/reverse_deepagent/adapters/native_web_source_dispatch.py
```

S5 分支：

```text
$ git show rollout15-source-dispatch-s5:src/reverse_deepagent/adapters/native_web.py | wc -l
10679

$ git show rollout15-source-dispatch-s5:src/reverse_deepagent/adapters/native_web_source_dispatch.py | wc -l
2846
```

收尾文档宣称：

- `native_web.py`：10679 行。
- `native_web_source_dispatch.py`：2846 行。
- `_dispatch_source` 最终 0 个内联分支，21 行纯网关调用。

这些数字属于 S5 分支，不属于当前 `origin/main`。

### 影响

文档把“分支上的目标状态”写成“主干事实状态”，会让后续 review / 修复 / PR 说明全部偏航。

### 建议修复

在合并 S5 前，改写 `docs/status/2026-06-23-rollout-15-final-closure.md`：

- 把 S5 状态改成 “分支验证通过，尚未合入 `main`”。
- 把主干指标和 S5 分支指标分开展示。
- 如果后续合并 S5，则在合并提交之后再补一条真实 closure 记录。

## CR-3：`_dispatch_source` 仍保留 explicit application 内联逻辑

### 级别

P1。

### 证据

当前 `native_web.py` 只 import / 调用 gateway A-D：

```python
from reverse_deepagent.adapters.native_web_source_dispatch import (
    dispatch_source_map_gateway_a,
    dispatch_source_map_gateway_b,
    dispatch_source_map_gateway_c,
    dispatch_source_map_gateway_d,
    dispatch_source_map_review_evidence,
)
```

当前 `_dispatch_source` 在调用 gateway D/A/C/B 之前仍保留大段 source-map debugger application 逻辑；S5 分支才新增：

```text
rollout15-source-dispatch-s5:src/reverse_deepagent/adapters/native_web.py:342:    dispatch_source_map_gateway_e,
rollout15-source-dispatch-s5:src/reverse_deepagent/adapters/native_web.py:2768:        result = dispatch_source_map_gateway_e(self, protection_name, context)
rollout15-source-dispatch-s5:src/reverse_deepagent/adapters/native_web_source_dispatch.py:1676:def dispatch_source_map_gateway_e(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
```

### 影响

架构方向没有错，但最终拆分没有落到主干。继续在当前 main 上开发 source dispatch，很容易和 S5 分支产生重复提取、冲突和行为漂移。

### 建议修复

优先把 S5 作为 “合并修复任务” 处理，而不是另开一个重复提取任务。合并时重点检查：

- gateway E 是否保留了 `acbc4bae` 的 internal-registry 安全修复。
- matcher 排除集修复是否真实覆盖之前 13 个失败。
- `_dispatch_source` gateway 调用顺序是否仍符合低副作用优先原则。
- S5 抽出去的方法是否没有把 `self` 隐式状态依赖弄丢。

## CR-4：`browser-provider-architecture.md` 出现重复章节

### 级别

P1。

### 证据

重复标题检查结果：

```text
DUP ## 5.2 Browser Runtime Subagent baseline [202, 290]
DUP ## 5.3 Debugger Subagent baseline [212, 300]
DUP ## 5.4 Hook Subagent baseline [220, 306]
DUP ## 5.5 Timeline Subagent baseline [226, 312]
DUP ## 5.6 Review Subagent baseline [232, 318]
DUP ## 5.7 Rebuild Subagent baseline [240, 324]
DUP ## 5.8 WorkspacePathResolver baseline [246, 330]
DUP ## 5.9 BrowserProvider plugin package template [268, 336]
```

前一组章节内容明显更新，包含更多近期 workflow / approval / artifact boundary；后一组章节是较旧、较短版本。

### 影响

这是典型合并/追加型文档坏味儿：两个版本都在，读者不知道哪个是准的。对 architecture doc 来说，这会直接影响后续开发对 subagent boundary、review-only tool、workspace migration boundary 的理解。

### 建议修复

1. 删除后半段重复旧章节，保留前半段较新的详细版本。
2. 重新整理 `5.x` 编号，因为当前 `5.10 ExternalDeliveryProvider plugin package template` 后又出现 `5.2`，结构已经乱了。
3. 修复后执行：
   - `git diff --check`
   - duplicate heading 脚本检查。

## CR-5：流程文档仍以 `dev` 为默认分支，和项目规则冲突

### 级别

P2。

### 证据

`开发者AI开发与PR提交流程.md` 中仍有大量 `dev` / `origin/dev` / “PR 只能指向 dev” 叙述，例如：

```text
阶段 2：先对齐最新 dev
 git rev-list --left-right --count origin/dev...HEAD
 git log --oneline HEAD..origin/dev
阶段 6：创建或更新 PR
 PR 只能指向 dev。
```

项目级 `AGENTS.md` 又声明：本仓库当前默认基线分支是 `main`，流程文档里的 `dev` 在本仓库默认映射为 `main`。

### 影响

虽然 AGENTS 做了兜底映射，但人和 Agent 读流程文档时仍容易执行错命令，特别是 PR、rebase、merge 阶段。这个问题不是代码 bug，但很容易制造合并事故。

### 建议修复

将该流程文档做本仓库适配：

- 明确当前仓库所有 `dev` 示例应替换为 `main` / `origin/main`。
- 保留一段说明：如果未来维护者显式改 base 分支，再按维护者指定。
- “PR 只能指向 dev” 改为 “本仓库默认 PR base 为 main”。

注意：该文件当前不是 BOM 文件；修改时保持 UTF-8 + LF。

## CR-6：CONTRIBUTING 仍推荐 `--runtime mcp`

### 级别

P2。

### 证据

`CONTRIBUTING.md` 的 Chrome debug lifecycle 示例：

```bash
reverse-agent-fixture-smoke   --profile context-navigator   --runtime mcp   --ensure-chrome   --chrome-debug-port 9461   --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```

当前长期口径是：

- 新命令使用 `--runtime legacy-mcp`。
- `mcp` / `jsreverser-mcp` 只是 deprecated compatibility alias。
- README Quick Start 推荐 `native-web`。

### 影响

这是小但烦人的方向性文档问题。CONTRIBUTING 是新人入口，继续写 `--runtime mcp` 等于把 deprecated alias 又教回去了。

### 建议修复

把示例改为：

```bash
reverse-agent-fixture-smoke   --profile context-navigator   --runtime legacy-mcp   --ensure-chrome   --chrome-debug-port 9461   --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```

并补一句：`mcp` / `jsreverser-mcp` 仅为兼容旧脚本的 deprecated aliases。

## CR-7：reference docs 存在坏图片链接

### 级别

P2。

### 证据

本地 Markdown 链接检查发现 14 个坏链接，集中在 `docs/reference/deepagents/*.md`，例如：

```text
docs/reference/deepagents/ch03-virtual-filesystem.md:33 ../public/imgs/07-infographic-six-tools.png
docs/reference/deepagents/ch01-agent-harness.md:91 ../public/imgs/01-framework-three-layer-architecture.png
docs/reference/deepagents/ch05-subagents.md:238 ../public/imgs/14-framework-multi-subagent.png
```

### 影响

这些是 reference docs，不一定影响核心 runtime，但会降低文档可信度。尤其本仓库现在已经严重依赖 docs 指导多 Agent 协作，坏链接会让 review 资料显得不可靠。

### 建议修复

二选一：

1. 补回 `docs/reference/public/imgs/` 或正确图片目录。
2. 如果这些 deepagents reference 是外部搬运残留，就在文档头部标明“外部参考，图片资源未纳入仓库”，并移除/改写坏链接。

## CR-8：大文件风险仍然偏高

### 级别

P2。

### 证据

当前大文件行数：

```text
14313 src/reverse_deepagent/browser/source_maps.py
13468 src/reverse_deepagent/tools/artifact_tools.py
11837 src/reverse_deepagent/adapters/native_web.py
13467 tests/test_native_web_runtime.py
 5705 tests/test_workspace_artifact_reader.py
```

### 影响

测试绿不代表长期可维护。现在的主要风险是：

- 多分支并行改同一个巨型文件时，冲突概率极高。
- review-only / executor / approval / journal / preflight 这类高度相似函数大量堆叠，后续很容易 copy-paste 出 policy 漏洞。
- 单个测试文件过大，失败定位慢，局部重构成本高。

### 建议修复

后续不要再往这些文件里直接堆新 workflow。建议按领域继续拆：

- `source_maps.py`：按 manager 族拆为 `source_maps/{lookup,consumer,debugger,hook,followthrough,terminal_review}.py`。
- `artifact_tools.py`：把 workspace foldered canonical migration、broader rollout、heap snapshot proof plan 等 review-only descriptor 分模块。
- `tests/test_native_web_runtime.py`：按 source dispatch gateway / artifact family / BrowserProvider runtime behavior 拆分。

## 5. 文档正确性专项结论

| 文档 | 结论 | 后续动作 |
| --- | --- | --- |
| `README.md` | 当前 176 行，主线清晰，整体可用。 | 暂无 P1 问题。 |
| `CONTRIBUTING.md` | 存在 deprecated `--runtime mcp` 示例。 | 改为 `legacy-mcp`，补 alias 说明。 |
| `docs/runtime/browser-provider-architecture.md` | 内容方向对，但重复章节严重。 | 删除旧重复块，重排 `5.x` 编号。 |
| `docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md` | 体量 3701 行，执行记录很多，但本次未发现直接错误。 | 后续建议拆 archive / current-state，避免 active plan 过长。 |
| `docs/status/2026-06-23-rollout-15-final-closure.md` | 与 Git 事实冲突。 | 必须修正 S5 合并状态和代码指标。 |
| `开发者AI开发与PR提交流程.md` | 与本仓库 `main` 基线冲突。 | 做本仓库适配，避免继续写 `origin/dev`。 |

## 6. 推荐修复顺序

### 第一批：先修合并事实，别继续盖楼

1. 新建修复分支，例如 `codex/review-fix-rollout15-s5-merge`。
2. 合并或 cherry-pick `rollout15-source-dispatch-s5` 的两个提交：
   - `7c60410e Extract source dispatch S5 final application branches`
   - `9efd7503 Fix S5 gateway_e browser session access`
3. 处理与 `acbc4bae` internal-registry 修复、`79925731` status doc 的冲突。
4. 跑全量测试。
5. 更新 rollout 15 收尾文档为真实状态。

### 第二批：修 active docs，不动代码行为

1. 清理 `docs/runtime/browser-provider-architecture.md` 重复章节。
2. 修 `CONTRIBUTING.md` deprecated runtime 示例。
3. 修 `开发者AI开发与PR提交流程.md` 中 `dev` / `origin/dev` / PR base 口径。
4. 跑 `git diff --check` 和 Markdown duplicate heading / local link 检查。

### 第三批：拆大文件，降低下一轮合并成本

1. 先拆测试文件，降低验证成本。
2. 再拆 `artifact_tools.py` 的 review-only descriptor 族。
3. 最后拆 `source_maps.py`，因为它涉及 manager / spec 类型多，风险最高。

## 7. 本次审查未发现的问题

- 未发现未解决 Git 冲突标记：`<<<<<<<` / `=======` / `>>>>>>>` 扫描为空。
- 未发现 tracked `__pycache__` / runtime artifacts 被提交。
- 全量测试通过，当前 main 没有立即阻断使用的测试级失败。
- legacy MCP 当前没有重新成为默认 Web runtime；主要问题是个别文档示例仍保留旧 alias。

## 8. 给后续修复 Agent 的注意事项

- 不要相信 `docs/status/2026-06-23-rollout-15-final-closure.md` 里关于 S5 已合并的描述，先看 Git DAG。
- 在合并 S5 前，不要继续手工重写 `_dispatch_source`，否则大概率重复劳动并制造冲突。
- 修文档时注意 `项目开发规范（AI协作）.md` 是 UTF-8 with BOM；本次建议修改的几个文件不是 BOM 文件。
- 本仓库默认 base 是 `main`，不要按流程文档旧示例去操作 `origin/dev`。
- 后续每个修复 PR 都要带上验证命令，不要只写“看起来修了”。

## 9. 审查结论

当前主干质量没有到“不能跑”的程度，测试也绿；但合并账和文档账必须先校正。最要命的是 S5 source dispatch 最终拆分并未进入 `origin/main`，而收尾文档已经宣布完成。这个问题不先处理，后面所有基于 rollout 15 closure 的修复计划都会带偏。

建议下一步直接做 `rollout15-source-dispatch-s5` 合流修复，然后再清理文档重复与 deprecated runtime 示例。

## 10. 修复跟进状态（2026-06-23）

本审核文档已被 `codex/review-fix-rollout15-s5-merge` 作为修复依据执行第一轮修复：

- 已 cherry-pick S5 两个真实提交 `7c60410e` / `9efd7503`，当前修复分支包含 `dispatch_source_map_gateway_e`，`native_web.py` 为 10679 行。
- 已修正 `docs/status/2026-06-23-rollout-15-final-closure.md`，明确原 `origin/main@79925731` 并未包含 S5，当前分支补齐后才满足 closure 口径。
- 已删除 `docs/runtime/browser-provider-architecture.md` 中重复的旧版 `5.2` 到 `5.9` 章节。
- 已将 `CONTRIBUTING.md` 的 legacy MCP 示例从 deprecated `--runtime mcp` 改为 `--runtime legacy-mcp`。
- 已将 `开发者AI开发与PR提交流程.md` 的本仓库基线口径统一为 `main` / `origin/main`。
- 已把 `docs/reference/deepagents/*.md` 中缺失的外部图片链接改为显式图示占位说明，避免保留坏链接。

后续如果本分支合入 `main`，CR-1 到 CR-7 可视为已处理；CR-8 大文件拆分仍是后续维护性任务。

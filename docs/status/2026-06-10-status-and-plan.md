# 项目状态与开发计划（2026-06-10）

> 本文档基于当前代码、测试和文档的实际状态生成，是 `2026-06-09-completion-and-docs-audit.md` 和 `2026-06-10-refactor-audit.md` 的综合后继文件。  
> 所有「完成度」结论以代码和测试为准，不以 ROADMAP 文字为准。

---

## 一、当前项目实际状态（快照）

### 1.1 测试状态

| 指标 | 数值 |
|---|---|
| 总测试数 | 1687 |
| 通过 | 1685 |
| Skip | 2 |
| **失败** | **0 ✅（P0 已修复，commit 7919f0e6）** |

**P0 回归已修复**：`_dispatch_paused()` 入口缺少 execution-class early-exit guard，导致 plan-class matcher 通过 context key 拦截 execution 请求返回 PARTIAL。修复后 1687 tests 全绿。

---

### 1.2 代码质量债

| 问题 | 位置 | 说明 |
|---|---|---|
| 7 个 backup 文件 | `src/reverse_deepagent/adapters/_*_backup.py` | 重构过程遗留，总计约 90K 行，占整个 src/ 约 36% |
| `apply_minimal_protection` 主方法体 156 分支 | `native_web.py` L531 | ~12203 行仍在主方法，B3a/B3b 仅抽出了约 25 个分支 |

---

### 1.3 文档与代码不对齐

ROADMAP `## Still not fully closed` 中下列条目**已有 MVP 实现**，需要移至 Done 区：

| ROADMAP 描述 | 实际实现 | 备注 |
|---|---|---|
| Heap retained-size proof executor | `HeapSnapshotRetainedSizeExecutorManager.execute()` + V8 真实解析 | estimate，`retained_size_proven=False` |
| Heap path-to-root proof executor | `HeapSnapshotPathToRootExecutorManager.execute()` | estimate，无完整 reachability proof |
| Heap constructor-growth drilldown | `HeapSnapshotConstructorGrowthDrilldownExecutorManager` | MVP |
| Automatic Source Map source-logpoint application | `SourceLogpointManager().install()` L3341 | explicit-review-only |

---

### 1.4 已完成能力概览（与实际代码对齐）

| 能力域 | 完成状态 |
|---|---|
| Native Web 运行时（BrowserProvider + collectors/hooks） | ✅ 基线完整 |
| BrowserProvider 抽象（Playwright / RemoteCDP / CloakBrowser / Browserless / Browserbase） | ✅ 基线完整，生产级 metadata + smoke |
| Legacy MCP split | ✅ 可选包 + alias 降级 |
| DeepAgents workspace contract | ✅ 基线 + foldered-canonical 迁移链 |
| Source Map workflow（lookup → executor review → logpoint/debugger/hook/rebuild MVP） | ✅ explicit-review-only MVP |
| Heap snapshot workflow（readiness → diff → retained-size / path-to-root / drilldown MVP） | ✅ explicit-review-only MVP（estimate，无 proof） |
| Paused session / cross-process continuation | ✅ 基线 + bounded one-iteration MVP |
| Delivery / lock / resume / external provider | ✅ 基线 |
| StrategyDetector plugin registry | ✅ 基线 + 外部模板包 |
| Android / iOS / mini-program | ⏸️ 有意延迟：只有 adapter interface 文档和 metadata probe |

---

## 二、开发计划（按优先级拆分为小目标）

### P0 — 修复回归（本次 commit 应先解决）

#### Goal-01：修复 8 个 failing paused_session 测试
- **什么**：所有测试期望 `status.value == "success"`，实际得到 `"partial"`
- **范围**：`src/reverse_deepagent/adapters/native_web.py` 的 `_dispatch_paused()` + 对应 Manager 类
- **验收**：`python -m unittest tests/test_native_web_runtime.py` 0 failures
- **工作量**：小（定位已清晰，调整状态判断逻辑或 FakeProvider 的 mock 返回值）

---

### P1 — 文档对齐（低风险，最高性价比）

#### Goal-02：更新 ROADMAP，把 heap/source-logpoint MVP 移入 Done 区
- **什么**：`ROADMAP.md` "Still not fully closed" → 移动 4 条已实现条目，加 `（MVP，estimate-only，无自动化）` 说明
- **范围**：`ROADMAP.md` 约 20 行改动
- **验收**：ROADMAP 中不再声称 heap retained-size / path-to-root / drilldown / source-logpoint 为未实现

#### Goal-03：清理 7 个 backup 文件
- **什么**：删除 `src/reverse_deepagent/adapters/_*_backup.py`（7 个文件，~90K 行）
- **范围**：只删除文件，不改任何 import
- **验收**：`rg --files src/ | grep backup` 为空；`python -m unittest discover -s tests -v` 全绿

#### Goal-04：在 AGENTS.md / README 中补充当前 8 个 failing test 是已知问题还是 bug
- **什么**：明确这 8 个测试是 B3b 引入的回归（非设计意图），避免后续 AI agent 把 `partial` 当正确行为
- **范围**：`AGENTS.md` 或新增 `docs/status/known-test-failures.md`

---

### P2 — 测试覆盖补齐

#### Goal-05：为 heap path-to-root executor 补测试（对齐 retained-size 水位）
- **什么**：当前只有 2 个测试，`retained-size` 有 5 个。新增 3 个：
  1. 多候选按 path_length 升序排列
  2. max_nodes 截断时 `node_analysis_truncated=True`
  3. `heap_snapshot=None` 时干净阻断
- **范围**：`tests/test_native_web_runtime.py`（新增约 60 行）
- **验收**：新测试全绿，总数 ≥ 1690

#### Goal-06：为 heap constructor-growth drilldown 补测试（同等覆盖）
- **什么**：同 Goal-05 逻辑，针对 `HeapSnapshotConstructorGrowthDrilldownExecutorManager`
- **范围**：`tests/test_native_web_runtime.py`

#### Goal-07：为 source-logpoint 补 FakeProvider 集成测试（参考 B3b 新增的 2 个）
- **什么**：B3b 新增了 bundle offset remap 和 provider unavailable 两个测试。补充：
  1. `names` 字段 remap 生效
  2. `sourcesContent` 摘要正确写入 artifact
- **范围**：`tests/test_native_web_runtime.py`

---

### P3 — 重构继续（中等工作量）

#### Goal-08：B3b 续：继续提取 `apply_minimal_protection` 中 page-free 分支
- **什么**：B3a 提取了 3 个 closure-prefix 分支，B3b 提取了 22 个 heap 分支。剩余 ~130 个 page-free 分支可继续机械提取（不依赖 `page` 变量）
- **策略**：每次提取一组语义上相关的分支（如 `source_logpoints` 系列、`federation` 系列），单次 commit
- **验收**：每次提取后全量测试全绿；`apply_minimal_protection` 主方法行数持续下降
- **参考节奏**：约 5–8 个 Goal，每个约 1–3 小时

#### Goal-09：B3c：处理 page-using 分支（需将 `page` 作为参数传入子方法）
- **什么**：依赖 L5984 `try` 块初始化的 `page` 变量的分支不能简单提取，需要在提取方法上加 `page` 参数
- **前提**：Goal-08 的 page-free 分支全部提取完毕
- **工作量**：中，需要仔细处理 page 初始化时机和 None guard

---

### P4 — 能力扩展（需求驱动，当前无硬性要求）

#### Goal-10：接入真实第三方 BrowserProvider（Browserless / Browserbase 生产配置）
- **什么**：现有包是 baseline + metadata；需要填充真实的 `start()` / `connect()` 实现并补 workspace smoke evidence
- **前提**：有对应服务账号/端点可测

#### Goal-11：Source Map 完整消费语义
- **什么**：raw source 文本导出、完整 binding/lexical scope 解析
- **当前边界**：intentionally unsupported，需求明确后再做

#### Goal-12：Heap 完整 proof executor（真实 retained-size proof / path-to-root proof）
- **什么**：当前只是 estimate；真正的 dominator-tree 遍历和完整 incoming-edge walk
- **当前边界**：intentionally unsupported，需求明确后再做

---

## 三、下一步行动（本轮建议执行顺序）

```
Goal-01  修复 8 个 failing 测试（~1h）
Goal-03  删除 7 个 backup 文件（~15min）
Goal-02  更新 ROADMAP 文档对齐（~30min）
Goal-04  记录已知问题（~15min）
Goal-05  heap path-to-root 测试补齐（~1h）
Goal-06  heap drilldown 测试补齐（~1h）
Goal-08  B3b 续：继续机械拆分 page-free 分支（迭代进行）
Goal-07  source-logpoint 测试补充（~1h）
Goal-09  B3c：page-using 分支提取（~3h，依赖 Goal-08）
```

---

## 四、已知问题与设计边界说明

### P0 根因（已修复，commit `7919f0e6`）

`_dispatch_paused` 中的 plan-class matcher（如 `_is_paused_session_cross_process_execution_plan_request`）会通过 context key 检测请求类型。execution-class 测试（如 attach probe、one-action、multi-step loop）将 plan 数据作为输入传入 context，导致被 plan matcher 提前拦截，返回 `ExecutionStatus.PARTIAL` 而非 `SUCCESS`。

修复方式：在 `_dispatch_paused` 入口处加 8 个 execution-class early-exit guard + 2 个交叉排除规则（见 `src/reverse_deepagent/adapters/native_web.py` line 9713-9730）。

**重要**：`partial` 作为 `ExecutionStatus` 的值表示"未达到执行预期"，绝不是这类 execution 请求的正确结果。如果看到 paused_session execution 类请求返回 `partial`，应优先检查 `_dispatch_paused` 的 guard 是否覆盖了新增的 execution matcher。

---

## 五、文档维护规则（对齐 2026-06-09 audit 结论）

1. 新增 explicit-review-only executor → ROADMAP 写 `Done（MVP，estimate-only）`，不写 `proof` / `automatic`
2. 重构 commit → 必须附带全量测试截图或 `Ran N tests in Xs, OK`
3. "Still not fully closed" 只列**尚无代码**的项，有代码但有边界的列 `Done（MVP，有意约束）`
4. backup 文件不进 main 分支；重构脚本进 `scripts/`

---

*生成时间：2026-06-10*  
*测试快照（P0修复后）：1687 total, 1685 pass, 0 fail, 2 skip*  
*当前 branch：refactor/consolidate-hooks-native-web（HEAD: 7919f0e6）*

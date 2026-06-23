# 项目状态与开发计划（2026-06-10）

> 本文档基于当前代码、测试和文档的实际状态生成，是 `2026-06-09-completion-and-docs-audit.md` 和 `2026-06-10-refactor-audit.md` 的综合后继文件。
> 所有「完成度」结论以代码和测试为准，不以 ROADMAP 文字为准。

---

## 一、当前项目实际状态（快照）

### 1.1 测试状态

| 指标 | 数值 |
|---|---|
| 总测试数 | 1697 |
| 通过 | 1695 |
| Skip | 2 |
| **失败** | **0 ✅** |

**P0 回归已修复**（commit `7919f0e6`）：`_dispatch_paused()` 入口缺少 execution-class early-exit guard，导致 plan-class matcher 通过 context key 拦截 execution 请求返回 PARTIAL。修复后全绿。

Goal-05/06（commit `d4d096c`）新增 6 个 heap 测试（1693），Goal-07（commit `2a7cb8f`）新增 2 个 source-logpoint 测试（1695）。

---

### 1.2 代码质量债

| 问题 | 位置 | 说明 |
|---|---|---|
| backup 文件 | `src/reverse_deepagent/browser/hooks/module_hooks_pkg/_original_backup.py` 等临时备份 | Goal-03 已清理 7/7 个备份文件，当前无已知 backup 残留 |
| `apply_minimal_protection` 主方法体 ~130 分支 | `native_web.py` L531 | B3a/B3b/Goal-08 已抽出约 26 个分支（closure-prefix 3 + heap 22 + object_graph 1），主方法仍有约 130 分支 |

---

### 1.3 文档与代码对齐状态

✅ **已对齐**（commit `86a11ade`）：ROADMAP `## Still not fully closed` 中的 heap / source-logpoint 条目已移入 Done 区，加注 `（MVP，estimate-only，无自动化）`。当前 ROADMAP 与代码无已知落差。

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

### P0 — 修复回归 ✅ 全部完成

#### ~~Goal-01：修复 8 个 failing paused_session 测试~~ ✅ commit `7919f0e6`
`_dispatch_paused()` 入口加 8 个 execution-class early-exit guard + 2 个交叉排除规则，全部 passing。

---

### P1 — 文档对齐 ✅ 全部完成

#### ~~Goal-02：更新 ROADMAP，把 heap/source-logpoint MVP 移入 Done 区~~ ✅ commit `86a11ade`
heap retained-size / path-to-root / drilldown / source-logpoint 均已移入 Done 区，标注 `（MVP，estimate-only）`。

#### ~~Goal-03：清理 7 个 backup 文件~~ ✅ 7/7 已清除
6 个 `src/reverse_deepagent/adapters/_*_backup.py` 与 1 个 `src/reverse_deepagent/browser/hooks/module_hooks_pkg/_original_backup.py` 均已删除；当前无已知 backup 残留。

#### ~~Goal-04：记录已知问题与 _dispatch_paused guard 契约~~ ✅ commit `808ac961`
P0 根因已记录在 `docs/status/2026-06-10-status-and-plan.md` 第四节，并同步到 `2026-06-10-status-and-plan.md` Known Issues 区。

---

### P2 — 测试覆盖补齐 ✅ 全部完成

#### ~~Goal-05：为 heap path-to-root executor 补测试~~ ✅ commit `d4d096c`
新增 3 个测试：多候选 path_length 升序排列、max_depth 截断、`heap_snapshot=None` 阻断。

#### ~~Goal-06：为 heap constructor-growth drilldown 补测试~~ ✅ commit `d4d096c`
新增 3 个测试：constructor-growth rows 降序排列、side-effects 标注准确、`None` drilldown 阻断。

#### ~~Goal-07：为 source-logpoint 补 FakeProvider 集成测试~~ ✅ commit `2a7cb8f`
新增 2 个测试：`names` 字段 remap 生效、`sourcesContent` 摘要写入 artifact。

---

### P3 — 重构继续（中等工作量）

#### ~~Goal-08（首步）：提取 `_dispatch_object_graph`~~ ✅ commit `a30ba3f`
`object_graph_diff` page-free 分支（63 行）提取到 `_dispatch_object_graph()`，全量测试 1695/2 skip 全绿。

#### Goal-08（续）：继续提取 `apply_minimal_protection` 中 page-free 分支
- **什么**：已抽出 closure-prefix（3）+ heap（22）+ object_graph（1），剩余约 130 个 page-free 分支可继续机械提取
- **策略**：每次提取一组语义相关分支（如 `source_logpoints` 系列、`federation` 系列），单次 commit
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

## 三、下一步行动

### ✅ 本轮已全部完成（P0–P3 首步）

```
✅ Goal-01  修复 8 个 failing 测试（commit 7919f0e6）
✅ Goal-03  删除 7/7 backup 文件（当前无已知 backup 残留）
✅ Goal-02  更新 ROADMAP 文档对齐（commit 86a11ade）
✅ Goal-04  记录已知问题与 _dispatch_paused guard 契约（commit 808ac961）
✅ Goal-05  heap path-to-root 测试补齐（commit d4d096c）
✅ Goal-06  heap drilldown 测试补齐（commit d4d096c）
✅ Goal-07  source-logpoint 测试补充（commit 2a7cb8f）
✅ Goal-08  _dispatch_object_graph 提取（commit a30ba3f）
```

### 待处理项

```
Goal-08 续    继续提取 apply_minimal_protection page-free 分支群（迭代进行）
Goal-09       B3c：page-using 分支提取（依赖 Goal-08 页面无依赖分支全部完成）
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

*生成时间：2026-06-10（最后更新：2026-06-11）*
*测试快照（HEAD 808ac961）：1697 total, 1695 pass, 0 fail, 2 skip*
*当前 branch：refactor/consolidate-hooks-native-web（HEAD: 808ac961）*

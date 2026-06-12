# 2026-06-10 重构审计与完成度核实

本文档记录 `refactor/consolidate-hooks-native-web` 分支上的三次整固 commit（B1/B2/B3a）以及 Direction A 测试补充的客观状态。

## 整固结果（B1/B2/B3a）

| Task | Commit | 变更内容 | 验证方式 |
|---|---|---|---|
| B1 | `8e2b8f3` | `module_hooks.py`(12449行) → `module_hooks/` 域包（base/module_io/async_chunk/federation/custom_loader + shim） | 138 符号字节级比对通过；1682 测试全绿 |
| B2 | `c1587bc` | 160 个 `_is_*_request` staticmethod → `_NativeWebRequestMatchers` mixin；`native_web.py` 19519→14706行 | MRO 验证；1682 测试全绿 |
| B3a | `730f884` | 3 个 page-free closure 前缀分支 → `_dispatch_closure_prefix`；`apply_minimal_protection` 首段提取 | 1682 测试全绿 |
| B3b | `b36f168` | 22 个 heap 分支 → `_dispatch_heap`；`apply_minimal_protection` 中段提取 | 1685 测试全绿 |
| Goal-08 | `a30ba3f` | `object_graph_diff` page-free 分支（63 行）→ `_dispatch_object_graph` | 1695 测试全绿 |

### B3b / Goal-08 已完成；B3c 待处理

> 2026-06-12 rollout4 update: B3c 已继续推进，`apply_minimal_protection` 又抽出了 `_dispatch_paused_session(...)` 与 `_dispatch_closure_runtime(...)` 两个 page-using 分支组。主方法从约 4777 行降到 3296 行，剩余 `protection_name` 分支从 70 个降到 47 个；module federation、custom-loader、async chunk、module hook / breakpoint 等分支组仍待后续批次继续拆。
>
> 2026-06-12 rollout7 update: B3c branch extraction 已收口，后续 rollout 又抽出了 `_dispatch_module_federation(...)`、`_dispatch_custom_loader(...)`、`_dispatch_async_chunk(...)`、`_dispatch_module_tail(...)`、`_dispatch_observation_review(...)` 与 `_dispatch_recursive_continuation_readiness(...)`。`apply_minimal_protection` 当前降到 85 行 / 0 个直接 request branch predicate；final fallback hook install / snapshot 仍有意保留在主方法，等待独立 fallback dispatch contract 评审。

B3b（commit `b36f168`）：22 个 heap 分支提取到 `_dispatch_heap()`，`apply_minimal_protection` 完成中段解耦。

Goal-08（commit `a30ba3f`）：`object_graph_diff` page-free 分支（63 行）提取到 `_dispatch_object_graph()`，在 try/session/page 块之前委托执行。

`apply_minimal_protection` 的 direct request branch extraction 当前已完成。后续剩余 refactor 已从 B3c 分支搬移转为两个独立方向：
- **fallback contract**：final fallback hook install / snapshot 仍保留在主方法，移动前必须先评审独立 contract。
- **source dispatch decomposition**：`_dispatch_source(...)` 仍是最大 helper，应单独规划拆分。
- **审计项 triage**：`docs/status/2026-06-12-readonly-code-audit.md` 是后续安全/质量修复输入，不属于 B3c 行为改动。

## Direction A：已实现能力的实际完成度核实

### 核实结论：ROADMAP "Still not fully closed" 多项描述已过时

审计了以下 ROADMAP 中标注为未完成的项目，实际均已有完整实现：

| ROADMAP 标注为未完成 | 实际状态 | 实现位置 |
|---|---|---|
| Heap retained-size proof executor | **已实现（MVPestimate）** | `HeapSnapshotRetainedSizeExecutorManager.execute()` + `_analyze_heap_snapshot()` (V8格式真实解析) |
| Heap path-to-root proof executor | **已实现（MVP estimate）** | `HeapSnapshotPathToRootExecutorManager.execute()` + `_analyze_heap_snapshot_for_paths()` |
| Heap constructor drilldown proof executor | **已实现（MVP）** | `HeapSnapshotConstructorGrowthDrilldownExecutorManager` |
| Automatic Source Map source-logpoint application | **已实现（explicit-review-only）** | `native_web.py` L3341 `SourceLogpointManager().install(page, spec)` |
| Source-logpoint log_expression 未接入 CDP | **已实现** | `_condition_expression()` L166 evaluate `log_expression` |

### 重要语义澄清

ROADMAP 的"未完成"描述准确地指代的是**自动化/无审查执行**，而非"代码不存在"：
- Heap executor 存在，但明确标注 `retained_size_proven=False`，只是 estimate
- Source-logpoint 存在，但需要 `approve_source_logpoint_install=True` 显式审批
- 这些边界是**有意为之的设计约束**，不是遗漏

## Direction A 新增测试（commit `005f724`）

在 `HeapSnapshotRetainedSizeExecutorManagerTests` 类新增 3 个测试：

| 测试名 | 验证内容 |
|---|---|
| `test_heap_snapshot_retained_size_executor_ranks_candidates_by_retained_size_desc` | 多候选时按 retained_size_estimate 降序排列 |
| `test_heap_snapshot_retained_size_executor_truncates_at_max_nodes` | max_nodes 截断后 node_analysis_truncated=True，且候选来自截断后可见范围 |
| `test_heap_snapshot_retained_size_executor_blocks_on_missing_heap_snapshot` | heap_snapshot=None 时干净阻断，无副作用 |

全量测试：1693 通过 / 2 skip / 退出码 0（Goal-08 后为 1695/1693）。

## 下一步建议

按价值/风险比排序：

1. ~~**B3b**~~：✅ 已完成（commit `b36f168`）
2. ~~**完善 ROADMAP**~~：✅ 已完成（commit `b36f168` / `86a11ade`）；heap/source-logpoint executor 已移入 Done 区
3. ~~**Direction A 深化**~~：✅ 已完成（heap path-to-root +3 tests，constructor-growth +3 tests，source-logpoint names-remap +2 tests，共 commit `d4d096c` + `2a7cb8f`）
4. ~~**B3c**~~：✅ 已完成至 `apply_minimal_protection` direct request branch predicate 清零；后续改为独立 fallback dispatch contract 评审与 `_dispatch_source(...)` 拆分规划。

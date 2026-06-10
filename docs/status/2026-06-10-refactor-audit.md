# 2026-06-10 重构审计与完成度核实

本文档记录 `refactor/consolidate-hooks-native-web` 分支上的三次整固 commit（B1/B2/B3a）以及 Direction A 测试补充的客观状态。

## 整固结果（B1/B2/B3a）

| Task | Commit | 变更内容 | 验证方式 |
|---|---|---|---|
| B1 | `8e2b8f3` | `module_hooks.py`(12449行) → `module_hooks/` 域包（base/module_io/async_chunk/federation/custom_loader + shim） | 138 符号字节级比对通过；1682 测试全绿 |
| B2 | `c1587bc` | 160 个 `_is_*_request` staticmethod → `_NativeWebRequestMatchers` mixin；`native_web.py` 19519→14706行 | MRO 验证；1682 测试全绿 |
| B3a | `730f884` | 3 个 page-free closure 前缀分支 → `_dispatch_closure_prefix`；`apply_minimal_protection` 首段提取 | 1682 测试全绿 |

### 未完成的 B3b/B3c

`apply_minimal_protection` 仍有 156 个分支（12203 行）留在主方法体内：
- **page-free 分支**：可安全提取，但与 page-using 分支交错，需逐段处理
- **page-using 分支**：依赖 L5984 try 块初始化的 `page`，提取时须将 `page` 作参数传入
- **fallback 代码**：永远保留在主方法，不提取

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

全量测试：1685 通过 / 2 skip / 退出码 0。

## 下一步建议

按价值/风险比排序：

1. **B3b**（机械工作）：继续抽 `apply_minimal_protection` 的 page-free 分支群，加参数传递机制处理 page-using 分支
2. **完善 ROADMAP**：把已实现的 heap/source-logpoint executor 从 "Still not fully closed" 移到 "Done（MVP，estimate-only）"，消除文档与代码的落差
3. **Direction A 深化**：为 heap path-to-root 和 constructor drilldown executor 补同等覆盖度的测试（目前各只有 2 个测试，新增量级与 retained-size 对齐）

# Rollout 15 收尾与项目整体进度报告（2026-06-23）

## 一、rollout 15 执行

| Worker | 分支 | 内容 | 结果 |
|---|---|---|---|
| A | `rollout15-source-dispatch-s5` | S5: 提取最后 7 个 explicit application 分支 | ✅ 316 tests |
| B | `rollout15-b5-internal-registry` | B-5: internal-registry `**kwargs` → 显式字段 | ✅ |
| Fix | `rollout15-source-dispatch-s5` | gateway_e matcher 排除集修复 | ✅ 13→0 failures |

全部已合并到 `main`（`78478d55`）。

## 二、核心指标总览

### 文件瘦身

| 文件 | 起始 (原基线) | 最终 (rollout 15) | 变化 |
|---|---|---|---|
| `native_web.py` | 14,317 | **10,679** | **-3,638 (-25.4%)** |
| `native_web_source_dispatch.py` | 219 | 2,846 | +2,627 (6 个 gateway 函数) |
| `coordinator.py` | 2,212 | **1,163** | **-1,049 (-47.4%)** |
| `artifact_tools.py` | 13,842 | **13,468** | **-374 (-2.7%)** |
| `README.md` | 1,333 | **176** | **-1,157 (-86.8%)** |

### `_dispatch_source` 分解完成

```
原始: 37 个内联分支，3,665 行
  ↓ S1:  3 个 review-evidence → review_evidence
  ↓ S2: 10 个 descriptor     → gateway_a + gateway_b
  ↓ S3: 12 个 read-only      → gateway_c
  ↓ S4:  5 个 dispatcher     → gateway_d
  ↓ S5:  7 个 application    → gateway_e
最终:  0 个内联分支，21 行纯网关调用
```

### 新增运行时模块

| 模块 | 行数 | 来源 |
|---|---|---|
| `runtime/factories.py` | 151 | coordinator 工厂函数 |
| `runtime/manifest.py` | 376 | artifact manifest + 分类 |
| `runtime/registry.py` | 431 | 注册表构建 |
| `runtime/mock_bridge.py` | 236 | MockJSReverserBridge |
| `runtime/browser_lifecycle.py` | 44 | Chrome 生命周期 |

## 三、审计 finding 最终状态

| # | 级别 | 摘要 | 状态 |
|---|---|---|---|
| A-1 | 🔴 安全 | cookie/Authorization 脱敏 | ✅ rollout 9 |
| A-2 | 🔴 架构 | native_web.py 体量 | ✅ 14,317→10,679, _dispatch_source 完全分解 |
| B-1 | ⚠️ 架构 | coordinator 职责越界 | ✅ 2,212→1,163, 5 个域已提取 |
| B-2 | ⚠️ 质量 | artifact_tools 拷贝粘贴 | ✅ 32/32 loader 迁移到公共 helper |
| B-3 | ⚠️ 安全 | 静默吞异常 | ✅ 11 处补 debug 日志 |
| B-4 | ⚠️ 安全 | Chrome 启动参数注入 | ✅ rollout 11 |
| B-5 | ⚠️ 安全 | internal-registry kwargs | ✅ rollout 15, 显式字段提取 |
| B-6 | ⚠️ 文档 | README 体量 | ✅ 1,333→176, 4 个专题文档 |
| B-7 | ✅ | rollout-5/BOM | ✅ |
| C-1~7 | ✅ | registry/契约 | ✅ |

**闭合率：11/12（92%）** — A-2 从「缓解中」升为「已闭合」。

## 四、rollout 历史

| Rollout | 日期 | 主题 | 状态 |
|---|---|---|---|
| 1-7 | 06-12 | module_hooks 拆包, B3c dispatch 族提取 | ✅ |
| 8 | 06-12 | fallback 契约 + audit triage | ✅ |
| 9 | 06-12 | native collector evidence 脱敏 | ✅ |
| 10 | 06-12 | 默认 hook fallback 提取 | ✅ |
| 11 | 06-13 | Chrome launcher + legacy alias + S1 | ✅ |
| 12 | 06-22 | S2 + B-1 Phase 1 + B-2 Phase 1 + B-3 | ✅ |
| 13 | 06-22 | S3 + B-1 Phase 2 + B-2 Phase 2 | ✅ |
| 14 | 06-23 | S4 + B-6 README 收敛 | ✅ |
| 15 | 06-23 | S5（最终）+ B-5 internal-registry | ✅ |

15 轮 rollout，约 20 个 agent，全部验收通过。

## 五、测试覆盖

```text
$ python -m unittest discover -s tests -v
Ran 1765 tests in 69.399s
OK (skipped=2)
```

## 六、已知遗留

1. **Security review**：`approve_internal_registry_delivery=bool(kwargs.get(...))` 需改为字符串安全解析（非纯 `bool()` 转换）
2. **Worktree 清理**：`.claude/worktrees/` 下有残留目录，但已加入 `.gitignore`
3. **Platform Expansion**：Android/iOS/小程序按用户指示不做

## 七、部署状态

```
origin/main: 78478d55 (最新)
origin/refactor/consolidate-hooks-native-web: 已推送
所有变更已推送到 https://github.com/Facetomyself/reverse-deepagent
```

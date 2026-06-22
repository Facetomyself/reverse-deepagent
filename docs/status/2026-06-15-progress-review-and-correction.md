# 项目进度复盘与 Code Review 纠偏报告（2026-06-15）

## 复盘元信息

- **基线**：分支 `refactor/consolidate-hooks-native-web`，HEAD `5d0b70bf`（rollout 11 已合并 PR #45/#46/#47）。
- **工作区状态**：存在未提交改动 `ROADMAP.md`、`docs/status/2026-06-13-multi-agent-rollout-11.md`；untracked 文件 `docs/status/2026-06-12-readonly-code-audit.md`。
- **方法**：以 `docs/status/2026-06-12-readonly-code-audit.md`（基线 `ed311086`）与 `docs/status/2026-06-12-code-audit-triage.md` 为对照表，逐条回源实证 finding 在当前 HEAD 的真实状态。
- **验证缺口（重要）**：本次环境下 `unittest` / `compileall` 测试运行被 auto-mode 一致拦截，**未能本地复跑** `tests` 全量与定向用例。下文所有结论基于静态阅读、`rg`、行数统计与 git 历史，不含运行时验证。

---

## 一、Rollout 进度盘点

| Rollout | 主题 | 文档状态 | 实证结论 |
|---|---|---|---|
| 1–4 | module_hooks 拆包 / `_is_*` matcher 提取 / B3c dispatch 族提取 | completed | 文档闭合 |
| 5 | Module Federation / custom-loader dispatch 提取 | completed | `_dispatch_module_federation` / `_dispatch_custom_loader` 已在码内，已闭合 |
| 6–7 | async-chunk / module-tail / observation-review / recursive-readiness dispatch | completed | 闭合 |
| 8 | fallback 契约文档化 + source-dispatch 分解计划 + 审计 triage | completed | 闭合 |
| 9 | native collector evidence 脱敏（P0） | completed | ✅ 已落地（见 A-1） |
| 10 | 默认 hook fallback 提取 `_dispatch_default_hook_fallback` | completed | 闭合 |
| 11 | Chrome launcher 加固 + 旧 alias 文档清理 + Source Dispatch S1 | **completed（标记）** | ⚠️ 见纠偏-1：最终验证节仍是占位符 |

整体：rollout 1–11 主线连续闭合，多 agent 分发 + 主线 review/merge 的协作模型运转正常。**唯一例外是 rollout 11 收尾文档存在内部矛盾。**

---

## 二、审计 finding 当前实证状态（对照 readonly-audit）

> 基线行数取自审计报告（HEAD `ed311086`），现状行数为本次实测（HEAD `5d0b70bf`）。

| 编号 | 级别 | 摘要 | 当前状态 | 实证 |
|---|---|---|---|---|
| **A-1** | 🔴 高·安全 | 原始 cookie / Authorization 进 evidence，未脱敏 | ✅ **已修复** | `collectors/storage.py` 复用 `redact_cookie_header`/`redact_mapping`，`collectors/network.py` 复用 `redact_mapping`；脱敏统一收敛进 `browser/redaction.py`（rollout 9 闭合） |
| **A-2** | 🔴 高·架构+质量 | `native_web.py` 单文件巨兽 | 🟡 **部分缓解，仍未达标** | 14446 → **14317 行**（仅降 129）；`_dispatch_source` 3853 → **约 3666 行**。S1 只抽走 3 个只读分类谓词，主体仍在 |
| **B-1** | ⚠️ 中·架构 | `coordinator.py` 职责越界 | ❌ **未处理** | 仍 **2212 行**，Chrome 生命周期 / legacy-MCP 感知 / `MockJSReverserBridge` / 工厂 / manifest 仍内嵌 |
| **B-2** | ⚠️ 中·质量 | `artifact_tools.py` journal loader 拷贝粘贴 | ❌ **未处理** | 仍 **13842 行**，`_load_or_read_workspace_foldered_canonical_migration_*` 同构函数 ≥10 个，未抽 `_load_journal` |
| **B-3** | ⚠️ 中·质量+安全 | 静默吞异常掩盖数据空洞 | 🟡 **未处理** | 点名的 `page_mutation.py:6561` 仍是裸 `except Exception: pass`；该文件裸异常仍 **11 处** |
| **B-4** | ⚠️ 中·安全 | Chrome 启动参数注入面 | ✅ **已修复** | `start_chrome_debug.sh` 已加 `DEBUG_PORT`(1..65535)/`WAIT_SECONDS` 校验 + `read -r -a`（rollout 11 闭合） |
| **B-5** | ⚠️ 中·安全 | internal-registry 工厂 `**kwargs` 直透 | ❌ **未处理** | `create_internal_registry_external_delivery_provider(**kwargs)` 仍直透，未对齐 s3/gitlab 的显式字段提取 |
| **B-6** | ⚠️ 中·文档 | README 旧 alias 示例 + 体量超标 | 🟡 **部分缓解** | active docs（`docs/runtime/*`）已澄清 `mcp`/`jsreverser-mcp` 为 deprecated alias（rollout 11）；README 本体仍 ~205KB、多 H1，未拆分 |
| **B-7** | ⚠️ 低·文档 | rollout-5 状态节未闭合 / 规范 BOM | ✅ **已闭合 / 确认** | rollout-5 现为 `Status: completed`；规范 BOM 为有意保留，非缺陷 |
| C-1~C-7 | ✅ | registry / provider 契约 / 凭证隔离 / .env / entrypoint / 测试 | ✅ 维持合规 | 无回归迹象 |

**小结**：两条最高优先级里，安全项 A-1 已闭合（实质风险消除）；架构项 A-2 仅微量缓解。中优先级 B-4 已修，B-1/B-2/B-5/B-3 仍是存量技术债，且都属"结构性 / 一致性"问题而非运行时硬错误。

---

## 三、本次新增纠偏发现

### 纠偏-1 🔴 rollout-11 文档 `completed` 与最终验证占位符矛盾
- **位置**：`docs/status/2026-06-13-multi-agent-rollout-11.md`（未提交改动）。
- **现象**：头部 `Status:` 已由 `dispatching` 改为 `completed`，且补全了 Worker B/C result；但「Final rollout validation」节正文仍为
  `Observed result to be recorded by the main agent after the final validation run.`——占位符未替换为真实结果。
- **判断**：标记"已完成"但缺最终验证证据，违反"可验证高于看起来差不多"。属典型"已完成未记录"误标风险。
- **纠偏建议**：在 `refactor/consolidate-hooks-native-web` 上实跑该节三条命令（`git diff --check` + `compileall` + `unittest discover`），把真实结果填回占位符后再 commit；若不跑，则 `Status` 应降级标注"验证待补"。

### 纠偏-2 🟠 readonly-audit 文档 untracked，与 checklist 约定冲突
- **位置**：`docs/status/2026-06-12-readonly-code-audit.md`（untracked，未在 `.gitignore`）。
- **现象**：rollout-11 checklist 第 6 条与 triage 文档均明确要求该报告保持 **local-only、不提交**；但它当前裸露在 untracked 状态，`git add -A` / `git commit -a` 极易误纳入。
- **纠偏建议（二选一，需决策）**：
  1. **正式纳入**：去掉"local-only"约定，将其作为正式审计存档提交（与本报告同目录）；或
  2. **保持隔离**：在 `.gitignore` 增加该路径，杜绝误提交。
  （本报告不擅自删除或提交用户文件。）

### 纠偏-3 🟡 未提交改动尚未落盘
- **位置**：`ROADMAP.md` + `rollout-11.md`。
- **现象**：rollout 11 的 ROADMAP note 与 Worker result 已写好但未 commit，与已合并的代码 PR 形成"代码已合、文档未提交"的时间窗。
- **纠偏建议**：连同纠偏-1 的验证结果一并 commit，保持文档与代码合并状态同步。

---

## 四、结构性技术债处置优先级（建议下一轮 rollout）

承接 triage 的排序，结合本次实证：

1. **P0 收尾（本轮即可做）**：补 rollout-11 最终验证 + 处理 readonly-audit 归属 + commit（纠偏 1/2/3）。
2. **P1 `_dispatch_source(...)` S2–S7**：继续按 review-gated 窄 PR 分解，每个 PR 限分支数、带 golden-shape 测试，禁止与行为变更混合。目标把 native_web.py 真正降到 ≤2000 行 / 单函数 ≤150 行。
3. **P1 B-1 coordinator 瘦身**：Chrome 生命周期下沉 runtime；legacy-MCP 收敛进 `runtime/legacy_mcp.py`；`MockJSReverserBridge` 迁 fixtures。
4. **P2 B-2 / B-5 / B-3**：抽 `_load_journal` 统一 journal loader；internal-registry 工厂改显式字段提取；裸 `except Exception: pass` 补 `logger.debug(..., exc_info=True)` 或 `# noqa` + 意图注释。
5. **P2 B-6**：README 收敛为入口+索引，能力矩阵 / legacy MCP 指南迁 `docs/runtime/`。

---

## 五、本报告边界

- 所有结论以 HEAD `5d0b70bf` 为准；后续提交需以新基线复核行号与文件状态。
- **未运行测试**：`unittest discover` / `compileall` 在本次环境被 auto-mode 拦截，未本地复跑。A-1 脱敏、B-4 脚本加固的"已修复"结论基于代码链路静态确认，未做运行时落盘验证。
- 行数 / 谓词位置经 `rg` 与 `wc -l` 实测；架构债结论为静态阅读判断，不含动态调用追踪。

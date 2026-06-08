# reverse-deepagent 项目级 AGENTS 强制规则

## 0. 适用范围与优先级

- 本文件适用于 `/Users/mengma/reverse/reverse_agent` 整个仓库及其所有子目录。
- 每次 AI 在本仓库执行开发、修复、重构、文档、测试、提交、推送或 PR 相关任务时，都必须先遵守本文件。
- 必须读取并遵循：
  - [`开发者AI开发与PR提交流程.md`](./开发者AI开发与PR提交流程.md)
  - [`项目开发规范（AI协作）.md`](./项目开发规范（AI协作）.md)
  - 与当前任务直接相关的仓库文档（至少包括 `README.md`、`CONTRIBUTING.md`、`docs/runtime/browser-provider-architecture.md`、`docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`；涉及 legacy MCP 时再补读 `docs/runtime/jsreverser-mcp-setup.md`、`docs/ci/self-hosted-mcp-smoke.md`、`docs/design/reverse-deepagent-architecture.md`）
- `开发者AI开发与PR提交流程.md` 作为 GitHub / PR / 合并动作流程基线直接使用；但本仓库当前默认基线分支是 `main`，其中提到的 `dev` 在本仓库默认映射为 `main`，除非维护者明确指定其他分支。
- `项目开发规范（AI协作）.md` 已做本仓库适配；其中原本面向别的 JS 项目所写的结构示例只保留为通用方法论，不能覆盖本仓库 Python / DeepAgents 架构规则。
- 如果流程文档、README、历史计划或旧对话口径冲突，以当前仓库真实代码、当前 `AGENTS.md`、用户本轮明确要求为准；不能靠记忆或猜测。

## 1. 任务开场白规则

- 仅在用户下达明确任务、要求产出或执行动作时触发。
- 任何命令或工具调用前，必须先用一段中文说明“我理解的任务”和“接下来怎么做”。
- 开场白后立刻执行，不等待用户确认，除非存在无法合理推断且会造成破坏性后果的关键问题。
- 闲聊、问候、情绪交流不触发。

## 2. 语言、编码与换行

- 默认语言：中文。
- 技术术语保留英文，中文与半角英数字之间保留半角空格。
- 新增文本文件默认 UTF-8 + LF。
- 修改已有文件时优先保持原有换行风格。
- 若原文件是 UTF-8 with BOM，必须保持 BOM；例如 `项目开发规范（AI协作）.md` 当前就是 UTF-8 with BOM + LF。
- Shell 路径必须显式确认，包含空格、中文或特殊字符时必须加引号。
- Python / Node 写文件必须显式指定编码。
- 出现乱码、异常解析错误、`Unterminated string constant` 时，优先检查编码和换行。

## 3. 每次开发前的强制检查

开始任何代码或文档改动前，至少执行或核对：

```bash
git status --short --branch
git remote -v
git branch --show-current
```

如果任务涉及 GitHub PR、PR 评论、PR 合并或远端分支管理，还必须按 `开发者AI开发与PR提交流程.md` 检查：

```bash
gh --version
gh auth status
git fetch origin
```

要求：

- 不得在没看当前分支、远端和工作区状态的情况下开始写代码。
- 如果发现无法确认归属的脏改动，必须先说明，不得偷偷带进本次提交，也不得擅自删除。
- 不得假装执行过 GitHub 操作；`gh` 不可用、未登录、账号错误或权限不足时，必须明确报告。

## 4. 分支、提交、推送与 PR

- 本仓库当前默认分支为 `main`。
- 如果用户没有要求 PR，且当前任务语境是直接维护本仓库，可在当前分支按要求开发、提交和推送。
- 如果用户明确要求创建或更新 PR：
  - PR base 默认为 `main`。
  - 必须先同步最新 `origin/main`，确认分支没有落后。
  - 必须使用 `gh pr create/view/edit/merge` 的真实输出作为依据。
- 不得把 PR 指向 `master`，除非维护者明确改了仓库策略。
- 未经明确授权，不得擅自合并 PR、关闭 PR、删除远端分支。
- 必须区分“同步 PR 分支”和“合并 PR 到主分支”：只有 GitHub PR merge 动作完成并验证远端主分支前进，才算合并完成。
- 提交信息必须描述真实改动，禁止 `update`、`fix bug`、`AI 修改`、`修改一下` 这类空泛信息。

## 5. 本仓库架构与文件边界

本仓库是 Python / DeepAgents / Web 逆向项目：

- 核心源码：`src/reverse_deepagent/`
- 测试：`tests/`
- 脚本：`scripts/`
- 长期文档：`README.md`、`CONTRIBUTING.md`、`docs/`
- 运行时产物：`artifacts/`、`artifacts-*`，不要提交。

关键架构方向：

- `native-web + BrowserProvider + native collectors / hooks` 是 Web 逆向主线。
- `legacy-mcp` 是兼容后端。
- `mcp` / `jsreverser-mcp` 只作为 legacy alias 保留。
- 浏览器实现应通过 `BrowserProviderRegistry` / `reverse_deepagent.browser_providers` entry point 可插拔，不要把 MCP 当成新的抽象边界。
- MCP stdio transport、`JSReverserMcpConfig` 和真实 legacy MCP factory 归属 `packages/reverse-deepagent-legacy-mcp/` optional package；core 只保留 `reverse_deepagent.runtime.legacy_mcp` shim、默认命令常量、alias warning、doctor proxy、plugin delegation 和 install guidance。
- coordinator 不应直接依赖 Playwright、CDP、CloakBrowser 或 MCP tool name。
- 新增 runtime / provider / collector / hook / artifact schema 时，必须同步测试和文档。
- DeepAgents workspace contract 由 `src/reverse_deepagent/workspace_contract.py` 维护；新增或改变 subagent role、middleware checkpoint、workspace artifact、manifest key 或虚拟文件夹规划时，必须同步 `tests/test_workspace_contract.py`、README / runtime docs，并保持 `workspace/workspace-contract.json` 输出。
- `workspace/workspace-contract.json` 当前保持 indexed-only contract；现有扁平 `workspace/*.json` artifact 路径仍为 canonical path。`workspace/backend-artifact-manifest.json` 的 entry metadata 会为已登记 workspace artifact 提供 manifest-only `workspace_alias`，指向 `/workspace/<area>/...` foldered future path / `virtual://workspace/<area>/...` URI；没有 manifest alias、兼容覆盖和回归测试时，不得移动或重命名既有 artifact 路径。
- `review_workspace_dual_write_pilot_workflow` 只是 review-first workflow helper：它可以串联 readiness、pilot plan 和 observed scoped dual-write result verification，但不得运行 pipeline、启用双写、迁移路径、改变 canonical path、启动浏览器、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路；`write_result=true` 只能写 `workspace/workspace-dual-write-pilot-result.json` 审计结果。
- `assess_workspace_consumer_readiness_score` 只能作为 read-only review descriptor：允许消费 consumer audit、migration readiness、delivery source audit 和 dual-write pilot result JSON，输出 `workspace/workspace-consumer-readiness-score.json` / `/workspace/review/workspace-consumer-readiness-score.json` 的评分语义；不得检查文件、写 artifact、创建目录、启用 dual-write、迁移路径、改变 canonical path、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_dual_write_expansion` 只能作为 read-only / plan-only rollout descriptor：允许消费 readiness score、migration readiness、pilot result 和 reviewed artifact keys，输出 `workspace/workspace-dual-write-expansion-plan.json` / `/workspace/review/workspace-dual-write-expansion-plan.json` 的下一批 opt-in scope；不得运行 pipeline、写 artifact、创建目录、启用 dual-write、迁移路径、改变 canonical path、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_dual_write_expansion_workflow` / `record_workspace_dual_write_expansion_result` 只能作为 review-first observed-result verifier：允许消费 ready expansion plan、observed `workspace-dual-write-plan.json` 和既有 legacy / future 文件，验证 planned expansion scope 的文件存在性与 sha256 一致性；不得运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路；`write_result=true` 只能写 `workspace/workspace-dual-write-expansion-result.json` 审计结果。
- `plan_workspace_foldered_canonical_migration_pilot` 只能作为 read-only / plan-only narrow migration descriptor：允许消费 ready foldered-canonical readiness score、verified expansion result 和 reviewed artifact keys，输出 `workspace/workspace-foldered-canonical-migration-pilot-plan.json` / `/workspace/review/workspace-foldered-canonical-migration-pilot-plan.json` 的 future canonical path 候选；不得写 artifact、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_preflight` 只能作为 read-only execution preflight / rollback descriptor：允许消费 ready `workspace-foldered-canonical-migration-pilot-plan.json`，检查既有 legacy / future candidate 文件存在性与 sha256 一致性，输出 `workspace/workspace-foldered-canonical-migration-preflight.json` / `/workspace/review/workspace-foldered-canonical-migration-preflight.json` 的候选 readiness、rollback requirement 和 reviewed execution gate；不得写 artifact、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_migration_apply` 只能作为 read-only / plan-only apply descriptor：允许消费 ready `workspace-foldered-canonical-migration-preflight.json`，输出 `workspace/workspace-foldered-canonical-migration-apply-plan.json` / `/workspace/review/workspace-foldered-canonical-migration-apply-plan.json` 的 apply steps、manifest mutation guard、rollback requirement、compatibility guard 和 apply review gate；不得检查候选文件、写 artifact、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_migration_approval` 只能作为 read-only / plan-only approval / transaction descriptor：允许消费 ready `workspace-foldered-canonical-migration-apply-plan.json`，输出 `workspace/workspace-foldered-canonical-migration-approval-plan.json` / `/workspace/review/workspace-foldered-canonical-migration-approval-plan.json` 的 approval ledger requirement、transaction journal plan、idempotency guard、staleness guard、manifest dry-run requirement、rollback checkpoint requirement、post-apply validation requirement 和 compatibility fallback window；不得记录 approval、写 journal、检查候选文件、写 artifact、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_manifest_dry_run` 只能作为 read-only manifest dry-run / rollback checkpoint descriptor：允许消费 ready `workspace-foldered-canonical-migration-approval-plan.json`、matching `workspace-foldered-canonical-migration-apply-plan.json` 和当前 `workspace/backend-artifact-manifest.json`，输出 `workspace/workspace-foldered-canonical-migration-manifest-dry-run.json` / `/workspace/review/workspace-foldered-canonical-migration-manifest-dry-run.json` 的 manifest dry-run preview、digest guard、rollback checkpoint plan 和 separate executor gate；不得写 dry-run artifact、写 rollback checkpoint、记录 approval、写 journal、检查候选文件、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_physical_apply_preflight` 只能作为 read-only physical apply executor preflight descriptor：允许消费 ready `workspace-foldered-canonical-migration-manifest-dry-run.json`、matching `workspace-foldered-canonical-migration-apply-plan.json`、`workspace/review-approval-ledger.json` 和可选 `workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json`，输出 `workspace/workspace-foldered-canonical-migration-physical-apply-preflight.json` / `/workspace/review/workspace-foldered-canonical-migration-physical-apply-preflight.json` 的 approval ledger match、rollback checkpoint gate、append-only transaction journal plan、idempotency guard、post-apply validation requirement 和 separate executor input；不得写 journal、写 rollback checkpoint、写 artifact、记录 approval、检查候选文件、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `execute_workspace_foldered_canonical_physical_apply` 只能作为 explicit-review-only physical apply executor skeleton：默认 `mode=dry-run` 必须保持只读；只有 `mode=apply`、`approve_physical_apply=true`、ready physical apply preflight、matching manifest dry-run / apply-plan digest、approved review ledger evidence、当前 backend manifest artifact-ref gate 和 idempotency guard 全部通过时，才允许写 `workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json`、append-only `workspace/workspace-foldered-canonical-migration-physical-apply-journal.json`、`workspace/workspace-foldered-canonical-migration-physical-apply-result.json` 并更新 `workspace/backend-artifact-manifest.json` entry canonical path；不得移动 workspace 文件、运行 pipeline、启用 dual-write、收紧 legacy fallback、自动运行 post-apply validation、自动 rollback / commit、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_post_apply_validation` 只能作为 read-only post-apply validation descriptor：允许消费 ready `workspace-foldered-canonical-migration-manifest-dry-run.json`、matching `workspace-foldered-canonical-migration-apply-plan.json` 和观测到的 post-apply `workspace/backend-artifact-manifest.json`，输出 `workspace/workspace-foldered-canonical-migration-post-apply-validation.json` / `/workspace/review/workspace-foldered-canonical-migration-post-apply-validation.json` 的 canonical-path promotion validation、digest guard、compatibility validation 和 legacy fallback review gate；不得写 validation artifact、写 rollback checkpoint、记录 approval、写 journal、检查候选文件、创建目录、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `record_workspace_foldered_canonical_migration_post_apply_validation_result` 只能作为 explicit post-apply validation result writer：允许消费 ready post-apply validation descriptor，默认 dry-run 只返回可记录结果，只有 `write_result=true` 才能写 `workspace/workspace-foldered-canonical-migration-post-apply-validation-result.json` / `/workspace/review/workspace-foldered-canonical-migration-post-apply-validation-result.json`；不得写 rollback checkpoint、记录 approval、写 journal、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、执行 foldered-canonical finalization、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_legacy_fallback_tightening_readiness` 只能作为 read-only legacy fallback tightening readiness descriptor：允许消费 verified post-apply validation result 和 ready workspace consumer readiness score，输出 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-readiness.json` / `/workspace/review/workspace-foldered-canonical-legacy-fallback-tightening-readiness.json` 的 readiness gate；不得写 artifact、记录 approval、写 journal、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、执行 tightening apply / executor、执行 foldered-canonical finalization、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_legacy_fallback_tightening` 只能作为 review-only legacy fallback tightening apply plan descriptor：允许消费 ready tightening readiness descriptor 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-plan.json` / `/workspace/review/workspace-foldered-canonical-legacy-fallback-tightening-plan.json` 的 planned metadata update preview、approval requirement、transaction journal plan 和 executor gate；不得写 artifact、记录 approval、写 journal、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、执行 tightening executor、执行 foldered-canonical finalization、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_legacy_fallback_tightening_preflight` 只能作为 read-only legacy fallback tightening executor preflight descriptor：允许消费 ready tightening plan、当前 backend artifact manifest 和 review approval ledger，输出 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-preflight.json` / `/workspace/review/workspace-foldered-canonical-legacy-fallback-tightening-preflight.json` 的 digest guard、approval gate、manifest revalidation、transaction journal plan、idempotency guard 和 executor gate；不得写 artifact、记录 approval、写 journal、运行 pipeline、启用 dual-write、迁移路径、改变 canonical path、mutate manifest、收紧 legacy fallback、执行 tightening executor、执行 foldered-canonical finalization、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `execute_workspace_foldered_canonical_legacy_fallback_tightening` 只能作为 explicit-review-only legacy fallback tightening executor：默认 dry-run 必须只读；apply 必须显式 `mode=apply` + `approve_legacy_fallback_tightening=true` + ready preflight + matching plan digest + 当前 backend manifest artifact-ref，允许写 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-journal.json` / `/workspace/review/workspace-foldered-canonical-legacy-fallback-tightening-journal.json`、`workspace/workspace-foldered-canonical-legacy-fallback-tightening-result.json` / `/workspace/review/workspace-foldered-canonical-legacy-fallback-tightening-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` legacy fallback 状态；不得移动 workspace 文件、改变 canonical path、执行 foldered-canonical finalization、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_finalization_readiness` 只能作为 read-only foldered-canonical finalization readiness descriptor：允许消费 applied legacy fallback tightening result 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-migration-finalization-readiness.json` / `/workspace/review/workspace-foldered-canonical-migration-finalization-readiness.json` 的 readiness gate、manifest revalidation 和 separate finalization plan gate；不得写 artifact、记录 approval、写 journal、mutate manifest、移动 workspace 文件、改变 canonical path、执行 foldered-canonical finalization、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_migration_finalization` 只能作为 review-only / plan-only foldered-canonical finalization plan descriptor：允许消费 ready finalization readiness descriptor 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-migration-finalization-plan.json` / `/workspace/review/workspace-foldered-canonical-migration-finalization-plan.json` 的 planned metadata update preview、approval requirement、transaction journal plan、digest guard 和 preflight / executor gate；不得写 artifact、记录 approval、写 journal、mutate manifest、移动 workspace 文件、改变 canonical path、执行 foldered-canonical finalization、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_finalization_preflight` 只能作为 read-only foldered-canonical finalization executor preflight descriptor：允许消费 ready finalization plan、当前 backend artifact manifest 和 review approval ledger，输出 `workspace/workspace-foldered-canonical-migration-finalization-preflight.json` / `/workspace/review/workspace-foldered-canonical-migration-finalization-preflight.json` 的 digest guard、approval gate、manifest revalidation、transaction journal plan、idempotency guard 和 separate executor gate；不得写 artifact、记录 approval、写 journal、mutate manifest、移动 workspace 文件、改变 canonical path、执行 foldered-canonical finalization、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `execute_workspace_foldered_canonical_migration_finalization` 只能作为 explicit-review-only foldered-canonical finalization executor：默认 dry-run 必须只读；apply 必须显式 `mode=apply` + `approve_finalization=true` + ready finalization preflight + matching plan digest + 当前 backend manifest artifact-ref，并通过 approval gate、manifest revalidation 和 idempotency guard；允许写 `workspace/workspace-foldered-canonical-migration-finalization-journal.json` / `/workspace/review/workspace-foldered-canonical-migration-finalization-journal.json`、`workspace/workspace-foldered-canonical-migration-finalization-result.json` / `/workspace/review/workspace-foldered-canonical-migration-finalization-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` finalization 状态；不得接受 inline backend manifest JSON 执行真实 apply，不得移动 workspace 文件、改变 canonical path、收紧 legacy fallback、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_migration_post_finalization_audit` 只能作为 read-only post-finalization audit descriptor：允许消费 applied finalization result、append-only finalization journal 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-migration-post-finalization-audit.json` / `/workspace/review/workspace-foldered-canonical-migration-post-finalization-audit.json` 的 transaction / idempotency / journal / `metadata.workspace_alias` finalization / canonical path stability 审计；不得写 artifact、mutate manifest、移动 workspace 文件、改变 canonical path、收紧 legacy fallback、执行 finalization、授权 broader rollout、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_broader_rollout_readiness` 只能作为 read-only broader rollout readiness descriptor：允许消费 verified post-finalization audit、workspace consumer readiness score、fresh delivery source audit、verified dual-write expansion result 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-broader-rollout-readiness.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-readiness.json` 的 rollout readiness gate；不得写 artifact、mutate manifest、移动 workspace 文件、改变 canonical path、收紧 legacy fallback、执行 finalization、授权 broader rollout apply、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_broader_rollout` 只能作为 review-only / plan-only broader rollout plan descriptor：允许消费 ready broader rollout readiness descriptor 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-broader-rollout-plan.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-plan.json` 的 reviewed rollout scope、digest guard、approval requirement、preflight / executor gate 和 side-effect boundary；不得写 artifact、mutate manifest、移动 workspace 文件、改变 canonical path、收紧 legacy fallback、授权 broader rollout apply、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_broader_rollout_preflight` 只能作为 read-only broader rollout executor preflight descriptor：允许消费 ready broader rollout plan、当前 backend artifact manifest 和 review approval ledger，输出 `workspace/workspace-foldered-canonical-broader-rollout-preflight.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-preflight.json` 的 plan digest guard、approval gate、manifest revalidation、transaction journal plan、idempotency guard、result artifact plan 和 executor gate；不得写 artifact、写 journal、mutate manifest、移动 workspace 文件、改变 canonical path、收紧 legacy fallback、授权 broader rollout apply、运行 pipeline、启用 dual-write、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `execute_workspace_foldered_canonical_broader_rollout` 只能作为 explicit-review-only broader rollout executor：默认 dry-run 必须只读；apply 必须显式 `mode=apply` + `approve_broader_rollout=true` + ready broader rollout preflight + matching plan digest + 当前 backend manifest artifact-ref，并通过 approval gate、manifest revalidation 和 idempotency guard；允许写 `workspace/workspace-foldered-canonical-broader-rollout-journal.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-journal.json`、`workspace/workspace-foldered-canonical-broader-rollout-result.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` broader rollout metadata；不得接受 inline backend manifest JSON 执行真实 apply，不得移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_broader_rollout_post_audit` 只能作为 read-only broader rollout post-audit descriptor：允许消费 applied broader rollout result、append-only broader rollout journal 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-broader-rollout-post-audit.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-post-audit.json` 的 transaction / idempotency / journal / `metadata.workspace_alias` broader rollout / canonical path stability 审计；不得写 artifact、mutate manifest、移动 workspace 文件、改变 canonical path、启用 dual-write、执行 rollback-vs-commit decision、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `plan_workspace_foldered_canonical_broader_rollout_rollback_decision` 只能作为 review-only / plan-only rollback-vs-commit decision descriptor：允许消费 verified broader rollout post-audit 和当前 backend artifact manifest，输出 `workspace/workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json` 的 commit / rollback / defer review options、current manifest revalidation、decision gate 和 side-effect boundary；不得写 artifact、记录 decision、commit broader rollout、rollback broader rollout、mutate manifest、移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `record_workspace_foldered_canonical_broader_rollout_decision` 只能作为 explicit reviewed decision record writer：允许消费 ready rollback-vs-commit decision plan，在 `write_result=true` + `approve_decision_record=true` + reviewer 非空时写 `workspace/workspace-foldered-canonical-broader-rollout-decision-record.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-decision-record.json` 的 commit / rollback / defer 人工决策审计记录；不得 commit broader rollout、rollback broader rollout、mutate manifest、移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `execute_workspace_foldered_canonical_broader_rollout_commit` 只能作为 explicit-review-only broader rollout commit executor：默认 dry-run 必须只读；apply 必须显式 `mode=apply` + `approve_commit=true` + recorded commit decision record + 当前 backend manifest artifact-ref，并通过 transaction / idempotency guard 与当前 manifest entry revalidation；允许写 `workspace/workspace-foldered-canonical-broader-rollout-commit-journal.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-commit-journal.json`、`workspace/workspace-foldered-canonical-broader-rollout-commit-result.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-commit-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` broader rollout commit metadata；不得接受 inline backend manifest JSON 执行真实 apply，不得 rollback broader rollout、移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路。
- `review_workspace_foldered_canonical_broader_rollout_rollback_preflight` 只能作为 read-only broader rollout rollback executor preflight descriptor：允许消费 recorded rollback decision record、当前 backend manifest 和可选 commit journal，输出 `workspace/workspace-foldered-canonical-broader-rollout-rollback-preflight.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-preflight.json` 的 transaction guard、commit-state guard、manifest entry revalidation 和 separate rollback executor gate；不得写 artifact、写 journal、mutate manifest、rollback broader rollout、移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路；若 manifest 或 commit journal 显示已 committed，必须阻断 rollback preflight。
- `execute_workspace_foldered_canonical_broader_rollout_rollback` 只能作为 explicit-review-only broader rollout rollback executor：默认 dry-run 必须只读；apply 必须显式 `mode=apply` + `approve_rollback=true` + ready rollback preflight + recorded rollback decision record + 当前 backend manifest artifact-ref，并通过 commit-state guard、transaction guard、manifest entry revalidation 和 rollback idempotency guard；允许写 `workspace/workspace-foldered-canonical-broader-rollout-rollback-journal.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-journal.json`、`workspace/workspace-foldered-canonical-broader-rollout-rollback-result.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` broader rollout rollback metadata；不得接受 inline backend manifest JSON 执行真实 apply，不得 commit broader rollout、移动 workspace 文件、改变 canonical path、启用 dual-write、运行 pipeline、启动浏览器、发送 CDP、调用 MCP 或触碰 Android / iOS / 小程序完整运行链路；若 manifest 或 commit journal 显示已 committed，必须阻断 rollback executor。

重点文件变更要求：

- 改 runtime registry / coordinator：检查 `tests/test_coordinator.py`、`tests/test_runtime_registry.py`、相关 pipeline 测试。
- 改 workspace contract / subagent / middleware / artifact route / workspace review workflow：检查 `tests/test_workspace_contract.py`、`tests/test_workspace_artifact_reader.py`、`tests/test_coordinator.py`、相关 subagent / coordinator tool 暴露测试、README 和 runtime docs。
- 改 delivery executor / transaction journal / external delivery / state machine：检查 `tests/test_delivery_executors.py`、`tests/test_delivery_tools.py`、`tests/test_delivery_state_machine.py`、README 和 plan 文档；状态机默认必须保持 read-only，不得在 evaluator / transition planner 中执行文件、网络、manifest mutation 或恢复动作。
- 改 BrowserProvider / BrowserProviderRegistry：检查 `tests/test_browser_provider_*`、`tests/test_browser_smoke_matrix.py`、`tests/test_browser_provider_smoke_cli.py`、`tests/test_playwright_provider.py`、`tests/test_cloakbrowser_provider.py`、`tests/test_remote_cdp_provider.py`、`tests/test_native_web_runtime.py`、`tests/test_doctor.py`、README 和 runtime docs。BrowserProvider metadata / matrix / registration listing / smoke artifact metadata-only 路径默认必须 side-effect-free，不得调用 provider factory、读取第三方 API key、创建 hosted session、启动浏览器、探测 CDP 端点或依赖 MCP；只有显式 `--launch-browser-smoke` 或等价开关才允许启动真实浏览器。`--browser-provider-smoke-json` 只能附加既有 UTF-8 JSON object，必须通过 metadata-only `attachment_acceptance` 标明 schema / ok / provider match / side-effect policy / launch-smoke consistency，不得把 metadata-only 或 availability-check evidence 宣称成已通过 runtime launch smoke。
- 改 native collectors / hooks：检查 `tests/test_browser_collectors.py`、`tests/test_cdp_collectors.py`、`tests/test_browser_hooks.py`、`tests/test_breakpoint_manager.py`、`tests/test_function_hooks.py`、`tests/test_module_hooks.py`、`tests/test_source_logpoints.py`；涉及 `module-discovery` / `hook-module` 还必须同步 `tests/test_native_web_runtime.py` 的 protection 集成断言；涉及 runtime module cache introspection 时必须覆盖 `require.c` / `require.m` 可用与不可用的结构化结果；涉及 `module_runtime_paths`、custom object runtime、module federation exposed-module baseline、review-only module federation traversal graph / workflow plan、review-gated module federation traversal workflow execution、review-only module federation recursive traversal follow-up planning、review-gated module federation recursive traversal follow-up checkpoint、review-gated module federation recursive traversal next-step execution、review-only module federation recursive continuation journal / multi-step checkpoint plan、review-gated module federation recursive continuation checkpoint execution、async chunk graph / loader metadata baseline、review-only async chunk traversal graph / queue、review-only async chunk traversal workflow plan、review-gated async chunk traversal workflow execution、review-only bounded async chunk traversal loop plan、review-gated bounded async chunk traversal loop execution、review-only async chunk recursive traversal follow-up planning、review-gated async chunk recursive traversal follow-up checkpoint、review-gated async chunk recursive traversal next-loop execution、reviewed custom-loader execution、bounded custom-loader traversal continuation、review-only custom-loader traversal graph / queue、review-only multi-step custom-loader traversal workflow plan、review-gated custom-loader traversal workflow execution、review-only bounded custom-loader traversal loop plan、review-gated bounded custom-loader traversal loop execution / review-only recursive custom-loader traversal follow-up planning / review-gated custom-loader recursive traversal follow-up checkpoint、review-gated custom-loader recursive traversal next-loop execution、review-only custom-loader continuation workflow planning、review-gated custom-loader continuation journal、review-approved one-step custom-loader continuation execution、custom-loader module diff / hook candidate refresh 或 reviewed custom-loader module hook follow-through 时，必须覆盖 `tests/test_module_hooks.py` 的 `hook_kind` / `function-path` candidate、chunk graph side-effect policy、async chunk traversal workflow side-effect policy、async chunk traversal workflow execution side-effect policy、async chunk traversal loop plan side-effect policy、async chunk traversal loop execution side-effect policy、async chunk recursive traversal execution side-effect policy、custom-loader execution side-effect policy、custom-loader traversal workflow execution side-effect policy、custom-loader traversal loop execution side-effect policy、custom-loader recursive traversal execution side-effect policy、custom-loader continuation execution side-effect policy、custom-loader module diff side-effect policy 或 reviewed custom-loader module hook side-effect policy，以及 `tests/test_native_web_runtime.py` 的 native-web artifact metadata；unified `recursive-continuation-readiness` descriptor 还必须覆盖 workspace contract、coordinator payload/category、hook review blocker/warning，并证明不调用 loader、不请求 chunk、不 invoke remote factory、不 rebuild graph、不 replan workflow、不调用 MCP、不触碰移动端完整链路；涉及 `closure-function-discovery` / `closure-scope` / `closure-wrapper-replacement-plan` / `closure-wrapper-assignment-safety` / `closure-wrapper-runtime-mutability-preflight` / `closure-wrapper-runtime-mutability-result` / `closure-wrapper-replacement-execution` / `closure-wrapper-restore-execution` / `closure-wrapper-events` / `closure-wrapper-continuation-readiness` / `closure-wrapper-continuation-execution-plan` / `closure-wrapper-continuation-execution` / `closure-wrapper-continuation-next-iteration-plan` / `closure-wrapper-continuation-next-iteration-execution` 时，必须覆盖 `tests/test_closure_scope.py` 的 paused-callframe 只读候选证明、review-only wrapper replacement plan、review-only assignment safety proof、review-only runtime mutability preflight、review-approved runtime mutability result 或 reviewed same-process execution、`tests/test_native_web_runtime.py` 的 `closure-functions.json` / `closure-function-candidates.json` / `closure-wrapper-replacement-plan.json` / `closure-wrapper-assignment-safety.json` / `closure-wrapper-runtime-mutability-preflight.json` / `closure-wrapper-runtime-mutability-result.json` / `closure-wrapper-replacement-execution.json` / `closure-wrapper-restore-plan.json` / `closure-wrapper-restore-execution.json` / `closure-wrapper-events.json` / `closure-wrapper-continuation-readiness.json` / `closure-wrapper-continuation-execution-plan.json` / `closure-wrapper-continuation-execution.json` / `closure-wrapper-continuation-checkpoint.json` / `closure-wrapper-continuation-next-iteration-plan.json` / `closure-wrapper-continuation-next-iteration-execution.json` artifact 断言、`tests/test_hook_subagent.py` 的 review / proof / mutability preflight / restore warning、workspace contract 和 coordinator payload/category 映射，并证明 plan-only / assignment-safety / runtime-mutability-preflight 路径无 wrapper install / runtime mutation / CDP command / callframe evaluation，runtime-mutability-result 路径必须 explicit review approval + same-process retained pause + temporary assignment audit + original restore 且不得安装 wrapper / 调用目标函数，install / restore execution 路径必须 explicit review approval + same-process retained pause + assignment safety proof + mutation audit + restore plan 或 restore result；install 若启用 runtime mutability result gate，还必须 matching proven result + original restore + no durable wrapper before replacement；closure wrapper strategy catalog 目前只能让 `log-only-call-through` 通过 reviewed install，`arg-preview` / `return-preview` / `throw-preview` / `blocked-mutation-plan` 只能作为 plan-only descriptor 输出，必须在 hook review 中暴露 plan-only / non-install-supported warning，不得把 preview / mutation 策略宣称为可执行；event harvesting 路径必须 read-only，不得触发目标函数、安装 hook、发送 CDP 或 mutate runtime；closure-wrapper-continuation-readiness 必须保持 read-only，只能消费既有 wrapper execution / events 与 paused-session continuation checkpoint 或 live callFrame recovery evidence，不得安装 wrapper、recover callFrame、发送 CDP、evaluate JavaScript、执行 paused-session action、循环、调用 MCP 或触碰移动端完整链路；closure-wrapper-continuation-execution-plan 必须保持 review-only / plan-only，只能消费 wrapper readiness 与 paused-session lifecycle / loop / checkpoint / live-callFrame-recovery evidence，不得安装或恢复 wrapper、recover callFrame、发送 CDP、evaluate JavaScript、订阅或捕获 paused event、执行 paused-session action、推进 loop、调用 MCP 或触碰移动端完整链路，且不得宣称已支持任意闭包函数自动 wrapper hook；closure-wrapper-continuation-execution 必须 explicit review approval + ready execution plan + ready multi-step workflow + fresh live callFrame + retained attached session，一次最多委托 existing multi-step executor 执行一个 reviewed paused-session step，执行后必须要求 wrapper event harvesting 和 continuation checkpoint，不得安装或恢复 wrapper、不得自动 harvest events、不得自动 recover live callFrame、不得执行下一步、不得自动 loop、不得调用 MCP / 触碰移动端完整链路；closure-wrapper-continuation-checkpoint 必须保持 read-only / review-only，只能消费已执行的 wrapper continuation execution、post-execution wrapper events、paused-session continuation checkpoint 和可选 loop-plan evidence 来审阅下一轮 wrapper-aware iteration，不得 harvest events、不得发送 CDP、不得订阅或捕获 paused event、不得 recover callFrame、不得执行下一步、不得安装 / 恢复 wrapper、不得自动 queue advance / loop、不得调用 MCP / 触碰移动端完整链路；closure-wrapper-continuation-next-iteration-plan 必须保持 read-only / review-only / plan-only，只能消费 ready checkpoint、previous execution plan、paused-session loop-plan 和可选 live-callFrame-recovery evidence 来生成下一轮 review input，不得 harvest events、不得发送 CDP、不得订阅或捕获 paused event、不得 recover callFrame、不得执行下一步、不得安装 / 恢复 wrapper、不得自动 queue advance / loop、不得调用 MCP / 触碰移动端完整链路；closure-wrapper-continuation-next-iteration-execution 必须 explicit review approval + ready next-iteration plan + ready execution plan + ready multi-step workflow + fresh live callFrame + retained attached session，一次最多委托 existing wrapper continuation executor 执行一个 reviewed next paused-session step，执行后必须要求 wrapper event harvesting 和 continuation checkpoint，不得安装或恢复 wrapper、不得自动 harvest events、不得自动 recover live callFrame、不得执行下一步、不得自动 queue advance / loop、不得调用 MCP / 触碰移动端完整链路；涉及 `page-mutation-audit` / `object-graph-diff` / `mutation-observer-timeline` 时必须覆盖独立 manager 单测和 native-web protection artifact 断言；`object-graph-diff` 必须保持 review-only，只消费调用方提供的 before/after snapshots，不得启动浏览器、采集 heap、evaluate JavaScript、发送 CDP、调用 MCP 或宣称完整 heap traversal；`mutation-observer-timeline` 必须保持显式触发，不得进入默认 recon，且不得复用 `mutation-audit.json` 混淆 callframe side-effect audit；涉及 source-map remap / `source-map-lookup` / `source-map-source-content` / `source-map-readiness` / `source-map-consumer-action-plan` / `source-map-consumer-materialization` / `bundler-symbol-scope` 时必须覆盖 `tests/test_source_maps.py`、`tests/test_source_logpoints.py`、`tests/test_native_web_runtime.py`、`tests/test_workspace_contract.py`、`tests/test_coordinator.py`、`tests/test_hook_subagent.py`、workspace contract、coordinator payload/category 和 hook review warning / blocker，至少说明 exact / bias / sourceRoot / indexed sections / `names` metadata / URL-like source equivalence / nested indexed-section stack / generated-to-original lookup / original-to-generated lookup / source-content availability descriptor / readiness join descriptor / consumer action plan descriptor / consumer materialization descriptor / conservative bundler symbol descriptor 的支持边界，以及 `source-map-lookup`、`source-map-source-content`、`source-map-readiness`、`source-map-consumer-action-plan` 和 `source-map-consumer-materialization` 必须保持 review-only、不 fetch 外部 source-map URL / section URL、不启动浏览器、不安装 logpoint、不 evaluate JS、不发送 CDP、不调用 MCP、不触碰移动端完整链路；`source-map-source-content` 还必须证明不导出 raw source content、不导出 preview、只输出 digest / size / line-count metadata；`source-map-readiness` 还必须证明只消费既有 lookup / source-content / symbol-scope / fetch metadata descriptors，不解析或导出 raw source / preview，不自动执行 debugger / rebuild / source-logpoint planning；`source-map-consumer-action-plan` 还必须证明只消费 readiness / lookup / source-content / symbol-scope descriptors，只输出 plan-only reviewed consumer actions，不执行 debugger、不写 rebuild、不安装 logpoint 或 hook；`source-map-consumer-materialization` 还必须证明只消费 ready action plan 和可选 lookup / source-content / symbol-scope descriptors，只输出 typed review payloads，不执行 debugger、不安装 logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不调用 MCP、不触碰移动端完整链路；涉及 paused-session 持久化、live-continuation preflight、target attach readiness proof、cross-process execution plan、reviewed cross-process attach probe、cross-process session lifecycle descriptor、live callFrame recovery proof 或 cross-process one-action execution、next paused-event capture planning、next paused-event capture execution、cross-process continuation checkpoint、pre-action subscribe-and-action orchestration 或 multi-step continuation workflow / journal plan 或 multi-step continuation one-iteration execution 时必须同时覆盖 `continuation_preflight`、同进程 registry live continuation、durable snapshot inspect-only、`paused-session-live-continuation-preflight.json` 只读 blocker artifact、`paused-session-target-attach-readiness.json` 只读 target correlation / attachability proof artifact、`paused-session-cross-process-execution-plan.json` plan-only executor descriptor、`paused-session-cross-process-attach-probe.json` reviewed Target.attachToTarget / Target.detachFromTarget probe artifact、`paused-session-cross-process-session-lifecycle.json` read-only session lifecycle descriptor artifact、`paused-session-live-callframe-recovery.json` read-only fresh live callFrame proof artifact、`paused-session-cross-process-one-action-execution.json` reviewed one-action execution artifact、`paused-session-next-paused-event-capture-plan.json` review-only next paused-event capture plan artifact、`paused-session-next-paused-event-capture-execution.json` reviewed one-shot next paused-event capture execution artifact、`paused-session-cross-process-continuation-checkpoint.json` review-only captured-pause continuation checkpoint artifact、`paused-session-pre-action-subscribe-and-action.json` reviewed pre-action subscribe-and-action orchestration artifact、`paused-session-multi-step-continuation-workflow.json` review-only multi-step continuation workflow / journal plan、multi-step continuation one-iteration execution artifact、`paused-session-multi-step-loop-plan.json` review-only loop plan artifact、`paused-session-multi-step-loop-execution.json` review-gated loop one-iteration execution artifact、`paused-session-automatic-loop-readiness.json` read-only / review-only / plan-only future bounded automatic-loop executor readiness artifact、`paused-session-automatic-loop-execution-plan.json` review-only / plan-only future bounded automatic-loop executor plan artifact 或 `paused-session-automatic-loop-executor-preflight.json` read-only / review-only / preflight-only future bounded automatic-loop executor preflight artifact 或 `paused-session-automatic-loop-executor-approval-plan.json` review-only / approval-plan-only / transaction-plan-only future bounded automatic-loop executor approval-plan artifact、`paused-session-automatic-loop-execution-result.json` explicit-review-only bounded one-iteration automatic-loop execution result artifact、`live_session_diagnostics` / `target_diagnostics` / `callframe_diagnostics` / `action_capability` / `target_correlation` / `attachability` / `callframe_recovery` / execution plan review gates / attach probe side-effect policy / session lifecycle side-effect policy / live callFrame recovery side-effect policy / one-action execution side-effect policy / next paused-event capture plan side-effect policy / next paused-event capture execution side-effect policy / cross-process continuation checkpoint side-effect policy / pre-action subscribe-and-action side-effect policy / multi-step continuation workflow side-effect policy / multi-step continuation execution side-effect policy / multi-step loop plan side-effect policy / multi-step loop execution side-effect policy 诊断字段；preflight / readiness / plan / recovery proof 路径必须保持不 attach CDP target / 不 probe CDP / 不发送 CDP / 不 resume / 不 step / 不 evaluate / 不调用 MCP / 不触碰移动端完整链路，attach probe 路径必须 explicit review approval 且只允许 Target attach / detach，不得启用 Debugger domain、不得 recover live callFrame、不得 resume / step / evaluate / 调用 MCP / 触碰移动端完整链路；session lifecycle descriptor 必须保持 read-only，只能消费已有 preflight / readiness / execution plan / attach probe / live callFrame recovery / capture / checkpoint / multi-step evidence，不得 probe target liveness、attach / detach CDP target、recover callFrame、订阅或捕获 paused event、resume / step / evaluate、执行 action、循环、调用 MCP / 触碰移动端完整链路；live callFrame recovery proof 必须默认要求 attach 后 fresh paused event，不得复用 durable callFrameId，不得启用 Debugger domain / 发送 CDP / resume / step / evaluate / 调用 MCP / 触碰移动端完整链路，不得宣称跨进程自动 live resume / step / evaluate 已支持；one-action execution 必须 explicit review approval + retained attached session + fresh live callFrameId，一次只允许一个 Debugger.resume / step / evaluateOnCallFrame 命令，不得自动 attach / detach、不得启用 Debugger domain、不得订阅或捕获下一次 paused event、不得循环执行、不得调用 MCP / 触碰移动端完整链路；next paused-event capture plan 必须保持 review-only，不得发送 CDP、不得订阅 Debugger.paused、不得等待或捕获 paused event、不得恢复 / step / evaluate / 循环、不得调用 MCP / 触碰移动端完整链路；next paused-event capture execution 必须 explicit review approval + retained attached session，一次最多订阅 / 等待一个 Debugger.paused event 或归一化调用方提供的 observed paused event，不得发送 Debugger step / resume / evaluate 命令、不得启用 Debugger domain、不得循环、不得自动 recover live callFrame、不得调用 MCP / 触碰移动端完整链路；cross-process continuation checkpoint 必须保持 review-only，只能消费 captured next paused-event evidence 并规划 live callFrame recovery 或下一次 one-action review，不得发送 CDP、不得订阅或捕获 paused event、不得 resume / step / evaluate、不得自动 recover live callFrame、不得执行 action、不得循环、不得调用 MCP / 触碰移动端完整链路；pre-action subscribe-and-action orchestration 必须 explicit review approval + retained attached session + fresh live callFrameId，必须先订阅 Debugger.paused 再发送 exactly one reviewed resume / step command，一次最多捕获一个 bounded paused event，不得支持 evaluate、不自动 recover live callFrame、不循环、不做 multi-step continuation、不安装 wrapper、不调用 MCP / 触碰移动端完整链路；multi-step continuation workflow / journal plan 必须保持 review-only，只能消费 ready continuation checkpoint 和 planned actions 生成 bounded workflow / append-only journal plan，不得发送 CDP、不得订阅或捕获 paused event、不得执行 action、不得自动 recover live callFrame、不得循环、不得调用 MCP / 触碰移动端完整链路；multi-step continuation one-iteration execution 必须 explicit review approval + fresh live callFrame + retained attached session，一次最多执行一个 reviewed planned step 并要求后续 checkpoint，不得自动执行下一步、不得自动 recover live callFrame、不得循环、不得调用 MCP / 触碰移动端完整链路；paused-session multi-step loop plan 必须保持 review-only，只能消费 lifecycle / workflow / latest execution / continuation checkpoint evidence 并规划下一次 reviewed loop iteration，不得发送 CDP、不得订阅或捕获 paused event、不得 recover live callFrame、不得执行 action、不得自动 queue advance、不得自动 loop、不得调用 MCP / 触碰移动端完整链路；paused-session multi-step loop execution 必须 explicit review approval + ready loop plan + ready multi-step workflow + fresh live callFrame + retained attached session，一次最多委托 existing multi-step executor 执行一个 reviewed next iteration，执行后必须要求 continuation checkpoint，不得自动 recover live callFrame、不得执行下一步、不得 replan / advance queue / advance loop、不得调用 MCP / 触碰移动端完整链路；paused-session automatic-loop execution result 必须 explicit review approval + ready bounded executor gate + written transaction journal + ready multi-step loop plan + ready multi-step workflow + fresh live callFrame + retained attached session；当前 MVP 一次最多委托 existing multi-step loop executor 执行一个 reviewed iteration，必须输出 `paused-session-automatic-loop-execution-result.json`，执行后必须 `checkpoint_required=true` 并要求 continuation checkpoint，不得自动 recover live callFrame、不得自动捕获下一轮 paused event、不得执行第二步、不得 replan / advance queue / advance loop、不得管理 long-lived cross-process session、不得调用 MCP / 触碰移动端完整链路；paused-session automatic-loop readiness 必须保持 read-only / review-only / plan-only，只能消费 ready loop plan、ready multi-step workflow、session lifecycle、latest loop execution 和 continuation checkpoint evidence，为 future bounded automatic-loop executor contract 生成机器可读 gate，不得发送 CDP、订阅或捕获 paused event、recover live callFrame、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `automation_executor_implemented=false` 与 `automatic_multi_step_loop_supported=false`；paused-session automatic-loop execution plan 必须保持 read-only / review-only / plan-only，只能消费 ready automatic-loop readiness descriptor，为 future bounded executor 生成 review input，不得发送 CDP、订阅或捕获 paused event、recover live callFrame、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `future_executor_contract.implemented=false`；paused-session automatic-loop executor preflight 必须保持 read-only / review-only / preflight-only / plan-only，只能消费 ready automatic-loop execution plan descriptor，为 future bounded executor 生成 executor gate，不得发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `future_executor_contract.implemented=false` 与 `executor_input_gates.ready_to_execute_now=false`；paused-session automatic-loop executor approval plan 必须保持 review-only / approval-plan-only / transaction-plan-only，只能消费 ready automatic-loop executor preflight descriptor，为 future bounded executor 规划 approval record、idempotency key、transaction journal 和 result artifact gate，不得记录 approval、写 journal、发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `future_executor_contract.implemented=false`、`executor_input_gates.ready_to_execute_now=false`、`executor_input_gates.approval_recorded=false`、`transaction_plan.transaction_started=false` 与 `transaction_plan.journal_written_now=false`；paused-session automatic-loop executor approval record writer 必须保持 explicit-review-only，只能消费 ready automatic-loop executor approval plan 并在 `mode=apply`、`write_result=true`、`approve_approval_record=true`、reviewer 非空、plan id / preflight id / digest guard 通过后写 `workspace/paused-session-automatic-loop-executor-approval-record.json` 审计记录，不得写 transaction journal、启动 transaction、发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `approval_recorded=true` 仅表示审批记录已写入、`transaction_started=false`、`journal_written=false`、`automatic_loop_executed=false`；paused-session automatic-loop transaction / journal preflight 必须保持 read-only / review-only / transaction-preflight-only，只能消费 ready approval plan 和 written approved approval record，输出 `workspace/paused-session-automatic-loop-transaction-preflight.json` / `/workspace/debugger/paused-session-automatic-loop-transaction-preflight.json` 的 journal-writer gate，不得写 artifact、写 transaction journal、启动 transaction、发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、执行 multi-step continuation、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `ready_to_write_now=false`、`transaction_started=false`、`journal_written_now=false`、`automatic_loop_executed=false`；paused-session automatic-loop transaction journal writer 必须保持 explicit-review-only，只能消费 ready transaction preflight，并在 `mode=apply`、`write_result=true`、`approve_transaction_journal=true`、reviewer 非空、transaction preflight id / approval record id / transaction id / preflight id / digest guard 通过且 journal 文件不存在后写 `workspace/paused-session-automatic-loop-executor-journal.json` 审计记录，不得执行 automatic loop、发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `journal_written=true` 不代表 executor 已执行、`ready_to_execute_now=false`、`automatic_loop_executed=false`；paused-session automatic-loop bounded executor gate 必须保持 read-only / review-only / plan-only，只能消费 written transaction journal，输出 `workspace/paused-session-automatic-loop-bounded-executor-gate.json` / `/workspace/debugger/paused-session-automatic-loop-bounded-executor-gate.json` 的 final gate 和 future result contract，不得执行 automatic loop、发送 CDP、attach target、启用 Debugger domain、订阅或捕获 paused event、recover live callFrame、evaluate JavaScript、advance loop / queue、管理 long-lived cross-process session、调用 MCP 或触碰移动端完整链路，且必须明确 `ready_to_execute_now=false`、`future_executor_contract.implemented=false`、`automatic_loop_executed=false`；涉及 `flow-timeline` / `cross-request-timeline` 时必须覆盖 `tests/test_flow_timeline.py` 的 previous timeline continuation / source normalization / correlation hints / conservative correlation groups / group verification readiness / manual-only `stitch_candidates` / `auto_stitch_dry_runs` dry-run scoring / `auto_stitch_policy_decisions` policy gate / `auto_stitch_materialization_plans` plan-only materialization baseline / review-approved `auto_stitch_materialization_results` baseline / `auto_stitch_materialization_audit_entries` / `auto_stitch_materialization_rollback_plans`，以及 `tests/test_native_web_runtime.py` 的 recon pipeline `workspace_flow_timeline`、manifest category、entry `correlation` 字段、`correlation_groups[].verification` 字段、`stitch_candidates[].automatic_stitching=false`、`auto_stitch_dry_runs[].would_materialize=false`、`auto_stitch_policy_decisions[].would_materialize=false`、未审批 `auto_stitch_materialization_plans[].writes_artifact=false`、已审批 `auto_stitch_materialization_results[].writes_artifact=true` 和 explicit `flow-timeline.json` / `auto-stitch-materialization-results.json` / `stitched-flow-materialization-audit.json` / `stitched-flow-rollback-plan.json` artifact 断言，且不得宣称已支持无需审批的自动全链路跨请求 materialization。
- 改 CLI / doctor / workflow：检查 `tests/test_doctor.py`、`tests/test_console_script.py`、`tests/test_run_demo*.py`、涉及 workspace dual-write smoke 时检查 `tests/test_workspace_dual_write_smoke.py`，并同步 README 和相关 docs。
- 改 rebuild / strategy：检查 `tests/test_rebuild_artifacts.py`、`tests/test_strategy_*`；涉及 StrategyDetector registry / plugin template / entry point 时，还必须检查 `tests/test_strategy_detector_registry.py`、`tests/test_strategy_detector_plugin_template.py`，并证明 metadata listing 不运行 detector、不采集 runtime context、不执行 replay、不启动浏览器、不 evaluate JS、不调用 MCP、不触碰移动端完整链路；涉及 `evidence_score`、review gate 或 delivery gate 消费时，还必须检查 `tests/test_review_gate.py`、`tests/test_review_subagent.py`，并证明 score 只读消费、不改变 rebuild `ready` 计算、不采集 runtime context、不执行 replay、不启动浏览器、不调用 MCP、不触碰移动端完整链路。

## 6. 规划与阶段化执行

- 用户提到 `plan`、`do-plan`、规划、继续推进、按顺序执行时，必须使用 `task-plan` 相关流程。
- 多步骤开发必须维护一个简洁计划，并随完成状态更新。
- 每个阶段完成后必须自检：
  - 相关代码是否都改到。
  - 文档是否同步。
  - 测试或静态检查是否覆盖关键路径。
  - 是否混入无关改动。
  - 是否引入乱码、错码、冲突标记或旧口径。
- 阶段自检未通过，不得进入下一阶段或提交。

## 7. 测试与验证

本仓库不是 npm / bun 项目。除非某个子任务明确涉及 Node 工具，否则不要套用 `npm test` / `bun test`。

代码改动最低验证：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m compileall -q "src/reverse_deepagent" "tests"
```

定向测试按改动范围选择，例如：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest tests.test_coordinator tests.test_doctor -v
```

跨模块、架构性、提交前全量回归：

```bash
"/Users/mengma/reverse/reverse_agent/.venv/bin/python" -m unittest discover -s tests -v
```

文档-only 改动最低验证：

```bash
git diff --check
```

并人工检查：

- 中文无乱码。
- 链接路径正确。
- 命令示例符合当前仓库实际。
- 没有把旧 `mcp` 默认路径、旧分支名、旧执行方式写回新文档。

测试失败时不得提交，除非用户明确要求保留失败状态用于排查；这种情况必须在回复中说明失败命令和失败原因。

## 8. Diff review 与提交前检查

提交前必须至少执行：

```bash
git status --short
git diff --stat
git diff --check
```

并根据任务范围查看完整 diff。

检查重点：

- 只包含本次任务相关文件。
- 没有临时调试代码。
- 没有无关格式化、无关重命名、生成物、缓存、runtime artifacts。
- 没有冲突标记：`<<<<<<<`、`=======`、`>>>>>>>`。
- 没有敏感信息：API key、cookie 值、Authorization、proxy 密码、真实 token。
- 文档和代码口径一致。

## 9. 文档同步规则

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

不要只在临时计划或聊天里说明，长期行为变化必须落到仓库文档。

## 10. AGENTS 与规范维护硬性要求

`AGENTS.md` 不是一次性文件，是本仓库 AI 协作的强制入口。任何会改变长期开发方式、模块边界、验证命令、运行时能力或提交流程的改动，都必须同步维护它。

维护规范时，优先复用本机可复用 skill：

- `$project-agents-governance`
- 路径：`/Users/mengma/.codex/skills/project-agents-governance`

必须更新 `AGENTS.md` 或重新核对它的场景：

- 新增、删除、重命名顶层目录、核心源码目录、测试目录、文档目录、脚本目录或运行产物目录。
- 新增或改变 runtime / backend / provider / collector / hook / breakpoint / artifact schema。
- 改变 BrowserProvider / CloakBrowser / legacy MCP 迁移口径。
- 改变 CLI 参数、doctor 行为、workflow、CI、测试命令或 console entrypoint。
- 改变默认分支、PR base、提交、推送、合并策略。
- 新增 Android、iOS、小程序、桌面端、云端任务等平台扩展边界。
- 发现 `AGENTS.md`、`项目开发规范（AI协作）.md`、`README.md`、`CONTRIBUTING.md`、`docs/` 或 `.codex/plans/` 之间存在冲突。

维护方式必须按下面顺序执行：

1. 先读取当前 `AGENTS.md`、两份流程规范和任务相关长期文档。
2. 再核对真实仓库结构、真实入口、真实测试命令和真实分支策略。
3. 使用 `$project-agents-governance` 的模板或脚本生成/对照规范草案。
4. 只保留符合本仓库真实情况的规则，删除模板里不适用的项目。
5. 保持已有文件编码和换行风格；尤其不要破坏中文文件的 BOM / CRLF。
6. 运行 `git diff --check`，并人工 review diff，确认没有旧项目口径、错路径、错分支、错命令和乱码。

禁止事项：

- 不得只在聊天记录里宣布长期规则变更，必须落到仓库文档。
- 不得把别的项目目录、测试命令、分支策略直接复制进本仓库。
- 不得加入没有可执行验证方式的空泛规则。
- 不得为了省事把过时的 `mcp` 主线、旧浏览器抽象或旧测试基线写回规范。

## 11. 大项目自动触发规范治理

满足任一条件时，必须自动触发“规范确认 / 计划 / 适配”阶段，先处理规范和计划，再进入代码实现：

- 任务预计改动 3 个及以上顶层目录。
- diff 预计超过 8 个文件，且同时涉及代码、测试、文档、workflow / CI 中至少 2 类。
- 任务涉及架构迁移、运行时拆分、浏览器底座替换、MCP 去耦、DeepAgents 子智能体编排、artifact schema、平台扩展。
- 用户要求“重构”“迁移”“拆掉”“可插拔”“长期维护”“大项目规范化”“多 agent 协同”。
- 当前规范无法解释将要做的改动，或现有规范与真实代码冲突。

自动触发后的最低动作：

1. 维护一个阶段化计划。
2. 明确本次是否需要更新 `AGENTS.md` 和 `项目开发规范（AI协作）.md`。
3. 如需要，先完成规范更新并通过 `git diff --check`。
4. 再继续代码实现、测试和文档同步。
5. 最终回复必须说明规范是否更新、为什么更新或为什么不需要更新。

## 12. Insight 使用规则

复杂根因分析、架构决策、关键功能实现、复杂 bug 修复时，可以使用固定格式：

```text
`★ Insight ─────────────────────────────────────`
- 要点 1
- 要点 2
- 要点 3
`─────────────────────────────────────────────────`
```

简单确认、常规配置、纯格式化、小文档改动不需要 Insight。

## 13. 表达风格

- 默认中文，专业简洁。
- 可以直接指出风险和盲区，不要讨好式附和。
- 可以有一点东北味儿，但不能牺牲信息密度。
- 不要写固定机器人腔，例如“自动回复”“AI 分析结果如下”。
- 结论必须基于真实文件、真实命令输出、真实 diff、真实测试结果。

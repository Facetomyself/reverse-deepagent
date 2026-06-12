# reverse-deepagent

[![CI](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml/badge.svg)](https://github.com/Facetomyself/reverse-deepagent/actions/workflows/ci.yml)

面向 Web / JavaScript 逆向流程的 DeepAgents 演示项目。项目聚焦本地、授权场景：归一化逆向任务、通过运行时适配器采集 Web 证据、验证候选签名函数，并生成 replay / rebuild 交付物。

> 当前发布线：`v0.1.x` 公开演示版稳定期。详见 [`CHANGELOG.md`](CHANGELOG.md) 与 [`ROADMAP.md`](ROADMAP.md)。
> BrowserProvider 架构与 MCP legacy 迁移：[`docs/runtime/browser-provider-architecture.md`](docs/runtime/browser-provider-architecture.md)、[`docs/runtime/cloakbrowser-provider.md`](docs/runtime/cloakbrowser-provider.md)、[`docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md`](docs/plans/2026-05-29-browser-provider-mcp-deprecation-plan.md)。
> MCP 运行时与自托管冒烟测试目前保留为 legacy 兼容路径：[`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)、[`docs/ci/self-hosted-mcp-smoke.md`](docs/ci/self-hosted-mcp-smoke.md)。
> 运行时适配器契约：[`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## 快速开始

```bash
git clone https://github.com/Facetomyself/reverse-deepagent.git
cd reverse-deepagent
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

运行确定性的 mock 流水线：

```bash
reverse-agent-demo --runtime mock
```

如果 shell 提示 `reverse-agent-demo: command not found`，说明当前终端还没有激活项目虚拟环境。可以先执行：

```bash
source "<repo-root>/.venv/bin/activate"
```

或者直接使用绝对路径：

```bash
"<repo-root>/.venv/bin/reverse-agent-demo" --runtime mock
```

运行本地 sign fixture 冒烟测试：

```bash
reverse-agent-fixture --check
reverse-agent-fixture-smoke --runtime mock --profile sha256
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

当前真实浏览器链路正在从 MCP 迁移到 BrowserProvider 架构：长期目标是 `native-web + BrowserProvider + native collectors`，MCP 保留为 legacy 兼容路径。

Native Web 运行时示例：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser playwright-chromium \
  --task-text "https://example.com 找 sign 入口"
```

如果还没有下载 Playwright 自带的 Chromium，也可以临时把 `--browser-executable-path` 指向系统 Chrome 做真实 smoke：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser playwright-chromium \
  --browser-executable-path "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --task-text "https://example.com 找 sign 入口"
```

如果本机已经有可用的 Chrome DevTools 端点，但还没有装 Playwright 或 CloakBrowser，`remote-cdp` 可以直接作为 BrowserProvider smoke 路径使用；它和 `chrome-cdp` 轻量探测后端不是一回事：前者接入 `native-web` 的采集栈，后者只是做端点探测。

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser remote-cdp \
  --cdp-browser-url "http://127.0.0.1:9555" \
  --task-text "http://127.0.0.1:8000/ 找 buildSign 入口"
```

对应的 doctor smoke 也支持显式指定端点：

```bash
reverse-agent-doctor \
  --browser remote-cdp \
  --browser-url "http://127.0.0.1:9555" \
  --launch-browser-smoke \
  --browser-smoke-url "about:blank"
```

CloakBrowser 作为可选 BrowserProvider 使用，安装方式如下：

```bash
uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cloak]"
```

运行示例：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-profile-dir "./profiles/example" \
  --task-text "https://example.com 查看登录态和关键请求"
```

如果已经有 CloakBrowser / cloakserve 暴露的 CDP endpoint，也可以显式走 connect baseline，不再由 agent 启动本地浏览器进程：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-url "http://127.0.0.1:9222" \
  --task-text "https://example.com 复用已有 CloakBrowser 会话检查关键请求"
```

本机已经验证过 `reverse-agent-doctor --browser cloakbrowser --launch-browser-smoke` 和 `reverse-agent-demo --runtime native-web --browser cloakbrowser` 的真实 smoke；如果要复现到别的机器，优先保证 `.[cloak]` 安装和 CloakBrowser 二进制可用。

BrowserProvider doctor 示例，默认不启动真实浏览器，也不依赖 MCP：

```bash
reverse-agent-doctor --browser cloakbrowser
```

如果只想看内置 BrowserProvider 能力 / lifecycle smoke matrix，而不导入可选依赖、不探测 CDP 端点、不启动浏览器：

```bash
reverse-agent-doctor --browser-provider-matrix
```

如果只想从 doctor 入口生成一条可审阅的显式 launch-smoke 命令，不检查 availability、不启动浏览器、不写 artifact、不调用 MCP：

```bash
reverse-agent-doctor \
  --browser cloakbrowser \
  --browser-url "http://127.0.0.1:9222" \
  --print-browser-launch-command
```

输出里的 `browser_provider_launch_command` 使用 `reverse-deepagent.browser-provider-launch-command.v1` schema，`review_command_hint.command` 会包含需要人工显式执行的 `--launch-browser-smoke`，并保留 `provider_factories_invoked=false`、`starts_browser=false`、`writes_artifact=false`、`calls_mcp=false`。

输出里的 `browser_provider_smoke_matrix` 由 `BrowserProviderRegistry` 驱动，会列出内置 `playwright-chromium`、`cloakbrowser`、`remote-cdp` 以及已安装 `reverse_deepagent.browser_providers` entry point plugin 的 capability flags、alias、supported modes、compatibility 结果、production readiness 结果和标准 lifecycle stages。metadata-only matrix 会读取 registration metadata 和 `describe()` 输出，但不调用 provider factory、不导入可选浏览器依赖、不探测 CDP 端点、不启动浏览器，也不依赖 MCP；compatibility validator 由可序列化 rule catalog 驱动，会检查 breakpoints/CDP、response body/network 或 CDP、persistent context/lifecycle，以及 proxy、humanize、mobile emulation、extensions 这类 capability flags 的自洽性；production readiness evaluator 只读 provider 声明的 `production_readiness` 元数据和 provider-specific readiness rule catalog，输出 `production-ready`、`review-required` 或 `metadata-incomplete`，用于区分 CloakBrowser 这类生产候选、Playwright / remote-cdp 这类需部署复核的 provider、fixture/template 这类非生产 runtime；当前 v5 rule catalog 支持 `required_metadata_keys`，会把 CloakBrowser 的 `stealth_policy`、Remote CDP / hosted-CDP / Browserless / Browserbase 的 endpoint / allocation / account boundary policy 缺失标成 `metadata-incomplete`，而不是只给泛泛 warning。matrix 会输出 `compatibility_rules`、`production_readiness_rules`、`rule_count`、`evaluated_rules`、`production_readiness_version` 和 summary 计数，单 provider doctor 输出会保留旧字段，并额外带 `browser_provider.smoke_matrix`，方便 CI 或人工 review 对比 provider 差异。

如果需要把单个 BrowserProvider smoke 证据落到 workspace，而不是只看 doctor stdout，可使用：

```bash
reverse-agent-browser-provider-smoke \
  --browser cloakbrowser \
  --artifact-root "<repo-root>/artifacts/browser-provider-smoke"
```

默认是 registry metadata-only：不调用 provider factory、不检查 availability、不启动浏览器、不调用 MCP，只写 `workspace/browser-provider-smoke.json`。artifact 会额外写入 redaction-safe `requested_provider_config` 和 `review_command_hint`：前者记录 connect / persistent profile / headless / humanize / proxy / locale / timezone / browser args 的脱敏摘要，后者给出复核或重新生成显式 launch smoke 的命令提示；这只是配置证据，不代表 runtime launch smoke 已通过。真实启动必须显式加 `--launch-browser-smoke`，例如：

如果只想先生成可复制的显式 launch-smoke 命令而不写 artifact、不 resolve provider、不检查 availability、不启动浏览器，可使用：

```bash
reverse-agent-browser-provider-smoke \
  --browser cloakbrowser \
  --browser-url "http://127.0.0.1:9222" \
  --artifact-root "<repo-root>/artifacts/browser-provider-smoke-cloak" \
  --print-launch-command
```

该命令只向 stdout 输出 `reverse-deepagent.browser-provider-launch-command.v1` JSON，里面的 `review_command_hint.command` 会包含 `--launch-browser-smoke`，但本次运行自身不会启动浏览器或写 `workspace/browser-provider-smoke.json`。

已生成的 smoke JSON 可以通过 `reverse-agent-browser-provider-smoke --review-smoke-json` 或 `reverse-agent-demo --browser-provider-smoke-json` 做复核 / 附加。复核输出的外层 `attachment_acceptance` 使用 `reverse-deepagent.browser-provider-smoke-acceptance.v1`，其中嵌套的 `acceptance_report` 使用 `reverse-deepagent.browser-provider-smoke-acceptance-report.v1`；metadata-only / availability-check 证据可以作为 provider 配置证据附加，但只有匹配 provider 且通过 side-effect 边界检查的 `launch-smoke` 证据才会被标记为 `runtime_launch_smoke_accepted=true`。

```bash
reverse-agent-browser-provider-smoke \
  --browser cloakbrowser \
  --launch-browser-smoke \
  --browser-smoke-url about:blank \
  --artifact-root "<repo-root>/artifacts/browser-provider-smoke-cloak"
```

如果要把已经生成并审阅过的 smoke 证据附加到一次 Web pipeline 输出里，可把该 JSON 显式传给 `reverse-agent-demo`：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-provider-smoke-json "<repo-root>/artifacts/browser-provider-smoke-cloak/workspace/browser-provider-smoke.json" \
  --artifact-root "<repo-root>/artifacts/native-web-with-provider-smoke"
```

`--browser-provider-smoke-json` 只读取现有 UTF-8 JSON object，并把它写入本次 pipeline 的 `workspace/browser-provider-smoke.json`、`exports/artifact-index.json` 和 `workspace/backend-artifact-manifest.json`；写入前会追加 metadata-only `attachment_acceptance`，检查 schema、`ok`、side-effect policy、resolved provider 与当前 BrowserProvider runtime provider 是否匹配，以及 launch-smoke 模式是否真有 passed smoke result。`attachment_acceptance.acceptance_report` 使用 `reverse-deepagent.browser-provider-smoke-acceptance-report.v1`，会把 evidence level、provider summary、side-effect summary、blockers / warnings 和 required follow-up 固化成 reviewer 可读的审计报告。metadata-only / availability-check evidence 可以作为 provider metadata evidence 附上，但 `runtime_launch_smoke_accepted=false`，不会被误称为 launch smoke 通过；provider 不匹配、schema 错误、`ok=false`、MCP / mobile full-chain side effect 或非 launch-smoke 模式启动浏览器会被标成 blocked。这个路径不会生成 smoke、不会调用 provider factory、不会检查 availability、不会启动浏览器、不会探测 CDP 端点，也不会调用 MCP。

只想独立审计一个既有 smoke JSON，而不跑完整 pipeline 时，可使用 standalone review 模式：

```bash
reverse-agent-browser-provider-smoke \
  --review-smoke-json "<repo-root>/artifacts/browser-provider-smoke-cloak/workspace/browser-provider-smoke.json" \
  --expected-provider cloakbrowser
```

该模式只读 JSON 并输出 `reverse-deepagent.browser-provider-smoke-review.v1`，内含同样的 `attachment_acceptance` / `acceptance_report`；它不写 artifact、不 resolve provider、不调用 provider factory、不检查 availability、不启动浏览器、不探测 CDP，也不调用 MCP。

如果要把这份既有 smoke evidence 作为 CI / PR gate，可以在同一个只读 review 模式里加 evidence policy：

```bash
reverse-agent-browser-provider-smoke \
  --review-smoke-json "<repo-root>/artifacts/browser-provider-smoke-cloak/workspace/browser-provider-smoke.json" \
  --expected-provider cloakbrowser \
  --minimum-evidence-level launch-smoke
```

`--minimum-evidence-level` 支持 `metadata-only`、`availability-check` 和 `launch-smoke`。输出里的 `policy_decision` 使用 `reverse-deepagent.browser-provider-smoke-policy-decision.v1`，会给出 `decision=pass|warn|block`、`policy_passed`、observed / required evidence level、blockers 和 warnings。默认 metadata-only evidence 可以作为配置证据通过只读 review，但会以 `decision=warn` 暴露 `runtime_launch_smoke_accepted=false`；要求 `launch-smoke` 时，metadata-only / availability-check evidence 会被 `insufficient_browser_provider_smoke_evidence_level` 阻断。`--block-on-warnings` 可把 warning 升级为 blocking policy，方便严格 CI 使用。这个 policy gate 只消费既有 JSON，不生成 smoke、不调用 provider factory、不检查 availability、不启动浏览器、不探测 CDP、不写 artifact、不调用 MCP。

仓库还提供专用 PR / CI gate 入口，默认要求 `launch-smoke`：

```bash
reverse-agent-browser-provider-smoke-policy \
  --smoke-json "<repo-root>/artifacts/browser-provider-smoke-cloak/workspace/browser-provider-smoke.json" \
  --expected-provider cloakbrowser
```

该入口输出 `reverse-deepagent.browser-provider-smoke-policy-gate.v1`，policy 通过时 exit code 为 `0`，阻断时为 `2`。默认 public CI 使用 `tests/fixtures/browser-provider-smoke/` 下的固定 evidence samples 验证 metadata-only 必须被 launch-smoke gate 阻断、launch-smoke fixture 必须通过；不会启动真实浏览器。细节见 [`docs/ci/browser-provider-smoke-policy.md`](docs/ci/browser-provider-smoke-policy.md)。

Native Web 的 CDP WebSocket frame 采集是 **post-attach-only**：只有在导航或目标 socket 流量发生前预先 attach `CDPEventCacheCollector`，才能从 `Network.webSocketFrameSent` / `Network.webSocketFrameReceived` 事件拿到帧；没有预订阅、预订阅后未观察到帧或 provider 不支持 CDP event subscription 时，collector 会输出 `websocket_event_cache_required_before_navigation`、`websocket_event_cache_attached_no_frames_observed`、`cdp_event_subscription_unavailable` 或 `network_domain_unavailable` 等结构化诊断，并固定 `historical_replay_supported=false`。这不是历史 WebSocket frame replay；需要补证据时应提前 attach CDP event cache，或启用 runtime WebSocket hook timeline fallback。

仓库还提供六个外部 BrowserProvider package：[`packages/reverse-deepagent-browser-provider-template/`](packages/reverse-deepagent-browser-provider-template/) 是通用 copy-and-replace 模板，声明 `template-browser` entry point 并故意让 `start()` / `connect()` 报 unavailable，证明 metadata-only 注册不会启动浏览器、探测 CDP 或调用 provider factory；[`packages/reverse-deepagent-browser-provider-hosted-cdp-template/`](packages/reverse-deepagent-browser-provider-hosted-cdp-template/) 是托管浏览器服务 / hosted CDP 接入模板，声明 `hosted-cdp-template` entry point，metadata-only 路径不分配远端会话，显式传入 `browser_url` 时可复用 `RemoteCDPProvider` 做 contract smoke；[`packages/reverse-deepagent-browser-provider-hosted-cdp-reference/`](packages/reverse-deepagent-browser-provider-hosted-cdp-reference/) 是 hosted CDP reference provider，声明 `hosted-cdp-reference` entry point，用 in-memory reference allocator 建模 allocation / attach / release lifecycle、idempotent stop、secret-safe metadata 和 launch smoke，可作为真实 browser-service / anti-detect browser / enterprise browser pool provider 的生产形态参考，但仍不是 vendor SDK；[`packages/reverse-deepagent-browser-provider-browserless-cdp/`](packages/reverse-deepagent-browser-provider-browserless-cdp/) 是 Browserless / hosted CDP 真实 provider package baseline，声明 `browserless-cdp` entry point，metadata-only 路径不探测 Browserless、不读取凭据、不调用 factory，显式传入 HTTP DevTools endpoint 时复用 `RemoteCDPProvider`，显式传入 direct browser WebSocket endpoint 时走最小 Target / Page / Runtime CDP wrapper；[`packages/reverse-deepagent-browser-provider-browserbase-cdp/`](packages/reverse-deepagent-browser-provider-browserbase-cdp/) 是 Browserbase hosted CDP 真实 provider package baseline，声明 `browserbase-cdp` entry point，metadata-only 路径不读取 API key、不创建 session、不打开 socket，显式传入 reviewed `connectUrl` 时 attach 到 Browserbase CDP WebSocket，显式 `start()` 时才调用 Session API 获取 `connectUrl`；[`packages/reverse-deepagent-browser-provider-fixture/`](packages/reverse-deepagent-browser-provider-fixture/) 是可运行 fixture provider，声明 `fixture-browser` entry point，能返回 provider-neutral in-memory session/page，用于 CI、doctor 风格 launch smoke 和第三方插件 contract 验证。接入自定义浏览器、反检测浏览器或托管 CDP 服务时，优先做外部 package，而不是把新 provider 硬编码进 core runtime。

ExternalDeliveryProvider doctor 示例，默认只读取 provider registration metadata，不调用 provider factory，不上传、不推送、不发布，也不依赖 MCP / Chrome：

```bash
reverse-agent-doctor --external-delivery-providers
```

输出里的 `external_delivery_provider_matrix` 会列出 `review-only`、`local-archive`、`webhook`、`presigned-object`、`github-release` 及其 alias，并显示 `reverse_deepagent.external_delivery_providers` entry point group、provider transport、`review_only`、`supports_external_delivery` 和 side-effect policy。当前内置 provider 已覆盖 review-only handoff、本地归档、HTTP JSON webhook、presigned object-storage URL 的 HTTP PUT baseline，以及 GitHub Release JSON asset upload / 显式 existing-release reuse / 同名 asset preflight block baseline；GitHub Release provider 在发现同名 asset 时会生成 secret-safe `existing_asset_overwrite_plan`，列出 delete + replacement upload 的人工审批要求和 partial-failure plan；显式配置 `approve_existing_asset_delete=true`、`approve_replacement_upload=true` 且可选 `expected_existing_asset_id` 匹配时，才会先发送 DELETE 删除旧 asset，再上传 replacement asset。webhook、presigned object-storage 与 GitHub Release provider 提供默认关闭的显式 retry baseline，并记录 secret-safe Retry-After、rate-limit、retry budget 和 jitter metadata；`retry_attempts=0`、`retry_backoff_seconds=0`、`retry_jitter_seconds=0` 仍是默认保守策略，Retry-After 默认会被解析和记录，但只有显式 backoff 产生 planned delay 时才会 sleep。external delivery apply 还会写 append-only `external-delivery-idempotency-ledger.json`，记录 transaction id、idempotency key、provider id、duplicate guard 与 retry / rate-limit attempt summary。provider-specific Retry-After / rate-limit / retry budget metadata baseline 已内置；更高级的自适应 retry budget、GitHub secondary rate-limit policy 和第三方 release provider 仍以后续 provider 演进或插件形式接入。

仓库还提供 ExternalDeliveryProvider 插件模板包 [`packages/reverse-deepagent-external-delivery-provider-template/`](packages/reverse-deepagent-external-delivery-provider-template/)，声明 `reverse_deepagent.external_delivery_providers` entry point，并用 `template-external-delivery` 示例证明 metadata-only 注册不会调用 provider factory、不会打开 socket、不会读取 credentials、不会上传或发布。接入 S3 / OSS / GCS / GitLab Release / 内部发布系统时，优先复制这个包，替换 `deliver()`，保留 dry-run side-effect-free、secret redaction、duplicate guard 和 review gate 语义。默认模板在 dry-run 返回 plan，在 apply 返回 blocked，避免误把 scaffold 当真实 provider 发布。

StrategyDetector 也已拆出可插拔 registry：`reverse_deepagent.strategies.build_default_strategy_detector_registry()` 会注册内置 `builtin-algorithm-strategy` provider，并可加载 `reverse_deepagent.strategy_detectors` entry point。仓库提供 [`packages/reverse-deepagent-strategy-detector-template/`](packages/reverse-deepagent-strategy-detector-template/) 作为 copy-and-replace 起点，声明 `template-strategy-detector`，证明 metadata-only 注册只暴露 rule / emits / side-effect policy，不运行 detector、不采集 runtime context、不执行 replay、不启动浏览器、不 evaluate JavaScript、不调用 MCP，也不触碰移动端完整链路。接入站点私有签名 detector 时，优先复制这个包，替换纯源码模式识别逻辑，而不是把 vendor 规则硬编码回 core。

RuntimeBackend doctor 示例，默认只读取 runtime backend registration metadata，不调用 backend factory，不启动 Chrome / MCP / 平台工具：

```bash
reverse-agent-doctor --runtime-backends
```

输出里的 `runtime_backend_matrix` 会列出 `mock`、`native-web`、`remote-cdp`、轻量 Web backend、平台 minimal backend 以及已安装 entry point plugin 的 backend id / alias / target platforms / capability flags，并显示 `reverse_deepagent.runtime_backends` entry point group、summary counts 和 side-effect policy。未安装 `reverse-deepagent-legacy-mcp` 时不会伪装存在 `legacy-mcp`；需要 legacy MCP 时应安装 optional plugin 或继续使用 `native-web`。

Delivery transaction doctor 示例，只读取 delivery root 中的 transaction artifacts，不执行恢复、提交或外部发布，也不依赖 MCP / Chrome：

```bash
reverse-agent-doctor --delivery-transaction-root "artifacts/<run>/delivery"
```

输出里的 `delivery_transaction` 复用 `evaluate_delivery_transaction_state(...)` / `plan_delivery_transition(...)`，包含 `state_snapshot`、`transition_plan`、各标准 artifact 的 exists / loaded / keys / error 状态、`missing_artifacts`、`load_errors` 和 read-only side-effect policy。它会读取 `delivery-transaction-journal.json`、`external-delivery-result.json`、`external-delivery-idempotency-ledger.json`、`backend-artifact-manifest-recovery-preflight.json`、`backend-artifact-manifest-recovery.json` 与 `backend-artifact-manifest-transaction-commit.json`；这是 inspector，不会执行副作用；真正执行 recovery workflow 需走显式 `DeliveryTransactionRecoveryExecutor` / `execute_delivery_recovery`，它仍不是 cross-run rollback state machine、transaction commit executor 或 external delivery provider。

Delivery transaction lock provider contract 现在由 delivery subagent 的 `manage_delivery_transaction_lock_provider` 暴露：tool 默认 provider 仍是 `local-file-lock`，默认 registry 还内置 `sqlite-lock`（alias：`db-lock` / `sqlite-transaction-lock` / `local-db-lock`）和 `redis-lock`（alias：`redis` / `redis-lease-lock` / `external-redis-lock`），支持 `inspect_lock`、`acquire_lock`、`renew_lock`、`release_lock`。`local-file-lock` apply 模式写 `delivery-distributed-transaction-lock.json` 与 `delivery-distributed-transaction-lock-operation.json`；`sqlite-lock` 用本地 SQLite `delivery-distributed-transaction-lock.sqlite3` 作为权威 transactional store，并继续写同名 JSON projection 与 operation record；`redis-lock` 用外部 Redis key 作为权威 lease store，apply 才联系 Redis，并继续写本地 JSON projection / operation record；dry-run 只返回计划且不联网。这个 baseline 用于稳定 `reverse_deepagent.delivery_lock_providers` entry point 和 lease / fencing token artifact 语义，不替换 `LocalDeliveryExecutor` 现有的 `delivery-transaction-lock.json` gate；SQLite provider 只序列化同一可靠本地 / 共享数据库文件上的 writer，Redis provider 语义取决于部署，不实现 Redlock quorum consensus。下游 side-effect gate 现在可显式传入 `expected_transaction_lock_fencing_token`，要求本地 `delivery-distributed-transaction-lock.json` projection 中的 fencing token 匹配且未过期后才继续复制 artifact、mutate manifest、recovery、commit 或 external delivery；这仍不是自动全局 fencing enforcement，也不替代调用方选择正确 provider lock record。

Delivery resume workflow scheduler 现在由 delivery subagent 的 `execute_delivery_resume_workflow` 暴露：支持 `plan_workflow` 与 `execute_workflow`，可把 `preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery`、`commit_cross_run_transaction` 这类显式 runner step 串成 review-gated workflow，也可把 `acquire_delivery_transaction_lock_provider`、`renew_delivery_transaction_lock_provider`、`release_delivery_transaction_lock_provider` 作为显式 provider lock lifecycle step 调用配置的 lock provider `acquire_lock` / `renew_lock` / `release_lock`；dry-run 只规划，apply 必须为每个 pending step 匹配 `review-approval-ledger.json`，并写 `delivery-resume-workflow.json` 与 append-only `delivery-resume-workflow-journal.json`。它会复用 `DeliveryResumeRunner` / `DeliveryTransactionTransitionExecutor` 的既有 digest、journal、lock 和 idempotency checks，lock provider step 会记录 `delivery-distributed-transaction-lock-operation.json` 与 journal 中的 provider / fencing token / lease expires evidence，并可跳过 journal 中已完成的 step；同一次 workflow execution 内成功 acquire / renew 的 fencing token 可传播给后续 runner step，resume-of-resume 时可从同 transaction journal 保守 replay 未过期 token，跳过任意已完成 step 会附带只读 `journal_replay` 摘要。规划阶段还会生成 `lock_lifecycle_plan`、`lease_renewal_plan` 与 `workflow_readiness_plan`：`lock_lifecycle_plan` 只在默认 workflow planning 中根据 provider projection / journal evidence 建议 reviewed acquire / release，例如缺少 provider lock evidence 的 recovery workflow 可前置 `acquire_delivery_transaction_lock_provider`，terminal transaction 仍有 provider lock evidence 时可只规划 `release_delivery_transaction_lock_provider`；`lease_renewal_plan` 读取 `delivery-distributed-transaction-lock.json` projection 与 workflow journal lease evidence，当已有 fencing token 的 lease 已过期或进入 `lease_renewal_warning_seconds` 窗口时，可前置 `renew_delivery_transaction_lock_provider`；`workflow_readiness_plan` 聚合 planned steps、approval summary、checks、blocking reasons、lock / lease planning 与 journal replay context，输出 `ready_for_review` / `ready_to_execute` / `blocked` / `no_steps`、缺失 approval action、是否需要 lock provider / fencing review 和下一步 review action；其中 `runtime_gate_evidence_projection` 会只读投影 transaction journal、rollback checkpoint、recovery preflight、provider lock projection、local transaction lock、terminal commit record 与 backend manifest 的 observed / missing / malformed / stale / transaction mismatch 状态；`step_dependency_contexts` 会逐步列出 approval、串行 predecessor、journal replay、provider lock、fencing、recovery preflight、底层 runtime gate 复核要求以及 per-step `runtime_gate_evidence`，并明确区分已 journal 完成、计划内前序可提供、artifact 目前可观察到和执行时仍需重验。这些 planning 仍必须通过对应 `resume_acquire_*` / `resume_renew_*` / `resume_release_*` review approval 后才会执行；规划不联系 provider、不写 operation artifact、不后台续租、不启动 daemon、不自动 acquire / release、不自动 stale takeover，也不是 automatic lock lifecycle manager 或 workflow daemon。

需要真实启动 smoke 时显式打开：

```bash
reverse-agent-doctor \
  --browser cloakbrowser \
  --launch-browser-smoke \
  --browser-smoke-url "about:blank"
```

legacy MCP 浏览器集成仍可用于真实 smoke，需要本机 JSReverser MCP 可执行文件和 Chrome 调试环境。环境假设与故障排查见 [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)。公开 CI 不默认运行 legacy MCP 链路，而是隔离在手动 `MCP Integration` 工作流中。本地建议优先使用受管 Chrome 启动器：

```bash
reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9461"
```

## DeepAgents `/memories/` 长期记忆

`build_reverse_agent(...)` 现在默认在 DeepAgents `CompositeBackend` 中启用 `/memories/` 路由：

- `/workspace/`：DeepAgents 默认 `StateBackend`，适合当前任务临时草稿。
- `/artifacts/`：`FilesystemBackend`，映射到本地 artifact root，适合人工检查的报告和交付物。
- `/memories/`：`StoreBackend`，适合跨 agent / 跨会话复用的长期逆向经验。

默认开发环境使用进程内 `InMemoryStore`；需要跨 agent 实例共享时，可以显式传入同一个 `memory_store` 和 `memory_namespace`：

```python
from langgraph.store.memory import InMemoryStore
from reverse_deepagent.agent import build_reverse_agent

memory_store = InMemoryStore()
agent = build_reverse_agent(
    model=model,
    artifact_root="artifacts/demo",
    memory_store=memory_store,
    memory_namespace=("reverse-deepagent", "project-a", "memories"),
)
```

`/memories/` 只应该保存可复用经验，例如：

- `/memories/sites/example.com.md`：站点级入口、路由、常见接口命名。
- `/memories/protections/debugger-loop.md`：已验证的 protection 处理经验。
- `/memories/patterns/x-sign.md`：参数命名、签名函数命名、上下文依赖模式。

不要把未验证的一次性抓包、候选源码、临时 todo 写入 `/memories/`；这些仍应留在 `/workspace/` 或 `/artifacts/`。

## DeepAgents workspace contract

每次 deterministic pipeline 现在都会额外输出 `workspace/workspace-contract.json`，用于把 DeepAgents 子智能体、middleware checkpoint 和 workspace artifact 路由固化成机器可读契约。这个文件当前保持 **indexed-only** contract，同时 `workspace/backend-artifact-manifest.json` 会为已登记 workspace artifact 提供 manifest-only foldered alias：

- 现有 `workspace/*.json` 扁平 artifact 路径仍是 canonical path，不会被自动迁移。
- `artifact_routes[].virtual_folder` 和 `artifact_routes[].future_path` 表示虚拟文件夹组织目标。
- manifest entry 的 `metadata.workspace_alias` 会记录 `canonical_path`、`canonical_uri`、`virtual_folder`、`future_path`、`virtual_uri`、`producer_roles`、`migration_status=manifest-alias-only` 和 `resolver_migration_status=resolver-only`，让消费者可以先读取 `/workspace/<area>/...` 语义而不要求物理迁移。
- `WorkspacePathResolver` 可以按 artifact key、legacy path、future path 或 `virtual://workspace/...` URI 解析同一 artifact；默认 `write_paths` 只包含 legacy canonical path；pipeline 显式 `enable_workspace_dual_write=True` 时会同时写 legacy path 与 `artifact_root/workspace/<area>/...` foldered future path，并输出 `workspace/workspace-dual-write-plan.json` / `reverse-deepagent.workspace-dual-write-plan.v1` 审计记录；如果同时传入 `workspace_dual_write_artifact_keys` 或 CLI 的 `--workspace-dual-write-artifact-keys`，则只对审阅过的 artifact key 做 future-path 双写，其他 registered artifact 保持 legacy-only 并在 audit record 中标为 out-of-scope；这些路径演进仍不移动旧文件、不改变 authoritative path。
- `read_workspace_artifact` 现在作为 coordinator 与 review / rebuild / timeline / hook / debugger 子智能体的只读工具，可按 artifact key、legacy path、future path、`virtual://workspace/...` URI 或 artifact-root-relative fallback 读取现有 workspace artifact；读取结果会附带 `resolver_metrics`，标记 ref 类型、命中的 legacy / future / direct 路径、checked path count、future fallback 和 direct fallback 状态，用于后续 dual-write / migration pilot 的兼容性判断；timeline / hook / debugger / rebuild / review gate 专项工具也可直接接受 artifact-ref 输入并返回 `artifact_input` 读取诊断；`execute_local_delivery` 的 artifact list 也可用 `source_artifact_ref` / `artifact_ref` 解析 reviewed source artifact 后再进入原有 dry-run / apply gate，并在每个 artifact metadata 与顶层 `delivery_artifact_source_audit` 中输出 source compatibility audit，区分 resolver-backed artifact ref、legacy / future workspace source path、artifact-root-relative path、relative path 与 external filesystem source path；这些 resolver / audit 路径不会创建目录、启用双写、迁移路径、启动浏览器或调用 MCP，delivery apply 仍必须显式 `mode=apply` 并通过既有 gate。
- `audit_workspace_artifact_consumers` 现在作为 coordinator 只读工具提供 workspace consumer adoption matrix，用 `resolver-ready`、`partial`、`candidate`、`explicit-filesystem-boundary` 和 `non-workspace-input` 区分已接入 resolver、可后续接入和必须保持显式 filesystem path 的输入；`assess_workspace_migration_readiness` 进一步把 consumer audit、registered workspace route 数量和可选 `delivery_artifact_source_audit` JSON 聚合成 workspace migration readiness report，分别评估 limited dual-write pilot 与 foldered-canonical migration 的 review 状态、blocking reasons 和 next actions；`assess_workspace_consumer_readiness_score` 会消费 consumer audit、migration readiness、可选 delivery source audit 和可选 dual-write pilot result，输出 `reverse-deepagent.workspace-consumer-readiness-score.v1`，包括 resolver adoption、virtual URI adoption、future path readiness、source_path risk、dual-write pilot evidence 和 foldered-canonical readiness 分数，用于 review 下一批 dual-write expansion 或窄 foldered-canonical migration pilot；`plan_workspace_dual_write_expansion` 会消费该 score、可选 verified pilot result 和可选 reviewed artifact keys，输出 `reverse-deepagent.workspace-dual-write-expansion-plan.v1`，在没有 verified pilot evidence 时阻断 broader expansion，只返回下一批 opt-in scope 和 review action；`review_workspace_dual_write_expansion_workflow` 会把 ready expansion plan 和可选 observed `workspace-dual-write-plan.json` 串成 `reverse-deepagent.workspace-dual-write-expansion-workflow.v1` 审阅工作流：没有观测到 expansion 输出时返回 `ready_for_review`，观测到显式 scoped expansion 输出后可报告 `verified` / `partial` / `blocked`，并给出单独运行 reviewed scoped dual-write pipeline、复核结果和记录审计 artifact 的 review steps；`record_workspace_dual_write_expansion_result` 会在显式 expansion 运行后检查 planned legacy / future 文件存在性和 sha256 一致性，默认只读，只有 `write_result=true` 时才写 `workspace/workspace-dual-write-expansion-result.json` 审计结果；`plan_workspace_foldered_canonical_migration_pilot` 会消费 ready foldered-canonical readiness score 与 verified expansion result，输出 `reverse-deepagent.workspace-foldered-canonical-migration-pilot-plan.v1` 的窄迁移 review plan，只列出已验证 artifact 的 future canonical path 候选和 rollback 预检要求，不移动文件、不改变 canonical path；`review_workspace_foldered_canonical_migration_preflight` 会在 reviewed pilot plan 之后读取既有 legacy / future candidate 文件，验证文件存在性与 sha256 一致性，输出 `reverse-deepagent.workspace-foldered-canonical-migration-preflight.v1` 和 `workspace/workspace-foldered-canonical-migration-preflight.json` 的 rollback / execution gate 描述符，但仍不创建目录、不写 artifact、不 mutate manifest、不迁移路径、不改变 canonical path；`plan_workspace_foldered_canonical_migration_apply` 会消费 ready preflight，输出 `reverse-deepagent.workspace-foldered-canonical-migration-apply-plan.v1` 和 `workspace/workspace-foldered-canonical-migration-apply-plan.json` 的 reviewed apply plan、manifest mutation guard、rollback requirement 与 compatibility guard，只规划 separate apply executor 的输入，不检查文件、不写 artifact、不创建目录、不 mutate manifest、不迁移路径、不改变 canonical path；`plan_workspace_foldered_canonical_migration_approval` 会消费 ready apply plan，输出 `reverse-deepagent.workspace-foldered-canonical-migration-approval-plan.v1` 和 `workspace/workspace-foldered-canonical-migration-approval-plan.json` 的 approval ledger requirement、transaction journal plan、idempotency guard、stale apply-plan / preflight / digest guard、manifest dry-run requirement、rollback checkpoint requirement、post-apply validation requirement 与 compatibility fallback window，只规划 separate apply executor 的审批 / 事务输入，不记录 approval、不写 journal、不检查文件、不写 artifact、不创建目录、不 mutate manifest、不迁移路径、不改变 canonical path；`review_workspace_foldered_canonical_migration_manifest_dry_run` 会消费 ready approval plan、matching apply plan 和当前 backend artifact manifest，输出 `reverse-deepagent.workspace-foldered-canonical-migration-manifest-dry-run.v1` 与 `workspace/workspace-foldered-canonical-migration-manifest-dry-run.json` 的 manifest canonical-path promotion dry-run、apply-plan digest guard、rollback checkpoint plan 和 separate executor gate，只做内存 preview，不写 dry-run artifact、不写 rollback checkpoint、不 mutate backend manifest、不迁移路径、不改变 canonical path；`review_workspace_foldered_canonical_migration_physical_apply_preflight` 会消费 ready manifest dry-run、matching apply plan、review approval ledger evidence 和可选 rollback checkpoint evidence，输出 `reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-preflight.v1` 与 `workspace/workspace-foldered-canonical-migration-physical-apply-preflight.json` 的 explicit executor gate、approval ledger match、rollback checkpoint gate、transaction journal plan、idempotency guard 和 post-apply validation requirement，只做只读 preflight，不写 journal、不写 checkpoint、不 mutate manifest、不迁移路径、不改变 canonical path；`execute_workspace_foldered_canonical_physical_apply` 默认 dry-run，显式 `mode=apply` + `approve_physical_apply=true` 且 preflight / dry-run / apply-plan / backend manifest digest 与 path gate 通过后，写 `workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json`、append-only `workspace/workspace-foldered-canonical-migration-physical-apply-journal.json`、`workspace/workspace-foldered-canonical-migration-physical-apply-result.json` 并更新 `workspace/backend-artifact-manifest.json` canonical path；它不移动 workspace 文件、不收紧 legacy fallback、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_migration_post_apply_validation` 会消费 ready manifest dry-run、matching apply plan 和观测到的 post-apply backend artifact manifest，输出 `reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation.v1` 与 `workspace/workspace-foldered-canonical-migration-post-apply-validation.json` 的 canonical-path promotion validation、digest guard、compatibility validation 和 legacy fallback review gate，只做只读审阅，不写 validation artifact、不收紧 legacy fallback、不 mutate manifest、不迁移路径、不改变 canonical path；`record_workspace_foldered_canonical_migration_post_apply_validation_result` 会消费 ready post-apply validation descriptor，默认只读，只有 `write_result=true` 时才写 `workspace/workspace-foldered-canonical-migration-post-apply-validation-result.json` 审计结果；它不 mutate manifest、不收紧 legacy fallback、不做 finalization；`review_workspace_foldered_canonical_legacy_fallback_tightening_readiness` 会消费 verified post-apply validation result 和 ready workspace consumer readiness score，输出 `reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1` 与 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-readiness.json` 的只读 readiness descriptor，只允许后续单独 reviewed tightening plan，不写 artifact、不 mutate manifest、不收紧 fallback、不 finalization；`plan_workspace_foldered_canonical_legacy_fallback_tightening` 会消费 ready tightening readiness descriptor 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-plan.v1` 与 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-plan.json` 的 review-only apply plan、approval requirement、transaction journal plan 和 executor gate，不写 artifact、不 mutate manifest、不收紧 fallback、不 finalization；`review_workspace_foldered_canonical_legacy_fallback_tightening_preflight` 会消费 ready tightening plan、当前 backend manifest 和 review approval ledger，输出 `reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-preflight.v1` 与 `workspace/workspace-foldered-canonical-legacy-fallback-tightening-preflight.json` 的 read-only executor preflight、plan digest guard、approval gate、manifest revalidation、transaction journal plan 和 idempotency guard，不写 artifact、不写 journal、不 mutate manifest、不收紧 fallback、不 finalization；`execute_workspace_foldered_canonical_legacy_fallback_tightening` 默认 dry-run，显式 `mode=apply` + `approve_legacy_fallback_tightening=true` 且 preflight / plan / backend manifest digest 与 metadata gate 通过后，写 append-only `workspace/workspace-foldered-canonical-legacy-fallback-tightening-journal.json`、`workspace/workspace-foldered-canonical-legacy-fallback-tightening-result.json` 并更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` legacy fallback 状态；它不移动 workspace 文件、不改变 canonical path、不做 foldered-canonical finalization、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_migration_finalization_readiness` 会消费 applied legacy fallback tightening result 和当前 backend artifact manifest，输出 `reverse-deepagent.workspace-foldered-canonical-migration-finalization-readiness.v1` 与 `workspace/workspace-foldered-canonical-migration-finalization-readiness.json` 的 read-only finalization readiness descriptor、manifest alias revalidation 和 separate finalization plan gate，不写 artifact、不 mutate manifest、不改变 canonical path、不执行 finalization、不运行 pipeline、不启动浏览器或调用 MCP；`plan_workspace_foldered_canonical_migration_finalization` 会消费 ready finalization readiness descriptor 和当前 backend artifact manifest，输出 `reverse-deepagent.workspace-foldered-canonical-migration-finalization-plan.v1` 与 `workspace/workspace-foldered-canonical-migration-finalization-plan.json` 的 review-only finalization plan、planned metadata update preview、approval requirement、transaction journal plan 和 preflight / executor gate，不写 artifact、不 mutate manifest、不改变 canonical path、不执行 finalization、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_migration_finalization_preflight` 会消费 ready finalization plan、当前 backend manifest 和 review approval ledger，输出 `reverse-deepagent.workspace-foldered-canonical-migration-finalization-preflight.v1` 与 `workspace/workspace-foldered-canonical-migration-finalization-preflight.json` 的 read-only executor preflight、plan digest guard、approval gate、manifest revalidation、transaction journal plan 和 idempotency guard，不写 artifact、不写 journal、不 mutate manifest、不改变 canonical path、不执行 finalization、不运行 pipeline、不启动浏览器或调用 MCP；`execute_workspace_foldered_canonical_migration_finalization` 默认 dry-run，显式 `mode=apply` + `approve_finalization=true` 且 finalization preflight / plan / backend manifest digest、approval gate、manifest revalidation 和 idempotency guard 通过后，写 append-only `workspace/workspace-foldered-canonical-migration-finalization-journal.json`、`workspace/workspace-foldered-canonical-migration-finalization-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` finalization 状态；它不移动 workspace 文件、不改变 canonical path、不收紧 legacy fallback、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_migration_post_finalization_audit` 会消费 applied finalization result、finalization journal 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-migration-post-finalization-audit.v1` 与 `workspace/workspace-foldered-canonical-migration-post-finalization-audit.json` 的只读 transaction / journal / workspace_alias / canonical path stability 审计，不写 artifact、不 mutate manifest、不授权 broader rollout、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_broader_rollout_readiness` 会消费 verified post-finalization audit、workspace consumer readiness score、fresh delivery source audit、verified dual-write expansion result 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-readiness.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-readiness.json` 的只读 broader rollout readiness gate，只允许后续单独 reviewed rollout plan，不写 artifact、不 mutate manifest、不授权 apply、不启用 dual-write、不运行 pipeline、不启动浏览器或调用 MCP；`plan_workspace_foldered_canonical_broader_rollout` 会消费 ready broader rollout readiness descriptor 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-plan.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-plan.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-plan.json` 的 review-only broader rollout scope、digest guard、approval requirement 和 preflight / executor gate，不写 artifact、不 mutate manifest、不改变 canonical path、不启用 dual-write、不授权 apply、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_broader_rollout_preflight` 会消费 ready broader rollout plan、当前 backend manifest 和 review approval ledger，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-preflight.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-preflight.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-preflight.json` 的 read-only executor preflight、plan digest guard、approval gate、manifest revalidation、transaction journal plan、idempotency guard 和 result artifact plan，不写 artifact、不写 journal、不 mutate manifest、不改变 canonical path、不启用 dual-write、不执行 broader rollout apply、不运行 pipeline、不启动浏览器或调用 MCP；`execute_workspace_foldered_canonical_broader_rollout` 默认 dry-run，显式 `mode=apply` + `approve_broader_rollout=true` 且 broader rollout preflight / plan / backend manifest artifact-ref、approval gate、manifest revalidation 和 idempotency guard 通过后，写 append-only `workspace/workspace-foldered-canonical-broader-rollout-journal.json`、`workspace/workspace-foldered-canonical-broader-rollout-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` broader rollout metadata；它不接受 inline backend manifest JSON 执行真实 apply、不移动 workspace 文件、不改变 canonical path、不启用 dual-write、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_broader_rollout_post_audit` 会消费 applied broader rollout result、append-only broader rollout journal 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-post-audit.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-post-audit.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-post-audit.json` 的只读 transaction / idempotency / journal / broader rollout metadata / canonical path stability 审计；它不写 audit artifact、不 mutate manifest、不改变 canonical path、不启用 dual-write、不执行 rollback-vs-commit decision、不运行 pipeline、不启动浏览器或调用 MCP；`plan_workspace_foldered_canonical_broader_rollout_rollback_decision` 会消费 verified broader rollout post-audit 和当前 backend manifest，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-decision-plan.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-decision-plan.json` 的 review-only commit / rollback / defer options、current manifest revalidation 和 decision gate；它不记录 decision、不 commit、不 rollback、不写 artifact、不 mutate manifest、不运行 pipeline、不启动浏览器或调用 MCP；`record_workspace_foldered_canonical_broader_rollout_decision` 会消费 ready rollback-vs-commit decision plan，在 `write_result=true`、`approve_decision_record=true` 且 reviewer 非空时写 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-decision-record.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-decision-record.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-decision-record.json` 的 reviewed commit / rollback / defer decision record；它只记录人工决策，不 commit、不 rollback、不 mutate manifest、不运行 pipeline、不启动浏览器或调用 MCP；`execute_workspace_foldered_canonical_broader_rollout_commit` 默认 dry-run，显式 `mode=apply` + `approve_commit=true` 且已写入的 commit decision record、当前 backend manifest artifact-ref、transaction / idempotency guard 和 manifest entry revalidation 通过后，写 append-only `workspace/workspace-foldered-canonical-broader-rollout-commit-journal.json`、`workspace/workspace-foldered-canonical-broader-rollout-commit-result.json` 并只更新 `workspace/backend-artifact-manifest.json` 的 `metadata.workspace_alias` broader rollout commit metadata；它不接受 inline backend manifest JSON 执行真实 apply、不 rollback、不移动 workspace 文件、不改变 canonical path、不启用 dual-write、不运行 pipeline、不启动浏览器或调用 MCP；`review_workspace_foldered_canonical_broader_rollout_rollback_preflight` 会消费已写入的 rollback decision record、当前 backend manifest 和可选 commit journal，输出 `reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-preflight.v1` 与 `workspace/workspace-foldered-canonical-broader-rollout-rollback-preflight.json` / `/workspace/review/workspace-foldered-canonical-broader-rollout-rollback-preflight.json` 的只读 rollback executor gate、transaction guard、commit-state guard 和 manifest entry revalidation；它不写 artifact、不 rollback、不 mutate manifest、不移动 workspace 文件、不改变 canonical path、不启用 dual-write、不运行 pipeline、不启动浏览器或调用 MCP；`plan_workspace_dual_write_pilot` 则基于 readiness report 与 registered routes 生成 plan-only pilot 候选，默认只选 low-risk workspace / runtime-context / source / network / evidence artifact，显式 high-risk delivery / transaction artifact 会阻断计划并要求单独 review；`review_workspace_dual_write_pilot_workflow` 会把 readiness、pilot plan 和可选 observed scoped dual-write result verification 串成 `reverse-deepagent.workspace-dual-write-pilot-workflow.v1` 审阅工作流：没有观测到 `workspace-dual-write-plan.json` 时返回 `ready_for_review`，观测到显式 dual-write 输出后可报告 `verified` / `partial` / `blocked`，并给出单独运行 scoped dual-write pipeline 与记录审计结果的 review steps；`record_workspace_dual_write_pilot_result` 仍负责在显式 dual-write 运行后检查 `workspace-dual-write-plan.json`、legacy / future 文件存在性和 sha256 是否一致，默认只读，只有 `write_result=true` 时才写 `workspace/workspace-dual-write-pilot-result.json` 审计结果；除显式 `execute_workspace_foldered_canonical_physical_apply` 的 backend manifest canonical path promotion、`execute_workspace_foldered_canonical_legacy_fallback_tightening` 的 legacy fallback metadata tightening、`execute_workspace_foldered_canonical_migration_finalization` 的 finalization metadata update、`review_workspace_foldered_canonical_migration_post_finalization_audit` 的只读审计、`review_workspace_foldered_canonical_broader_rollout_readiness` 的只读 readiness gate、`plan_workspace_foldered_canonical_broader_rollout` 的 review-only plan descriptor 和 `review_workspace_foldered_canonical_broader_rollout_preflight` 的只读 executor preflight、`execute_workspace_foldered_canonical_broader_rollout` 的 explicit-review-only broader rollout metadata apply、`review_workspace_foldered_canonical_broader_rollout_post_audit` 的只读 post-rollout 审计、`plan_workspace_foldered_canonical_broader_rollout_rollback_decision` 的 review-only rollback-vs-commit decision plan、`record_workspace_foldered_canonical_broader_rollout_decision` 的 explicit reviewed decision record writer、`execute_workspace_foldered_canonical_broader_rollout_commit` 的 explicit reviewed commit executor 和 `review_workspace_foldered_canonical_broader_rollout_rollback_preflight` 的只读 rollback executor preflight 外，这些工具不会运行 pipeline、启用双写、移动 workspace 文件、启动浏览器或调用 MCP。

低风险 scoped dual-write pilot 现在也有纯 Python smoke 入口，可复现“mock Web pipeline 显式 scoped dual-write -> review workflow 验证 observed plan -> 可选写 `workspace/workspace-dual-write-pilot-result.json`”闭环，不启动浏览器、不调用 MCP、不迁移 canonical path：

```bash
reverse-agent-workspace-dual-write-smoke \
  --artifact-root "<repo-root>/artifacts/workspace-dual-write-pilot-smoke" \
  --artifact-keys workspace_task_card
```

只想保留 review-only 验证而不写 pilot result artifact 时，加 `--no-write-result`。
- `build_rebuild_delivery` 现在可直接接受 `task_card_artifact_ref` 与 `final_result_artifact_ref`，通过同一 workspace resolver 读取 `workspace_task_card` / `workspace_final` 等引用后生成既有 rebuild 输出；JSON 字符串入口仍保留，artifact-ref 输入不会执行 delivery、不会 mutate manifest、不会改变输出路径。
- 新增或调整 subagent、middleware、runtime artifact、hook artifact 时，必须同步 `workspace-contract.json` 的生成逻辑、manifest alias metadata、resolver 行为和测试。
- 不得在没有 compatibility alias、manifest 覆盖和回归测试的情况下直接移动现有 artifact 路径。

当前 contract 覆盖的虚拟协作区包括 `/workspace/recon/`、`/workspace/browser/`、`/workspace/debugger/`、`/workspace/hooks/`、`/workspace/timeline/`、`/workspace/rebuild/`、`/workspace/review/`、`/workspace/delivery/`、`/workspace/runtime/` 和 `/workspace/evidence/`。它把已实现角色 `coordinator`、`router`、`browser_runtime`、`web_recon`、`protector`、`delivery`、`debugger`、`hook`、`timeline`、`rebuild`、`review` 放在同一张表里，当前无剩余 planned-contract 子智能体。`browser_runtime` 负责 BrowserProvider metadata / capability matrix / session readiness 边界，默认 metadata-only 工具不会启动浏览器、探测 CDP、调用外部 provider factory 或依赖 MCP；`debugger` 负责 read-only debugger artifact review、paused-session continuation preflight、callframe 和 debugger timeline 摘要，不 resume / step / evaluate，不发送 CDP 命令；仅在显式 `record_paused_session_automatic_loop_executor_approval` 审批记录流程中写 `workspace/paused-session-automatic-loop-executor-approval-record.json`，或在显式 `record_paused_session_automatic_loop_multi_iteration_executor_approval` 审批记录流程中写 `workspace/paused-session-automatic-loop-multi-iteration-executor-approval-record.json`；`review_paused_session_automatic_loop_transaction_preflight` 只审计 approval plan / record 到 journal writer 的输入 gate；`record_paused_session_automatic_loop_transaction_journal` 仅在显式审批下写 `workspace/paused-session-automatic-loop-executor-journal.json` transaction journal；multi-iteration 路径中 `review_paused_session_automatic_loop_multi_iteration_transaction_preflight` 只审计 approval plan / record 到 journal writer 的输入 gate，`record_paused_session_automatic_loop_multi_iteration_transaction_journal` 仅在显式审批下写 `workspace/paused-session-automatic-loop-multi-iteration-executor-journal.json` transaction journal；这些 writer 不执行 automatic loop、不发送 CDP、不调用 MCP、不触碰移动端完整链路；`hook` 负责 read-only hook artifact review、function / module hook inventory、hook timeline、source-logpoint 摘要和 Source Map follow-through 审批记录 / dispatcher result / apply-preflight / selected-result checkpoint / completion checkpoint / terminal review package / closure checkpoint / final audit rollup 审计；除显式 `record_source_map_selected_executor_approval` 在审批通过时只写 `workspace/source-map-selected-executor-approval-record.json`，或显式 `record_source_map_followthrough_dispatch_approval` 在审批通过时只写 `workspace/source-map-followthrough-dispatch-approval-record.json` 外，不安装 hook / breakpoint / logpoint、不 evaluate JavaScript、不触发目标函数、不启动 transaction、不写 dispatch journal、不调用 dispatch target、不执行 selected executor；`review_source_map_followthrough_dispatch_transaction_preflight` 只审计 ready approval plan + written approval record 到 journal writer 的输入 gate，输出 `workspace/source-map-followthrough-dispatch-transaction-preflight.json`，不写 journal、不启动 transaction、不 dispatch；显式 `record_source_map_followthrough_dispatch_transaction_journal` 只在审批通过时写 `workspace/source-map-followthrough-dispatch-transaction-journal.json`，不调用 dispatch target、不执行 selected executor；`source-map-followthrough-dispatch-bounded-executor-gate` 只消费 written transaction journal 并输出 `workspace/source-map-followthrough-dispatch-bounded-executor-gate.json` read-only gate，固定 `ready_to_dispatch_now=false`、`future_dispatcher_contract.implemented=false`，下一步仍需 explicit dispatcher handoff review；`source-map-followthrough-dispatcher-result` 只在显式审批下记录 dispatcher MVP decision 到 `workspace/source-map-followthrough-dispatcher-result.json`，不得调用 dispatch target、不得执行 selected executor、不得运行 selected-executor apply-preflight；`timeline` 负责 read-only flow timeline review、correlation group / stitch proposal / auto-stitch gate 摘要，不生成 `stitched-flow.json`、不写 artifact、不记录审批；`review` 负责 read-only review gate 评估、risk / warning hints、evidence review requirements 汇总，以及显式 `record_review_approval` 审批审计记录；审批 ledger 只写 `review-approval-record.json` / `review-approval-ledger.json`，不执行交付、rollback、materialization 或 external delivery；`rebuild` 负责 rebuild-plan / pure or context-aware replay / Scrapy project 生成和 read-only rebuild artifact review，真实 local / external delivery transaction 由 `delivery` 负责；实际 Web recon、源码搜索、网络采样和 protection 仍由 `web_recon` / `protector` 负责。

纯 Python 冒烟测试：

```bash
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_memory_smoke.py"
```

## 轻量 Web 运行时后端

除了 `mock`、`native-web` 和 `legacy-mcp`，默认 registry 还注册了 3 个轻量 Web 后端：

- `playwright-cli`（别名：`playwright`, `pw-cli`）：运行 `playwright --version` 这类轻副作用探测，并对目标 URL 做静态 HTML / 脚本源码拉取。
- `chrome-cdp`（别名：`cdp`, `devtools`）：只探测已经存在的 Chrome DevTools 端点，例如 `http://127.0.0.1:9222/json/version` 和 `/json/list`，不会主动启动 Chrome。
- `browser-cli`（别名：`cli-browser`, `browser-command`）：给本地浏览器 CLI 适配命令预留的轻量后端；默认不配置命令，因此会结构化返回不可用。

示例：

```bash
reverse-agent-demo \
  --runtime chrome-cdp \
  --cdp-browser-url "http://127.0.0.1:9222" \
  --task-text "https://example.com/search 找 sign"

reverse-agent-demo \
  --runtime playwright-cli \
  --playwright-command playwright \
  --task-text "https://example.com/search 找 sign"

reverse-agent-demo \
  --runtime browser-cli \
  --browser-cli-command "my-browser-shim" \
  --task-text "https://example.com/search 找 sign"
```

这 3 个后端复用 `WebReverseRuntime` / `JSReverserRuntime` 的 Web recon schema，但能力刻意保持保守：不捕获实时网络时间线，不执行页面内 JS 运行时验证，也不注入反调试预加载脚本。工具不可用时会输出 `status=failed`、`next_action=ensure_browser_session` 和会话导出 artifact，而不是假装完成。

## 环境重建

项目已经补了 `pyproject.toml`，可以用 `pip`、`uv` 或现成的 `.venv` 进行重建。

如果你想在本地重新安装依赖，可以直接执行：

```bash
cd "<repo-root>"
uv pip install --python "<repo-root>/.venv/bin/python" -e .
```

安装完成后，会生成正式命令：

```bash
reverse-agent-demo --runtime mock
```

同时还会生成平台中立 runtime pipeline 命令和本地 fixture 相关命令：

```bash
reverse-agent-platform --runtime mini-program-devtools
reverse-agent-fixture --check
reverse-agent-fixture-smoke --runtime mock
```

如果你只想沿用当前现成环境，也可以继续直接使用：

```bash
"<repo-root>/.venv/bin/python" ...
```

## 目录说明

- `docs/design/`：架构与设计文档
- `docs/plans/`：规划文档
- `docs/reference/deepagents/`：本地 deepagents 学习资料
- `src/reverse_deepagent/`：实现代码骨架与 runtime adapter
- `src/reverse_deepagent/coordinator.py`：包内协调入口，统一调度 task card、route、recon、artifact 输出
- `scripts/`：运行与开发脚本
- `artifacts/`：mock demo 产出物、报告、截图与导出文件
- `artifacts-mcp-smoke/`：legacy MCP 后端 smoke 产物
- `tests/`：测试目录

## 当前关键文档

- 设计文档：`<repo-root>/docs/design/reverse-deepagent-architecture.md`
- 规划文档：`<repo-root>/docs/plans/2026-05-26-deepagents-js-reverse-agent-plan.md`

## 配置真实 OpenAI API 验证

仓库默认测试仍走 mock 运行时，避免公开 CI 或本地单元测试误消耗 API 额度。要用真实 OpenAI API 验证 DeepAgents 编排，可以安装 `llm` 可选依赖并设置环境变量。

安装可选依赖：

```bash
cd "<repo-root>"
uv pip install --python "<repo-root>/.venv/bin/python" -e ".[llm]"
```

设置 API key。不要把 key 写进 `.env`、README、代码或 Git 历史里；推荐只放当前 shell、系统 keychain 或 CI secret：

```bash
read -rsp "OPENAI_API_KEY: " OPENAI_API_KEY && export OPENAI_API_KEY
printf "\n"
export OPENAI_MODEL="gpt-5.5"
```

运行真实 OpenAI-backed DeepAgents 冒烟测试：

```bash
reverse-agent-openai-smoke \
  --task-text "http://localhost 找 sign 入口，并给出下一步建议。先调用 route_reverse_task 工具完成路由。" \
  --artifact-root "<repo-root>/artifacts/openai-smoke"
```

也可以不安装 console script，直接用模块入口：

```bash
"<repo-root>/.venv/bin/python" -m reverse_deepagent.openai_smoke \
  --model "${OPENAI_MODEL:-gpt-5.5}" \
  --artifact-root "<repo-root>/artifacts/openai-smoke"
```

这个 smoke 只验证真实模型能驱动 DeepAgents 主 Agent、调用 `route_reverse_task` 工具并返回结构化摘要；它不默认启动 Chrome，也不默认调用 MCP。真实 Web runtime 仍按后文 `reverse-agent-demo --runtime legacy-mcp --ensure-chrome` 或 `reverse-agent-fixture-smoke --runtime legacy-mcp --ensure-chrome` 配置。

如果你的账号暂时没有 `gpt-5.5` 权限，可以把 `OPENAI_MODEL` 改成账号可用的模型。

## 运行最小演示（mock 运行时）

mock 运行时不依赖真实浏览器，适合验证 schema、route、adapter、artifact 链路。

`scripts/run_demo.py` 现在只是薄 CLI；真正的协调逻辑在：

- `<repo-root>/src/reverse_deepagent/coordinator.py`
- 包内入口：`reverse_deepagent.run_reverse_pipeline`

也可以直接使用正式命令：

```bash
reverse-agent-demo --runtime mock
```

默认会在 `artifacts/` 下生成：

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/recon-result.json`
- `workspace/final-result.json`
- `workspace/evidence-candidates.json`（通用候选证据索引）
- `workspace/evidence-validated.json`（通用已验证证据索引）
- `workspace/evidence-promotion.json`（通用证据晋升摘要）
- `workspace/review-gate.json`（review_hints 自动 gate 结果）
- `workspace/function-candidates.json`（有候选时）
- `workspace/function-validations.json`（有验证结果时）
- `workspace/function-validation-summary.json`（有验证结果时）
- `workspace/runtime-context.json`（检测到并采集运行时上下文时）
- `workspace/runtime-context-diff.json`（运行时上下文稳定性摘要）
- `workspace/backend-artifact-manifest.json`（backend 输出 manifest）
- `workspace/rebuild-plan.json`
- `rebuild/sign_rebuild.py`（可生成纯算策略时）
- `rebuild/replay_demo.py`（可生成纯算策略时）
- `rebuild/scrapy_middleware.py`（兼容型单文件 middleware）
- `rebuild/scrapy_project/`（可运行 Scrapy replay 项目，含 settings / middleware / spider / runner）
- `rebuild/scrapy_export_manifest.json`（Scrapy 交付 manifest）
- `reports/demo-final-result.json`
- `reports/demo-final-report.md`
- `exports/artifact-index.json`

## 通用证据晋升

Web pipeline 与平台中立 pipeline 现在都会生成一组平台无关的证据晋升 artifact：

- `workspace/evidence-candidates.json`：所有规范化 `EvidenceItem` 的候选索引。
- `workspace/evidence-validated.json`：通过通用验证门槛的证据索引。
- `workspace/evidence-promotion.json`：candidate / validated / promoted / rejected 全量记录与摘要。

证据晋升不替代 `final-result.json`，也不改变现有 rebuild 所依赖的 `FinalResult.evidence`；它是给 review gate、后续自动门禁、自动交付阻断和人工代码审查使用的机器可读索引。`flow_timeline` evidence 中的 pending `stitch_proposals` 会被提炼为 `review_required_count`、`review_required_codes` 和 `review_required_items`，用于阻断自动交付，直到 reviewer 明确审批。

通用规则保持保守：

- 低置信、工具不可用、`available=false`、unsupported 等信号会阻断晋升。
- 高置信 source/callstack/runtime/context/function validation 证据更容易进入 `promoted`。
- `function_validation_summary.replay_ready=true` 和运行时验证成功会提高晋升分数。
- 非 Web runtime 也会生成同样结构的 promotion 文件，避免把证据规则写死在 Web recon 里。

这些文件会进入 `workspace/backend-artifact-manifest.json`，category 为 `evidence`。

## `review_hints` 自动门禁

Web rebuild 交付流程现在会在生成 `workspace/rebuild-plan.json` 后自动评估 `review_hints`，并输出：

- `workspace/review-gate.json`

门禁输入包括：

- `rebuild_plan.ready`
- `rebuild_plan.review_hints`
- `workspace/evidence-promotion.json` 的 validated / promoted / rejected 摘要
- `workspace/evidence-promotion.json` 的 evidence-level review requirements，例如 pending `flow_timeline` stitch proposal

门禁结果字段包括：

- `status`: `pass` / `warn` / `block`
- `blocked`: 是否阻断自动交付
- `blocking_hint_codes`: 阻断交付的 `risk` hint code
- `warning_hint_codes`: 需要人工确认的 warning 提示码
- `evidence_counts`: candidate / validated / promoted / rejected 证据数量
- `evidence_review_required_count` / `evidence_review_required_codes` / `evidence_review_required_items`: evidence promotion 暴露的人工复核阻断项
- `next_action`: `delivery_allowed`、`manual_review_before_delivery`、`manual_review_or_expand_evidence` 或 `review_stitch_proposals_before_delivery`

自动 gate 的基本规则：

- 任意 `severity=risk` 的 `review_hints` 会阻断自动交付。
- `rebuild_plan.ready=false` 会阻断自动交付。
- 没有 validated evidence 会阻断自动交付。
- ready=true 但没有 promoted evidence 会阻断自动交付。
- evidence promotion 中存在 pending review requirement 会阻断自动交付；当前典型来源是 `flow_timeline.stitch_proposals` 的 `review_decision.status=pending_review`。
- `flow_timeline.auto_stitch_dry_runs` 只提供自动拼接建议、`confidence_score`、`score_reasons`、`conflict_reasons`、`review_required=true` 和 `would_materialize=false`；`flow_timeline.auto_stitch_conflict_resolutions` 会把 dry-run 冲突整理成 review-only resolution，输出 review-preferred candidate、alternatives、unresolved conflicts 和 `would_materialize=false`；`flow_timeline.auto_stitch_policy_decisions` 进一步给出 conservative policy gate 结果、threshold、blockers 和 review-gate eligibility；`flow_timeline.auto_stitch_materialization_plans` 默认只生成 plan-only 的目标 artifact、entry path、review requirements 和 rollback plan。未显式审批前这些阶段都固定 `would_materialize=false` / `automatic_stitching=false` / `writes_artifact=false`，不会生成 `stitched-flow.json`，也不会绕过 review gate。
- 显式 `stitch_review_decisions` 审批通过后，`native-web` 可以生成 `workspace/stitched-flow.json` / `virtual://workspace/stitched-flow.json`；显式 `auto_stitch_materialization_review_decisions` 审批通过后，也可以把 policy-eligible materialization plan 转成 `auto_stitch_materialization_results` 并生成同一个 stitched-flow baseline，同时输出 `stitched-flow-materialization-audit.json`、`stitched-flow-rollback-plan.json`、transaction-log-only 的 `stitched-flow-materialization-transactions.json`，以及 rollback execution dry-run / explicit-review-only 的 `stitched-flow-rollback-executions.json`；显式 rollback execution result 还会派生 blocking 的 `review-gate-after-rollback.json` baseline 和 physical rollback dry-run diff 的 `stitched-flow-physical-rollback-diff.json`；显式 `auto_stitch_physical_rollback_review_decisions` 审批后，还会生成 `stitched-flow-physical-rollback-results.json` 并从本轮 `stitched_flows` artifact model 中移除匹配 materialization；physical rollback applied 后会派生 blocking 的 `review-gate-after-physical-rollback.json` rerun baseline；显式 `auto_stitch_standard_review_gate_replacement_review_decisions` 审批后，会生成 `review-gate-replacement-results.json`，记录标准 `workspace/review-gate.json` artifact model 已完成 replacement；replacement result 还会派生 `delivery-guard-after-review-gate-replacement.json`，记录 delivery guard rerun passed 与 `delivery_allowed=true`；delivery guard passed 后还会派生 `final-delivery-package-after-review-gate-replacement.json`，记录 artifact-model final delivery package ready / final_delivery_packaged / delivery_allowed；显式 `auto_stitch_transaction_commit_review_decisions` 审批后，还可以派生 `final-delivery-transaction-commit.json`，记录 artifact-model transaction commit record。它们都属于 reviewer-approved materialization / rollback / gate replacement / delivery guard / final package / transaction commit record baseline，仍保持 `automatic_stitching=false` / `automatic_rollback=false` / `automatic_delivery=false`；rollback execution 默认只生成 dry-run plan，显式审批后先记录 logical rollback result，physical diff 只描述 would-remove / manifest impact，final delivery package 和 transaction commit record 也只是 artifact-model record，不执行 filesystem artifact mutation、不执行 external delivery，不代表自动全链路 stitching、跨运行文件系统级 rollback transaction 或自动交付闭环。

本地交付执行器已提供最小 contract baseline：`LocalDeliveryExecutor` 默认 dry-run，只规划 reviewed artifact 的本地交付；delivery subagent 暴露 `execute_local_delivery`、`plan_delivery_resume`、`execute_delivery_resume`、`execute_delivery_resume_workflow`、`manage_delivery_transaction_lock_provider`、`execute_delivery_transition`、`execute_delivery_recovery`、`write_delivery_rollback_state` 和 `execute_delivery_rollback` tools；显式 `apply` 才会复制文件并写 `delivery-receipt.json` / `delivery-transaction-journal.json`；显式 `commit_manifest_revision=true` 时还会写本地 `delivery-manifest-revision.json`；显式 `commit_backend_manifest_mutation=true` 时会写本地 `backend-artifact-manifest-mutation.json` 与 `backend-artifact-manifest.patched.json`；显式 `preflight_backend_manifest_in_place_mutation=true` 时会写本地 `backend-artifact-manifest-preflight.json`，校验 source digest、patched manifest 可用性和 artifact key 冲突；显式 `approve_backend_manifest_in_place_mutation=true` 且 apply、patch written、preflight passed、expected source digest 匹配时，才会先写本地 `backend-artifact-manifest.rollback.json` checkpoint，再写 `backend-artifact-manifest-in-place-mutation.json` 并原地更新标准 `backend-artifact-manifest.json`；显式 `preflight_backend_manifest_recovery=true` 时，会读取上一轮 `delivery-transaction-journal.json`、in-place mutation record、patched manifest、rollback checkpoint 和当前 source manifest digest，写 `backend-artifact-manifest-recovery-preflight.json`，输出 `ready_for_review` / `blocked` / `no_recovery_required`；显式 `apply_backend_manifest_recovery=true` 且 apply、上一轮 journal、ready recovery preflight、rollback checkpoint、source digest 与 expected transaction id 全部通过时，会写 `backend-artifact-manifest-recovery.json`，把 `backend-artifact-manifest.rollback.json` 复制回标准 `backend-artifact-manifest.json`，并把上一轮 journal 标记为 `backend_manifest_recovered=true`；显式 `commit_cross_run_transaction=true` 且上一轮 journal、recovery preflight、source digest 与 expected transaction id 全部通过时，会写 `backend-artifact-manifest-transaction-commit.json` 并把上一轮 journal 标记为 `cross_run_transaction_committed=true`；重复执行已完成的 recovery apply 或 cross-run commit 时，会触发本地 `delivery-transaction-idempotency-guard.json`，保留既有成功终态 artifact，不把 `backend-artifact-manifest-recovery.json` / `backend-artifact-manifest-transaction-commit.json` 覆盖成 blocked 记录；显式 `require_transaction_lock=true` 时，apply-mode 的本地 artifact 复制、backend manifest 原地 mutation、recovery apply、cross-run transaction commit、external delivery request、recovery / rollback workflow 会先经过本地 `delivery-transaction-lock.json` gate；该记录包含 owner、lease_expires_at、resume_token 与 expected_resume_token 检查，同 owner 或匹配 resume token 可继续，其他 owner 或 stale lock 默认阻断并要求人工 review / cleanup；显式 `release_transaction_lock=true` 可生成 `delivery-transaction-lock-release.json` release / stale review 记录，apply 模式还必须设置 `approve_transaction_lock_release=true` 且可选 expected owner / transaction id / resume token 检查通过后，才会删除本地 lock；`plan_delivery_resume` / `DeliveryResumePlanner` 可从现有 transaction / rollback / transition / lock / release artifacts 生成只读或 apply 写审计的 `delivery-resume-plan.json`，给出 `recommended_resume_action`、`resume_steps`、`lock_summary` 和 blockers；`execute_delivery_resume` / `DeliveryResumeRunner` 可在匹配 `review-approval-ledger.json` 后执行单个显式 recovery / commit transition 并写 `delivery-resume-execution.json`，仍委托 transition executor 和 LocalDeliveryExecutor 保留 journal / digest / lock checks；这是 local delivery root lock / resume / release / resume-plan / single-transition runner baseline；`execute_delivery_resume_workflow` 进一步提供本地 durable workflow journal baseline，可在审批后串行执行多个 resume step 并跳过已 journal 的完成项，但仍不是后台 daemon、分布式工作流引擎或自动恢复系统，不做自动 stale takeover，也不提供跨机器 consensus；`manage_delivery_transaction_lock_provider` 进一步提供 pluggable transaction lock provider contract baseline，默认 registry 包含 `local-file-lock` / `filesystem-lock` / `local-distributed-lock` reference provider、`sqlite-lock` / `db-lock` / `sqlite-transaction-lock` / `local-db-lock` SQLite provider，以及 `redis-lock` / `redis` / `redis-lease-lock` / `external-redis-lock` external Redis provider；local-file 只在显式 apply 时写 `delivery-distributed-transaction-lock.json` 与 `delivery-distributed-transaction-lock-operation.json`，SQLite 把 `delivery-distributed-transaction-lock.sqlite3` 作为权威 local transactional store 并继续写 JSON projection / operation record，Redis 把外部 Redis key 作为权威 lease store 并继续写本地 JSON projection / operation record；三者都支持 acquire / renew / release、lease 和 fencing token 审计，但不替换现有 `delivery-transaction-lock.json` gate；Redis 只在非 dry-run provider 操作中联系外部服务，不实现 Redlock quorum consensus；显式 `expected_transaction_lock_fencing_token` 会把 provider projection 接入 `LocalDeliveryExecutor` 及 transition / resume / recovery / rollback 工具链的 apply-mode side-effect gate，不匹配、缺失、格式错误或过期的 fencing record 都会阻断副作用；`execute_delivery_resume_workflow` 在同一次 reviewed workflow execution 内还会把成功 `acquire_delivery_transaction_lock_provider` / `renew_delivery_transaction_lock_provider` step 返回的 fencing token 传播给后续 runner step，作为 `expected_transaction_lock_fencing_token` 使用；显式配置的 expected token 优先级更高，成功 `release_delivery_transaction_lock_provider` 会清空已传播 token，传播元数据会写入 step result 与 `delivery-resume-workflow-journal.json`；resume-of-resume 跳过已 journal 的 lock-provider step 时，scheduler 会从同一 transaction 的成功 workflow journal 条目中保守 replay 未过期 fencing token，并在 journaled release 后清空 token；跳过任意已完成 step 时，还会附带只读 `journal_replay` 摘要，包含上一轮 entry status、runner / transition status、lock evidence 与 side-effect policy，方便审计 durable workflow 依赖；规划阶段还会输出 `lock_lifecycle_plan` 与 `lease_renewal_plan`；`lock_lifecycle_plan` 只根据 provider projection / workflow journal evidence 给出 reviewed acquire / release 建议，缺少 provider lock evidence 的默认 recovery workflow 可前置 `acquire_delivery_transaction_lock_provider`，terminal transaction 仍有 provider lock evidence 时可规划 `release_delivery_transaction_lock_provider`；`lease_renewal_plan` 判断已有 fencing token 的 lease 是否缺失、过期或即将过期，过期 / 即将过期时可把 `renew_delivery_transaction_lock_provider` 作为默认 workflow 的前置 reviewed step；这些计划都保持 `dry_run_plan_only=true`、`automatic_lock_lifecycle=false`、`automatic_renewal=false`、`starts_daemon=false`，执行仍需要对应 review approval；这些 replay、lifecycle planning 和 lease planning 都不自动 acquire / renew / release、不重放 provider action、不恢复 manifest，也不是全局 fencing enforcement；`execute_delivery_transition` 在这个基础上提供显式 transition shell，支持 `preflight_backend_manifest_recovery`、`apply_backend_manifest_recovery` 和 `commit_cross_run_transaction`，默认 dry-run，apply 必须显式选择 transition，并可写 `delivery-transition-execution.json` 审计记录；`execute_delivery_recovery` / `DeliveryTransactionRecoveryExecutor` 则提供更高一层的 recovery workflow baseline，支持 `plan_recovery`、`preflight_recovery` 和显式审批的 `apply_recovery`，可按顺序编排 recovery preflight -> recovery apply 并写 `delivery-recovery-execution.json`，但不自动 commit、不发布 external delivery、不实现跨运行 rollback 状态机；`record_review_approval` 可把人工 review decision 写入 `artifact_root/workspace/review-approval-record.json` 并追加到 `review-approval-ledger.json`；默认 dry-run，apply 必须有 reviewer 且 `approve_decision_record=true`，这个 ledger 只是后续 review-gated executor 的审计输入，不会自动执行 delivery、rollback、manifest mutation 或 materialization。显式 `request_external_delivery=true` 时会通过 `ExternalDeliveryProviderRegistry` 解析 `ExternalDeliveryProvider` contract；默认内置 `review-only` provider 及 `noop` / `manual-handoff` alias 只写 `external-delivery-result.json` blocked handoff record，不上传、不推送、不发布；内置 `local-archive` / `filesystem-release` 可在显式 apply 后复制到本地归档目录，`webhook` / `http-webhook` 可显式 POST redacted JSON package，`presigned-object` / `object-storage` / `presigned-url` / `s3-presigned` 可显式 PUT JSON package 到 presigned object-storage URL；registry 支持 `reverse_deepagent.external_delivery_providers` entry point 发现 provider registration，`reverse-agent-doctor --external-delivery-providers` 可 side-effect-free 输出 provider matrix 和 alias / transport / review-only metadata，测试中的 fake provider 用于证明 contract 可把 `external_delivery_performed=true` 写回 result / journal；`external_delivery_idempotency_key` 默认等于 transaction id，并写入 package / result / journal metadata；同一个 delivery root 如果已有 journal 或 result 标记 `external_delivery_performed=true`，后续 external delivery 请求默认会在调用 provider factory / provider 之前被 duplicate guard 阻断，并写 `external-delivery-duplicate-guard.json`，只有显式 `allow_duplicate_external_delivery=true` 才会继续调用 provider；apply-mode external delivery 还会维护 append-only `external-delivery-idempotency-ledger.json`，把正常 provider 结果、duplicate guard block 和 retry / Retry-After / rate-limit attempt summary 记录成审计流水，但不发布、不自动重试、不恢复、不绕过 duplicate guard。`DeliveryExecutionResult.to_dict()` 现在还会内嵌只读 `transaction_state` 快照，由 `reverse_deepagent.delivery.evaluate_delivery_transaction_state(...)` 统一把 result / journal / external result / recovery / commit artifact 归一成 `planned`、`local_applied`、`manifest_patch_written`、`manifest_mutated`、`recovery_required`、`recovered`、`external_delivery_attempted`、`external_delivered`、`committed` 或 `blocked`，并输出 `completed_states`、`flags`、`evidence_paths`、`blocking_reasons` 和 `recommended_actions`；`plan_delivery_transition(...)` 只给 conservative next-transition 建议，不执行任何副作用。`evaluate_delivery_rollback_state(...)` 进一步把 journal、recovery preflight、recovery result、commit record、external delivery result 和 idempotency guard 归一成只读 rollback phase，例如 `rollback_preflight_required`、`rollback_decision_required`、`rollback_applied`、`committed`、`external_delivery_performed` 或 `duplicate_terminal_action_blocked`，输出 review-gated `allowed_transitions`；`write_delivery_rollback_state` / `DeliveryRollbackStateArtifactWriter` 可在显式 apply 时把该只读状态写成 `delivery-rollback-state.json` durable audit artifact，作为后续 reviewed rollback executor / resume workflow 的稳定输入；`execute_delivery_rollback` / `DeliveryRollbackExecutor` 进一步提供 `plan_rollback`、`preflight_rollback` 与显式审批的 `apply_rollback` baseline：显式 apply 的 preflight 只写 `delivery-rollback-state.json`、`backend-artifact-manifest-recovery-preflight.json` 和 `delivery-rollback-execution.json` 审计记录，不执行 recovery apply；显式 apply 的 `apply_rollback` 必须处于 `rollback_decision_required`，提供 `expected_transaction_id`、`backend_manifest_path` 与 `approve_rollback=true`，才会委托 recovery executor 用 rollback checkpoint 恢复本地 `backend-artifact-manifest.json`，写 `backend-artifact-manifest-recovery.json`，并把 `delivery-rollback-execution.json` 标记为 `rolled_back`。这只表示 `local_manifest_rollback_performed=true` / `manifest_recovered=true`，仍不 commit、不 external delivery、不获取分布式锁、不执行 broader filesystem physical rollback。`reverse-agent-doctor --delivery-transaction-root` 可从 delivery root 读取这些标准 transaction artifacts，输出只读 state / transition / artifact load status / side-effect policy，方便跨运行审计当前 delivery transaction 卡在哪一步；它仍不会自动 external delivery，也不会自动 restore manifest；transition executor 也不会自动选择 recovery vs commit、不会发布 external delivery、不会替代完整 cross-run rollback state machine；`backend_manifest_patch_written=true` 只表示 patched copy 已写入，`backend_manifest_in_place_preflight_passed=true` 只表示 preflight 通过，`backend_manifest_mutated=true` 也只表示本地显式审批后的标准 manifest mutation，`backend_manifest_recovery_preflight_passed=true` 只表示 recovery preflight 可进入 review 或无需恢复，`backend_manifest_recovered=true` 只表示本地显式 recovery apply 已从 rollback checkpoint 恢复标准 manifest，`external_delivery_performed=true` 只表示配置的 external provider 明确返回已交付，默认 review-only provider 永远不会返回 true，`cross_run_transaction_committed=true` 只表示本地 transaction journal 已完成显式 commit，不等价于完整恢复状态机。
- warning hint 不阻断，但输出 `status=warn`，要求人工确认后再交付。
- 存在 rejected evidence 且没有阻断项时输出 `status=warn`，避免把有争议的证据静默放行。

`review-gate.json` 会进入 `workspace/backend-artifact-manifest.json`，category 为 `triage`。平台中立 pipeline 不生成 rebuild bundle，因此不生成 review gate；它继续只输出证据晋升结果。

## 运行平台中立运行时流水线

`run_reverse_pipeline(...)` 仍然是 Web 专用入口，会要求后端实现 `WebReverseRuntime` 并执行 Web recon；非 Web runtime 统一走 `run_platform_pipeline(...)` / `reverse-agent-platform`。这个入口只依赖平台中立的 `ReverseRuntime` 契约：任务归一化、路由、能力采集、运行时 artifact 导出，以及 manifest / index / report 落盘，不会调用 `ensure_browser_session()` 或 `run_web_recon()`。

最小冒烟测试：

```bash
reverse-agent-platform \
  --runtime mini-program-devtools \
  --task-text "mini-program://demo 找 sign"
```

Android / iOS 可以传本地工具链参数：

```bash
reverse-agent-platform \
  --runtime android-adb \
  --android-adb-command adb \
  --android-device-serial "<device-serial>" \
  --android-package-name "com.example.app"

reverse-agent-platform \
  --runtime ios-simulator \
  --ios-xcrun-command xcrun \
  --ios-device-id "<simulator-udid>" \
  --ios-bundle-id "com.example.app"
```

默认会在 artifact root 下生成：

- `workspace/task-card.json`
- `workspace/route-decision.json`
- `workspace/runtime-capabilities.json`
- `workspace/runtime-export-bundle.json`
- `workspace/platform-tool-probe.json`（backend 暴露 tool probe 时）
- `workspace/final-result.json`
- `workspace/evidence-candidates.json`
- `workspace/evidence-validated.json`
- `workspace/evidence-promotion.json`
- `workspace/backend-artifact-manifest.json`
- `reports/platform-pipeline-result.json`
- `reports/platform-pipeline-report.md`
- `exports/artifact-index.json`

工具链不可用时不会伪装成功：pipeline 会结构化返回 `status=partial` 和 `next_action=install_or_configure_platform_tooling`，同时仍然保留 probe 证据，方便后续平台专用子流程接手。

## 运行最小 DeepAgents 调用冒烟测试

如果你想验证“主 Agent + route tool（并注册专用子 Agent）”这条深度编排链路，但又不想依赖外部模型或真实浏览器，可以直接跑纯 Python 冒烟测试：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-smoke"
```

这条冒烟测试会：

- 构建 `deepagents` 主 Agent
- 通过 `route_reverse_task` 工具完成一次真实 invoke
- 产生 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage` 的完整消息链
- 打印 route 结果和最终消息摘要

适合用来验证：

- `build_reverse_agent()` 是否和当前 deepagents 版本对齐
- 工具函数是否具备可包装成 LangChain tool 的元数据
- 主 Agent 到 route tool 的闭环是否可用

### 子 Agent 委派冒烟测试

如果你还想验证主 Agent 通过 `task` 工具委派给 general-purpose 子 Agent 的链路，可以再跑这个：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_subagent_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-subagent-smoke"
```

这条冒烟测试会验证：

- 主 Agent 生成 `task` tool call
- deepagents 启动 general-purpose 子 Agent
- 子 Agent 的单条结果被回收到主线程
- 消息链完整呈现为 `HumanMessage -> AIMessage -> ToolMessage -> AIMessage`

### 重建交付冒烟测试

如果你想验证 deepagents 主 Agent 的 rebuild 生成链路，可以跑：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/run_deepagent_delivery_smoke.py" \
  --artifact-root "<repo-root>/artifacts/deepagents-delivery-smoke"
```

这条冒烟测试会验证：

- 先用 mock 运行时准备一份已验证 `FinalResult`
- `rebuild` 子智能体调用 `build_rebuild_delivery`
- 生成结构化 `RebuildResult`
- 产出 `workspace/rebuild-plan.json`
- 产出 `rebuild/sign_rebuild.py`
- 产出 `rebuild/replay_demo.py`
- 产出 `rebuild/scrapy_middleware.py`
- 产出 `rebuild/scrapy_project/` 与 `rebuild/scrapy_export_manifest.json`
- `delivery` 子智能体保留为后续 local / external delivery transaction 执行边界

对应 deepagents 能力已接入：

- rebuild tool：`build_rebuild_delivery`
- rebuild subagent：`rebuild`
- delivery tools：`execute_local_delivery`、`execute_delivery_transition`、`execute_delivery_recovery`、`write_delivery_rollback_state`、`execute_delivery_rollback`
- delivery subagent：`delivery`
- schema：`RebuildResult`

## 本地 sign fixture 样例

项目内置了一个可重复的 `localhost` Web 逆向样例，用来验证 sign 入口、请求样本和源码命中链路。

相关入口：

- fixture 服务：`reverse-agent-fixture`
- fixture 冒烟测试：`reverse-agent-fixture-smoke`
- 服务实现：`<repo-root>/src/reverse_deepagent/fixtures/web_sign.py`

快速自检：

```bash
reverse-agent-fixture --check
```

启动阻塞式本地服务：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765
```

指定 fixture profile：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765 --profile sha256
```

当前支持：

- `default`：`charCodeAt` 求和取模，再输出 `sig_<hex>_<timestamp>`
- `md5`：fixture 内置纯 JS `md5(keyword:timestamp)`，用于验证 `md5_keyword_timestamp` rebuild
- `sha1`：浏览器 `crypto.subtle.digest('SHA-1', ...)`，用于验证 `sha1_keyword_timestamp` rebuild
- `sha256`：浏览器 `crypto.subtle.digest('SHA-256', ...)`
- `base64`：`btoa(keyword:timestamp)`
- `context-localstorage`：依赖 `localStorage.device_id`，用于验证 localStorage context-aware delivery
- `context-cookie`：依赖 `document.cookie` 中的 `device_id`，用于验证 cookie context-aware delivery
- `context-navigator`：依赖 `navigator.userAgent`，用于验证浏览器指纹上下文 context-aware delivery
- `webpack-minified`：模拟 webpack 模块包装器与压缩辅助函数，验证打包形态下的 SHA-256 sign 识别
- `token-chain`：先访问 `/api/bootstrap` 获取 token，再用 `sessionStorage.fixture_token` 参与 SHA-256 sign
- `hybrid-context`：同时依赖 `localStorage.fixture_nonce` 与 `cookie.csrf_token`，用于验证多上下文绑定 context-aware delivery

页面与脚本：

- `http://127.0.0.1:8765/`
- `http://127.0.0.1:8765/app.js`
- `http://127.0.0.1:8765/api/bootstrap`（`token-chain` profile 使用）
- `http://127.0.0.1:8765/api/search`

`app.js` 中包含稳定的入口特征：

- `function buildSign(keyword, timestamp)`
- `x-sign`
- `window.reverseFixture.search(...)`

使用 mock 运行时跑 fixture 冒烟测试：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime mock \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mock"
```

使用 legacy MCP + 受管 Chrome 跑 fixture 冒烟测试：

```bash
reverse-agent-fixture-smoke \
  --profile default \
  --runtime legacy-mcp \
  --ensure-chrome \
  --jsreverser-mcp-command "/opt/homebrew/bin/jsreverser-mcp" \
  --chrome-debug-port 9445 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-fixture-smoke" \
  --artifact-root "<repo-root>/artifacts/fixture-smoke-mcp"
```

多策略真实冒烟测试示例：

```bash
reverse-agent-fixture-smoke \
  --profile sha256 \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9456 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-sha256" \
  --artifact-root "<repo-root>/artifacts/fixture-sha256-mcp"
```

如果要验证运行时上下文采集与 context-aware delivery：

```bash
reverse-agent-fixture-smoke \
  --profile context-localstorage \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9457 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-context" \
  --artifact-root "<repo-root>/artifacts/fixture-context-mcp"
```

第 13 阶段还可以直接验证 cookie / navigator 两类上下文：

```bash
reverse-agent-fixture-smoke \
  --profile context-cookie \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9460 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-phase13-cookie-9460" \
  --artifact-root "<repo-root>/artifacts/phase13-cookie-mcp"

reverse-agent-fixture-smoke \
  --profile context-navigator \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9461 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-phase13-navigator-9461" \
  --artifact-root "<repo-root>/artifacts/phase13-navigator-mcp"
```

预期 `context-localstorage` 会生成：

```json
{
  "ready": true,
  "pure_extraction": {
    "pure_extractable": false,
    "context_aware_extractable": true,
    "runtime_context_required": ["localStorage"],
    "captured_runtime_context": ["localStorage"]
  }
}
```

并落盘：

- `workspace/runtime-context.json`
- `workspace/runtime-context-diff.json`
- `rebuild/sign_rebuild.py`
- `rebuild/replay_demo.py`

`context-cookie` 的预期是 `runtime_context_required = ["cookie"]`，生成的 `sign_rebuild.py` 会固化 `COOKIE_DEVICE_ID`。

`context-navigator` 的预期是 `runtime_context_required = ["navigator"]`，生成的 `sign_rebuild.py` 会固化 `NAVIGATOR_USER_AGENT` 并完成 `sha256_keyword_timestamp` 自检。

当前已验证 legacy MCP 冒烟测试结果：

- `final_result.status = success`
- `final_result.next_action = extract_pure_logic_and_build_replay`
- 能观察到 `/api/search` 网络请求样本
- 能命中 `/app.js` 中的 `buildSign` / `x-sign` 源码位置
- 能自动晋升请求发起链路证据：
  - `source = get_request_initiator`
  - artifact：`virtual://workspace/request-initiators.json`
- 能自动晋升源码上下文证据：
  - `source = get_script_source`
  - artifact：`virtual://workspace/source-contexts.json`
- 能自动生成候选函数卡片：
  - `source = function_candidate_card`
  - artifact：`virtual://workspace/function-candidates.json`
  - 当前 fixture 可稳定生成 `buildSign` 与 `search` 两张函数卡片
- 能自动完成候选函数运行时验证与 replay 校验：
  - `source = function_validation_result`
  - `source = function_validation_summary`
  - artifact：`virtual://workspace/function-validations.json`
  - artifact：`virtual://workspace/function-validation-summary.json`
  - 当前 fixture 可稳定验证 `buildSign` 与 `search` 两张函数卡片，并完成 replay
- 能自动生成纯算交付包：
  - `workspace/rebuild-plan.json`：描述候选函数、算法策略、纯算提取状态、验证状态、replay URL 和输出文件
  - `rebuild/sign_rebuild.py`：浏览器外纯 Python sign 计算脚本
  - `rebuild/replay_demo.py`：浏览器外 HTTP replay 演示
  - `rebuild/scrapy_middleware.py`：兼容型 Scrapy 下载中间件单文件
  - `rebuild/scrapy_project/`：可运行 Scrapy replay 项目，包含 `scrapy.cfg`、settings、middleware、spider、runner 和 `sign_adapter.py`
  - `rebuild/scrapy_export_manifest.json`：Scrapy 项目入口、命令和文件索引
- workspace 虚拟 artifact 会同步写成真实 JSON 文件：
  - `workspace/network-requests.json`
  - `workspace/source-hits.json`
  - `workspace/request-initiators.json`
  - `workspace/source-contexts.json`
  - `workspace/runtime-context.json`
  - `workspace/runtime-context-diff.json`
  - `workspace/function-candidates.json`
  - `workspace/function-validations.json`
  - `workspace/function-validation-summary.json`
  - `workspace/backend-artifact-manifest.json`
  - `workspace/rebuild-plan.json`
- rebuild 交付文件会写入：
  - `rebuild/sign_rebuild.py`
  - `rebuild/replay_demo.py`
  - `rebuild/scrapy_middleware.py`
  - `rebuild/scrapy_project/`
  - `rebuild/scrapy_export_manifest.json`
- `chrome_launch.ok = true`
- `chrome_stop.ok = true`
- 结束后调试端口无残留监听

### 纯算 replay 交付包

legacy MCP fixture 冒烟测试完成后，可以先对生成的 sign 脚本做 sample 自检：

```bash
"<repo-root>/.venv/bin/python" \
  "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/sign_rebuild.py"
```

如果要验证 `replay_demo.py` 的浏览器外复放能力，需要让 fixture 服务保持运行，例如另开一个终端：

```bash
reverse-agent-fixture --host 127.0.0.1 --port 8765
```

然后执行：

```bash
"<repo-root>/.venv/bin/python" \
  "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/replay_demo.py" \
  --base-url "http://127.0.0.1:8765" \
  --keyword "sign"
```

这一步不需要 Chrome，也不需要 MCP，证明已经进入“纯算 + HTTP replay”的交付形态。

### Scrapy replay 项目

第 10 项开始，ready rebuild 会额外生成完整 Scrapy 项目，而不只是 middleware 草案：

- `rebuild/scrapy_project/scrapy.cfg`
- `rebuild/scrapy_project/reverse_sign_project/settings.py`
- `rebuild/scrapy_project/reverse_sign_project/middlewares.py`
- `rebuild/scrapy_project/reverse_sign_project/spiders/replay_spider.py`
- `rebuild/scrapy_project/reverse_sign_project/sign_adapter.py`
- `rebuild/scrapy_project/runner.py`
- `rebuild/scrapy_export_manifest.json`

Scrapy 是可选依赖，按需安装：

```bash
pip install "reverse-deepagent[scrapy]"
# 或者在当前环境里手动安装
pip install scrapy
```

运行示例：

```bash
cd "<repo-root>/artifacts/fixture-smoke-mcp/rebuild/scrapy_project"
scrapy crawl reverse_sign_replay -a base_url="http://127.0.0.1:8765"
# 或者
python runner.py --base-url "http://127.0.0.1:8765" --output result.json
```

生成项目通过 `reverse_sign_project.sign_adapter` 读取同级上层的 `../sign_rebuild.py`，middleware 会把请求改写为带 `keyword` / `timestamp` / `sign` JSON body 的 POST，并设置 `x-sign` 与 `x-fixture` headers。没有安装 Scrapy 时，middleware 和 adapter 仍可被普通 Python import / compile，用于离线验证签名注入逻辑。

### 纯算提取策略字段

`workspace/rebuild-plan.json` 现在会显式区分“能纯算”和“需要运行时上下文”：

```json
{
  "algorithm_strategy": {
    "id": "md5_keyword_timestamp",
    "supported": true,
    "confidence": "medium",
    "confidence_score": {
      "score": 0.65,
      "label": "medium",
      "positive_markers": ["md5", "keyword_colon_timestamp"],
      "caveats": []
    },
    "dependencies": ["python-stdlib:hashlib"],
    "confidence_reason": "Detected md5 hash marker in source context."
  },
  "pure_extraction": {
    "pure_extractable": true,
    "manual_port_required": false,
    "runtime_context_required": [],
    "dependencies": ["python-stdlib:hashlib"],
    "confidence_reason": "Detected md5 hash marker in source context."
  },
  "review_hints": [
    {
      "severity": "info",
      "category": "strategy",
      "code": "pure_strategy_detected",
      "message": "Supported pure-Python rebuild strategy detected; review generated sign_rebuild.py against the captured sample before reuse.",
      "evidence": ["strategy=md5_keyword_timestamp", "runtime_context_required=[]"]
    }
  ]
}
```

当前策略检测通过 `reverse_deepagent.strategies` 包里的 `AlgorithmStrategyRule` registry 管理；`rebuild.py` 只保留兼容代理。策略输出保留旧 `confidence` 字符串，同时新增 `confidence_score`，记录数值分数、positive markers 和 caveats；策略与 rebuild plan 还会携带 review-only `evidence_score`，把 detector confidence、validation readiness、replay URL、runtime-context diff、protected-flow triage 和 rebuild readiness 归一成 `score`、`label`、`signals`、`blockers` 和 `recommended_next_action`。这个评分面不改变 `ready` 判定，不采集 runtime context，不执行 replay，不启动浏览器，也不调用 MCP；review gate 会只读消费该 score，把 `needs_more_evidence` / `runtime_assisted_required` / score blockers 转成自动 delivery 阻断，把 `reviewable_candidate` 转成人工 review warning，并把 `strategy_evidence_score_*` 摘要写入 `workspace/review-gate.json`。registry 元数据可由 `list_algorithm_strategy_registry()` 读取。当前默认顺序：

1. `protected_flow_triage`：发射 `triage_wasm_module`、`triage_vm_obfuscation`、`triage_anti_debug_runtime`、`triage_dynamic_secret`、`triage_wasm_vm_obfuscation`
2. `deterministic_fixture`：发射 `fixture_seed_mod100000`
3. `crypto_hash`：发射 `md5_keyword_timestamp`、`sha1_keyword_timestamp`、`sha256_keyword_timestamp`、`sha512_keyword_timestamp`、`hmac_md5_keyword_timestamp`、`hmac_sha1_keyword_timestamp`、`hmac_sha256_keyword_timestamp`、`hmac_sha512_keyword_timestamp`（HMAC 需要能提取 literal secret）
4. `sig_template`：发射 `sig_keyword_timestamp_template`
5. `encoding`：发射 `base64_keyword_timestamp`、`urlencode_keyword_timestamp`

`protected_flow_triage` 是阻断型前置检测器，必须保守：普通 `cookie` / `localStorage` / `navigator` / `nonce` / `csrf` 等上下文输入不会仅凭变量名进入仅分诊状态，除非同时出现 WASM / VM / anti-debug / 原生桥 / 强运行时挑战等强保护证据。

策略库还提供 `STRATEGY_SAMPLE_CORPUS` / `list_strategy_sample_corpus()`，覆盖 fixture reducer、MD5、SHA-1、SHA-256、SHA-512、HMAC-MD5、HMAC-SHA1、HMAC-SHA256、HMAC-SHA512、Base64 和 URL encoding 的确定性样本。测试会用这些样本同时验证检测器输出和生成的 `sign_rebuild.py` 自检。

WASM、JS VM、重混淆、反调试和动态 secret 这类流程不能被硬说成纯 Python 可移植。对应边界见 [`docs/strategy/wasm-vm-obfuscation-triage.md`](docs/strategy/wasm-vm-obfuscation-triage.md)：这类场景会优先命中 `protected_flow_triage` 检测器，输出仅分诊 / 运行时辅助 / 部分完成计划，并通过 `review_hints` 阻断误导性的纯算交付。protected-flow strategy 还会携带 plan-only `triage_hook_plan`，在 rebuild README 中列出 hook/debugger 候选和计划 artifact，例如 `workspace/protection-triage-hooks.json`、`workspace/wasm-runtime-candidates.json`、`workspace/vm-dispatcher-candidates.json`；这些只是显式复核计划，不会默认安装 hook、patch runtime、启动浏览器或调用 MCP。

当前会阻断纯算提取的运行时上下文依赖：

- `document.cookie`
- `localStorage`
- `sessionStorage`
- `navigator`
- `timezone`
- `canvas`

如果出现这些依赖，`rebuild-plan.json` 会标记：

```json
{
  "ready": false,
  "pure_extraction": {
    "pure_extractable": false,
    "manual_port_required": true,
    "runtime_context_required": ["localStorage"]
  },
  "review_hints": [
    {
      "severity": "risk",
      "category": "manual_port",
      "code": "manual_port_required",
      "message": "No complete automatic rebuild is available; expand source/runtime evidence or keep a JS runtime backend for this flow.",
      "evidence": ["strategy=sha256_keyword_timestamp", "missing_runtime_context=localStorage"]
    }
  ]
}
```

如果运行时上下文没有采集到，这时候不会强行生成假的纯算交付脚本，而是生成 `rebuild/README.md`，提示需要继续补运行时上下文或人工移植。

如果上下文已经采集到，例如 `context-localstorage` profile 的：

```json
{
  "localStorage": {
    "device_id": "fixture-device"
  }
}
```

则 `rebuild-plan.json` 会升级为：

```json
{
  "ready": true,
  "pure_extraction": {
    "pure_extractable": false,
    "context_aware_extractable": true,
    "runtime_context_required": ["localStorage"],
    "captured_runtime_context": ["localStorage"],
    "runtime_context_binding": {
      "source": "localStorage.device_id",
      "key": "device_id",
      "constant": "LOCAL_STORAGE_DEVICE_ID",
      "value": "fixture-device"
    },
    "runtime_context_binding_required": true,
    "runtime_context_binding_candidates": ["localStorage.device_id"]
  },
  "review_hints": [
    {
      "severity": "warning",
      "category": "runtime_context",
      "code": "context_aware_rebuild",
      "message": "Generated rebuild depends on captured browser/runtime context; verify these values are stable before running at scale.",
      "evidence": ["runtime_context_required=localStorage", "captured_runtime_context=localStorage"]
    }
  ]
}
```

生成的 `sign_rebuild.py` 会把采集到的上下文写成默认常量，用于浏览器外 replay。renderer 会从源码自动识别 `localStorage.getItem('<key>')`、`localStorage['<key>']`、`localStorage.<key>`、`sessionStorage.getItem('<key>')`、`sessionStorage['<key>']`、`sessionStorage.<key>`、`document.cookie` 中的 cookie name、`navigator.<prop>` 和 `timezoneOffset`，再从 `runtime-context.json` 中提取对应值写入 `pure_extraction.runtime_context_binding`。

如果源码已经明确依赖某个具体上下文 key，例如 `localStorage.getItem('nonce')`，但采集结果里只有同 family 的其他值，例如 `localStorage.device_id`，则 `context_aware_extractable` 会保持 `false`，`review_hints` 会输出 `missing_runtime_context_binding=localStorage.nonce`，交付包只生成 `rebuild/README.md`，不会用空 salt 或错误兜底生成假成功脚本。

当前自动交付支持单个或多个运行时上下文 binding 写入生成脚本；如果源码同时依赖 `localStorage.nonce` 和 `cookie.csrf` 这类多个显式上下文值，只要都已采集并解析出来，就会把它们按源码顺序拼进生成脚本，继续保持 ready。缺失任一上下文值时才会标记 `multiple_runtime_context_bindings_unsupported=true` 并保持 not-ready，避免把半截多输入签名硬塞进单 salt renderer。HMAC 策略会区分 HMAC secret 与 message 里的运行时上下文：`CryptoJS.HmacSHA256(raw, 'secret')` 会把 `secret` 作为 HMAC key，把 `nonce` 作为 message binding。

`review_hints` 是给后续人工 review、CI gate 或子智能体复核使用的机器可读提示，不替代 `ready` / `pure_extraction`。当前由 `reverse_deepagent.schemas.ReviewHint` 集中约束，固定字段为 `severity`、`category`、`code`、`message`、`evidence`，会覆盖 pure rebuild、context-aware rebuild、人工移植 / 部分 rebuild，以及 runtime-context diff 派生出的 volatile、session-bound、missing-field、type-drift 和 object-drift 风险。`evidence_score` 则是更紧凑的排序 / 下一步建议面，供 review / rebuild / 后续子智能体判断“强纯算候选、可 review 候选、需要更多证据、必须 runtime-assisted”；review gate 现在会保守消费该 score 作为 delivery gate 辅助信号，但它同样不替代 rebuild 的 ready 计算，也不会执行任何证据采集或 replay。

`workspace/runtime-context-diff.json` 会对运行时上下文做稳定性摘要。默认运行时会采集多次样本，兼容字段仍包括 `status`（legacy runtime 输出 `multi_sample` 或 `single_sample` 兜底）、`sample_count`、`stable`、`stable_keys`、`volatile_keys`、`missing_requirements` 和 `changes`；通用 diff 基线还会输出 `fields`、`summary` 和 `review_hints`，把字段细分为 `stable`、`volatile`、`session_bound`、`missing_in_some_samples`、`type_drift` 或 `object_drift`。其中 `sample_index` / `collected_at_ms` 只作为采样元数据，不参与稳定性判断；`token` / `cookie` / `csrf` / `session` / `auth` 等敏感路径只输出类型、长度和 digest 摘要，不落原值；`volatile_keys` 应被视为 replay 时仍需要运行时绑定的输入。

## 运行时后端能力

运行时后端能力通过 `RuntimeBackendCapabilities` 描述，调用方可以用 `runtime.describe_capabilities()` 做能力发现，而不是在 coordinator 中硬猜 MCP、Chrome 或 mock 后端的行为。

示例：

```python
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends

print(list_runtime_backends())

runtime = build_runtime("mock")
capabilities = runtime.describe_capabilities()
print(capabilities.model_dump(mode="json"))
```

`build_runtime(...)` 现在通过 `RuntimeBackendRegistry` 创建后端。架构方向是 `native-web` 通过 `BrowserProviderRegistry` 切换 `playwright-chromium`、`cloakbrowser`、`remote-cdp` 以及外部 BrowserProvider plugin，并把 MCP 降级为 legacy 兼容后端。BrowserProvider registry 会加载 `reverse_deepagent.browser_providers` Python entry-point group，`native-web` 的 provider 解析不再在 factory 里硬编码 if/else；metadata / doctor 路径不会启动浏览器或调用 provider factory。StrategyDetector registry 会加载 `reverse_deepagent.strategy_detectors` Python entry-point group，metadata listing 不运行 detector、不采集 runtime context、不执行 replay、不启动浏览器、不调用 MCP。Runtime registry 还会加载 `reverse_deepagent.runtime_backends` Python entry-point group 里的外部 backend registration，加载 metadata 时不会调用 backend factory；`legacy-mcp` 的 registration / factory / alias warning 已从 coordinator 内联代码挪到 `reverse_deepagent.runtime.legacy_mcp`，并且 `build_default_runtime_registry(include_legacy_mcp=False)` 可以构建不带 MCP backend 的 clean registry。仓库现在还包含 `packages/reverse-deepagent-legacy-mcp/` optional plugin package，声明 `reverse_deepagent.runtime_backends` entry point，并已拥有 legacy MCP registration / factory、`JSReverserMcpConfig` 和 stdio bridge 实现；同时包含 `packages/reverse-deepagent-browser-provider-template/` BrowserProvider 通用插件模板包、`packages/reverse-deepagent-browser-provider-hosted-cdp-template/` hosted CDP / 托管浏览器服务模板包、`packages/reverse-deepagent-browser-provider-browserless-cdp/` Browserless hosted CDP provider 包、`packages/reverse-deepagent-browser-provider-browserbase-cdp/` Browserbase hosted CDP provider 包和 `packages/reverse-deepagent-browser-provider-fixture/` functional fixture provider 包，它们都声明 `reverse_deepagent.browser_providers` entry point；通用模板作为接入自定义浏览器 provider 的复制起点，hosted CDP 模板作为第三方远程浏览器服务的 contract smoke 起点，Browserless 包证明真实 hosted CDP provider 可以通过外部 package 接入 HTTP DevTools 或 direct browser WebSocket endpoint，Browserbase 包证明真实 provider 可以显式调用第三方 Session API 并把返回的 `connectUrl` 纳入 BrowserProvider contract smoke，fixture 用于证明外部 provider package 可以不改 core runtime 就完成 metadata listing、factory 延迟调用和 launch/connect smoke。core 侧 `reverse_deepagent.runtime.legacy_mcp` 现在只保留兼容 shim、默认命令常量、alias warning、doctor 代理和 install guidance，不再内置 legacy MCP factory fallback 或 stdio MCP transport；默认 registry 会先加载外部 entry points，若未安装 `reverse-deepagent-legacy-mcp`，`--runtime legacy-mcp` / `mcp` 会返回结构化安装建议，并推荐继续使用 `native-web`。当前默认 registry metadata 通常包含以下 core backend；`legacy-mcp` 只有安装 optional plugin 后才会通过 entry point 出现在 registry / doctor matrix 中：

- `mock`（别名：`in-process`）：公开 CI 和本地 deterministic demo 使用
- `native-web`（别名：`web`, `browser-native`）：BrowserProvider-backed native Web runtime，目标默认路径，当前通过 `BrowserProviderRegistry` 支持 `playwright-chromium`、`cloakbrowser`、`remote-cdp` 与外部 `reverse_deepagent.browser_providers` plugin；真实二进制 smoke 需要显式触发
- `legacy-mcp`（别名：`mcp`, `jsreverser-mcp`）：optional plugin 提供的 legacy JSReverser MCP + Chrome DevTools 兼容运行时；未安装 `reverse-deepagent-legacy-mcp` 时不会出现在默认 matrix 中，`mcp` / `jsreverser-mcp` 仅作为旧命令 alias 保留，CLI 会输出 deprecation warning，新脚本应改用 `legacy-mcp`
- `playwright-cli`（别名：`playwright`, `pw-cli`）：轻量 Playwright CLI 探测与静态源码拉取，不主动启动浏览器
- `chrome-cdp`（别名：`cdp`, `devtools`）：连接既有 Chrome DevTools 端点，不主动启动 Chrome
- `browser-cli`（别名：`cli-browser`, `browser-command`）：通用浏览器 CLI 适配命令 backend，默认 command 未配置
- `android-adb`（别名：`adb`, `android-device`）：Android ADB 工具链探测与平台 artifact 导出
- `ios-simulator`（别名：`simctl`, `ios-sim`）：iOS Simulator / `xcrun simctl` 工具链探测与平台 artifact 导出
- `mini-program-devtools`（别名：`mp-devtools`, `wechat-devtools`）：小程序 vendor devtools CLI 配置探测与平台 artifact 导出

`reverse-agent-doctor --runtime-backends` 可 side-effect-free 输出 runtime backend matrix，列出 backend id、alias、target platforms、capability flags、entry point group 和 side-effect policy，且不会调用 backend factory 或启动外部工具。

每次 pipeline 会额外写出 `workspace/backend-artifact-manifest.json`，用 `RuntimeArtifactManifest` / `RuntimeArtifactManifestEntry` 描述 artifact key、路径、类别、kind、producer backend、transport 和 target platforms。这个 manifest 是新增索引，不替换现有 `exports/artifact-index.json`。跨平台 artifact category 词表见 [`docs/runtime/platform-neutral-artifact-categories.md`](docs/runtime/platform-neutral-artifact-categories.md)。

非 Web 运行时会沿用同一套 capability / manifest 边界，但不能复用 Web 专属的浏览器会话语义。当前接口草案：

- Android: [`docs/runtime/android-adapter-interface.md`](docs/runtime/android-adapter-interface.md)
- iOS: [`docs/runtime/ios-adapter-interface.md`](docs/runtime/ios-adapter-interface.md)
- Mini-program: [`docs/runtime/mini-program-adapter-interface.md`](docs/runtime/mini-program-adapter-interface.md)

当前 Web 路径的浏览器会话、Chrome 调试端口、JSReverser MCP、Web 存储、URL replay 推导等假设统一收口在 [`docs/runtime/web-runtime-assumptions.md`](docs/runtime/web-runtime-assumptions.md)，后续平台适配器不应默认继承这些语义。BrowserProvider 新架构见 [`docs/runtime/browser-provider-architecture.md`](docs/runtime/browser-provider-architecture.md)。

`JSReverserMcpConfig` 现在由 optional `reverse-deepagent-legacy-mcp` package 持有，字段包括 `command`、`browser_url`、`request_timeout`、`startup_timeout`、后端元数据和运行时采样参数。CLI 里的 `--jsreverser-mcp-command`、Chrome 调试端口等参数会通过 core shim 传给 optional package；未安装 optional package 时只返回结构化安装建议，不会在 core 中启动 MCP stdio transport。

兼容期内 `--runtime mcp` 和 `--runtime jsreverser-mcp` 仍可解析到 `legacy-mcp`，但会向 stderr 打印 deprecation warning；`reverse-agent-doctor --check-mcp` 也只作为 `--legacy-mcp` 的旧别名保留。后续新增文档、脚本和 workflow 不应继续使用旧 alias。

核心字段包括：

- `backend_id`：稳定后端标识，例如 `mock`、`native-web`、`legacy-mcp`
- `transport`：实现传输，例如 `in-process`、`mcp-stdio`
- `target_platforms`：当前目标平台，现阶段主要是 `web`
- `supports_web_recon` / `supports_runtime_context` / `supports_replay_validation`：能力开关
- `managed_chrome` / `mcp_backed`：运行时约束提示
- `evidence_kinds` / `artifact_kinds`：该后端常见输出类型

### `native-web` 能力边界速览

`native-web` / `remote-cdp` 在 BrowserProvider 支持 runtime eval 时，会沿用现有 workspace artifact 名称输出候选函数验证、调试、hook、module discovery、timeline 和 mutation audit 证据。它的默认原则是：**metadata / discovery / planning 默认只读，runtime 执行必须显式 protection、显式参数和 review gate**。

已实现的 baseline 包括：

- 候选函数验证：`workspace/function-candidates.json`、`workspace/function-validations.json`、`workspace/function-validation-summary.json`。
- 调试与 callframe：`workspace/debugger-paused.json`、`workspace/callframes.json`、`workspace/debugger-session.json`、`workspace/debugger-timeline.json`，显式 callframe evaluation 时补充 `workspace/callframe-evaluations.json` 和 `workspace/mutation-audit.json`；显式 live continuation preflight 时输出 `workspace/paused-session-live-continuation-preflight.json`，显式 cross-process target attach readiness proof 时输出 `workspace/paused-session-target-attach-readiness.json`，显式 cross-process paused-session execution plan 时输出 `workspace/paused-session-cross-process-execution-plan.json`；显式 cross-process session lifecycle review 时输出 `workspace/paused-session-cross-process-session-lifecycle.json`；显式 reviewed cross-process attach probe 时输出 `workspace/paused-session-cross-process-attach-probe.json`；显式 attach 后 live callFrame recovery proof 时输出 `workspace/paused-session-live-callframe-recovery.json`；显式 reviewed cross-process one-action execution 时输出 `workspace/paused-session-cross-process-one-action-execution.json`；显式 one-action 后 next paused-event capture plan 时输出 `workspace/paused-session-next-paused-event-capture-plan.json`；显式 reviewed next paused-event capture execution 时输出 `workspace/paused-session-next-paused-event-capture-execution.json`；显式 cross-process continuation checkpoint 时输出 `workspace/paused-session-cross-process-continuation-checkpoint.json`；显式 paused-session multi-step loop plan review 时输出 `workspace/paused-session-multi-step-loop-plan.json`；显式 review-gated paused-session loop iteration execution 时输出 `workspace/paused-session-multi-step-loop-execution.json`；显式 paused-session automatic loop readiness review 时输出 `workspace/paused-session-automatic-loop-readiness.json`；显式 future bounded automatic-loop executor plan review 时输出 `workspace/paused-session-automatic-loop-execution-plan.json`；显式 future bounded automatic-loop executor preflight review 时输出 `workspace/paused-session-automatic-loop-executor-preflight.json`；显式 future bounded automatic-loop executor approval / transaction plan review 时输出 `workspace/paused-session-automatic-loop-executor-approval-plan.json`；显式 automatic-loop one-iteration execution result 输出 `workspace/paused-session-automatic-loop-execution-result.json`；显式 automatic-loop follow-up checkpoint review 输出 `workspace/paused-session-automatic-loop-followup-checkpoint.json`，只审计 continuation checkpoint 与 next-loop plan 是否可进入下一轮 review，不写 checkpoint、不执行下一轮；显式 automatic-loop next-iteration plan review 输出 `workspace/paused-session-automatic-loop-next-iteration-plan.json`，只把 ready follow-up checkpoint、continuation checkpoint、next-loop plan 和 fresh live callFrame recovery evidence 归一成下一轮 execution review input，不 recover callFrame、不发送 CDP、不执行下一轮、不 advance queue / loop；显式 automatic-loop next-iteration execution 输出 `workspace/paused-session-automatic-loop-next-iteration-execution.json`，只在 review approval 后委托现有 loop executor 执行最多一轮并强制后续 checkpoint；显式 automatic-loop next-iteration follow-up checkpoint review 输出 `workspace/paused-session-automatic-loop-next-iteration-followup-checkpoint.json`，只审计 Step 253 执行后的 continuation checkpoint 与 next-loop plan 是否可进入后续 iteration review，不写 checkpoint、不恢复 callFrame、不执行下一轮；显式 automatic-loop following-iteration plan review 输出 `workspace/paused-session-automatic-loop-following-iteration-plan.json`，只把 ready next-iteration follow-up checkpoint、continuation checkpoint、next-loop plan 和 fresh live callFrame evidence 归一成后续 execution review input，不写 checkpoint、不恢复 callFrame、不发送 CDP、不执行 iteration、不 advance queue / loop；显式 automatic-loop bounded multi-iteration policy review 输出 `workspace/paused-session-automatic-loop-multi-iteration-policy.json`，只消费 ready following-iteration plan 和显式预算，归一 per-iteration review / checkpoint / fresh live callFrame gate、stop conditions 与未来 `execute_paused_session_automatic_loop_multi_iteration` executor contract，并固定 `implemented=false` / `automatic_multi_iteration_execution_allowed_now=false`，不执行多轮；显式 automatic-loop multi-iteration executor preflight review 输出 `workspace/paused-session-automatic-loop-multi-iteration-executor-preflight.json`，只消费 ready policy 并检查 bounded iteration、transaction journal、per-iteration review / checkpoint / fresh live callFrame gate；显式 automatic-loop multi-iteration execution plan review 输出 `workspace/paused-session-automatic-loop-multi-iteration-execution-plan.json`，只消费 ready preflight 并生成未来 executor review input；显式 automatic-loop multi-iteration executor approval / transaction plan review 输出 `workspace/paused-session-automatic-loop-multi-iteration-executor-approval-plan.json`，只消费 ready execution plan 并规划 approval record、idempotency key、transaction journal 和 result artifact 要求，固定 `approval_recorded=false`、`transaction_started=false`、`journal_written_now=false`、`ready_to_execute_now=false` 与 `future_executor_contract.implemented=false`，不记录审批、不写 journal、不执行多轮；显式 multi-iteration reviewer approval record apply 时输出 `workspace/paused-session-automatic-loop-multi-iteration-executor-approval-record.json`，只记录审批 metadata，不启动 transaction、不写 executor journal、不执行多轮；显式 multi-iteration transaction preflight review 输出 `workspace/paused-session-automatic-loop-multi-iteration-transaction-preflight.json`，只消费 ready approval plan 和 written approval record，审计 journal writer 输入、planned journal entries 与 transaction gate，固定 `ready_to_write_now=false` / `journal_written=false` / `transaction_started=false`，不写 journal、不启动 transaction、不执行多轮；显式 multi-iteration transaction journal apply 时输出 `workspace/paused-session-automatic-loop-multi-iteration-executor-journal.json`，只在 reviewer / apply / write_result / approve_transaction_journal gates 全部通过后写 journal audit artifact，标记 transaction_started / journal_written，但固定 `ready_to_execute_now=false`、`automatic_multi_iteration_loop=false`，不发送 CDP、不执行多轮；显式 multi-iteration bounded executor gate review 输出 `workspace/paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json`，只消费 written journal 并生成未来 `execute_paused_session_automatic_loop_multi_iteration` result contract，继续固定 `ready_to_execute_now=false`、`future_executor_contract.implemented=false`、`automatic_multi_iteration_loop=false`；显式 multi-iteration bounded executor MVP 输出 `workspace/paused-session-automatic-loop-multi-iteration-execution-result.json`，只在 ready gate / written journal / ready loop plan / ready workflow / fresh live callFrame / retained session 和 review approval 都满足时委托现有 loop executor 执行最多一个 reviewed iteration，并强制后续 checkpoint review；显式 multi-iteration execution follow-up checkpoint review 输出 `workspace/paused-session-automatic-loop-multi-iteration-followup-checkpoint.json`，只审计 Step 264 execution result、continuation checkpoint 与 next loop plan 是否可进入下一次 multi-iteration step review，不写 checkpoint、不恢复 callFrame、不执行下一轮、不 advance queue / loop；显式 reviewer approval record apply 时输出 `workspace/paused-session-automatic-loop-executor-approval-record.json`，只记录审批，不启动 transaction、不写 executor journal、不执行循环。
- Hook：全局函数 wrapper、webpack-like module export wrapper、remote federation export wrapper follow-through、source-level logpoint、closure-scope function discovery、review-only `closure-wrapper-replacement-plan`、review-only `closure-wrapper-assignment-safety` proof、review-only `closure-wrapper-runtime-mutability-preflight`、review-approved `closure-wrapper-runtime-mutability-result` 临时 assignment probe / restore audit，closure wrapper strategy descriptor/catalog metadata（当前仅 `log-only-call-through` 可 reviewed install，`arg-preview` / `return-preview` / `throw-preview` / `blocked-mutation-plan` 仍为 plan-only descriptor），以及支持可选 runtime-mutability-result gate 的 gated same-process reviewed `closure-wrapper-replacement-execution` MVP、reviewed `closure-wrapper-restore-execution` baseline、read-only `closure-wrapper-events` harvesting baseline、read-only `closure-wrapper-continuation-readiness` review descriptor、review-only `closure-wrapper-continuation-execution-plan` descriptor，以及 review-gated `closure-wrapper-continuation-execution` one-iteration executor、read-only `closure-wrapper-continuation-checkpoint` follow-up descriptor、review-only `closure-wrapper-continuation-next-iteration-plan` descriptor、review-gated `closure-wrapper-continuation-next-iteration-execution` one-step executor，并输出对应 hook / debugger timeline、assignment-safety、runtime-mutability-preflight、runtime-mutability-result、execution、restore-plan、events、continuation-readiness、continuation-execution-plan、continuation-execution、continuation-checkpoint、continuation-next-iteration-plan、continuation-next-iteration-execution 或 plan artifact。
- Module discovery：webpack-like `require.c` / `require.m` 只读 introspection、custom object runtime、module federation exposed-module function-path candidate、只读 async chunk graph / loader metadata。
- Custom-loader / async-chunk：review-only traversal plan、graph / queue、workflow plan、review-gated one-step workflow execution、bounded loop plan、review-gated bounded loop execution、custom-loader recursive traversal follow-up plan、review-gated recursive follow-up checkpoint、review-gated recursive next-loop execution、async-chunk recursive traversal follow-up plan、review-gated async recursive follow-up checkpoint、review-gated async recursive next-loop execution、module diff refresh、reviewed module hook follow-through，以及跨 custom-loader / async-chunk / federation 的只读 `recursive-continuation-readiness` 统一审阅 descriptor。
- Federation：review-only `get/init` plan、review-gated `init/get` probe、review-gated remote factory invoke、review-only export hook plan、review-approved export hook install，以及 review-only federation traversal graph / workflow plan、review-gated traversal workflow execution、review-only federation recursive traversal follow-up plan、review-gated federation recursive traversal follow-up checkpoint、review-gated federation recursive traversal next-step execution、review-only federation recursive continuation journal / multi-step checkpoint planning、review-gated federation recursive continuation checkpoint execution，以及参与统一 `recursive-continuation-readiness` descriptor 的 baseline。
- Paused session multi-iteration follow-up：`paused-session-automatic-loop-multi-iteration-followup-checkpoint` 消费 Step 264 execution result、可选 continuation checkpoint 与可选 next loop plan，输出 `reverse-deepagent.paused-session-automatic-loop-multi-iteration-followup-checkpoint.v1` / `workspace/paused-session-automatic-loop-multi-iteration-followup-checkpoint.json`；它只是 read-only / review-only handoff descriptor，不写 checkpoint、不 recover live callFrame、不发送 CDP、不订阅或捕获 paused event、不执行下一轮、不 advance queue / loop、不管理 long-lived session、不调用 MCP，也不触碰 Android / iOS / 小程序完整链路。
- Paused session multi-iteration next-step plan：`paused-session-automatic-loop-multi-iteration-next-step-plan` 消费 ready Step 265 follow-up checkpoint、continuation checkpoint、ready next loop plan 与可选 fresh live callFrame recovery evidence，输出 `reverse-deepagent.paused-session-automatic-loop-multi-iteration-next-step-plan.v1` / `workspace/paused-session-automatic-loop-multi-iteration-next-step-plan.json`；它只是 read-only / review-only / plan-only descriptor，用于把 handoff 归一成下一次显式 Step 264 executor review input，不写 checkpoint、不 recover live callFrame、不发送 CDP、不订阅或捕获 paused event、不执行 iteration、不 advance queue / loop、不管理 long-lived session、不调用 MCP，也不触碰 Android / iOS / 小程序完整链路。
- Paused session multi-iteration executor-input preflight：`paused-session-automatic-loop-multi-iteration-executor-input-preflight` 消费 ready Step 266 next-step plan，并只读校验 Step 264 executor 所需的 written transaction journal、ready bounded executor gate、ready loop plan、ready workflow、fresh live callFrame evidence 与 retained attached session，输出 `reverse-deepagent.paused-session-automatic-loop-multi-iteration-executor-input-preflight.v1` / `workspace/paused-session-automatic-loop-multi-iteration-executor-input-preflight.json`；它只是 read-only / review-only / preflight-only descriptor，用于进入显式 Step 264 executor review，不调用 executor、不写 checkpoint、不 recover live callFrame、不发送 CDP、不订阅或捕获 paused event、不执行 iteration、不 advance queue / loop、不管理 long-lived session、不调用 MCP，也不触碰 Android / iOS / 小程序完整链路。
- Source map：generated bundle offset、Source Map exact / bias / `sourceRoot` / indexed section / `names` / URL equivalence / nested indexed-section remap、review-only `source-map-lookup` descriptor、review-only `source-map-source-content` availability descriptor、review-only `source-map-readiness` join descriptor、review-only `source-map-consumer-action-plan` descriptor、review-only `source-map-consumer-materialization` descriptor、read-only / review-only / preflight-only `source-map-typed-payload-preflight` descriptor、review-only / handoff-only `source-map-followthrough-review` descriptor、review-only / selection-only `source-map-followthrough-surface-selection` descriptor、review-only / preflight-only `source-map-selected-executor-input-review` descriptor、review-only / approval-plan-only / apply-plan-only `source-map-selected-executor-approval-plan` descriptor、explicit-review-only `source-map-followthrough-dispatch-approval-record` writer、read-only / review-only `source-map-followthrough-dispatch-transaction-preflight` descriptor、explicit-review-only `source-map-followthrough-dispatch-transaction-journal` writer、read-only / review-only `source-map-followthrough-dispatch-bounded-executor-gate` descriptor、review-only bundler symbol scope descriptor，以及 review-gated credentialless source-map fetch metadata。`source-map-lookup` 只消费调用方提供的 Source Map payload 与 generated/original 位置，输出 `workspace/source-map-lookup.json`，不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-source-content` 只消费调用方提供的 Source Map `sourcesContent`，输出 `workspace/source-map-source-content.json` 的 availability / digest / size / line-count metadata，不导出 raw source content 或 preview，不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-readiness` 消费既有 lookup / source-content / bundler-symbol-scope / fetch metadata descriptors，输出 `workspace/source-map-readiness.json`，只判断 debugger / rebuild / source-logpoint planning 是否进入 review-ready，不导出 raw source 或 preview，不 fetch Source Map、不启动浏览器、不安装 logpoint、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-consumer-action-plan` 消费 readiness / lookup / source-content / bundler-symbol-scope descriptors，输出 `workspace/source-map-consumer-action-plan.json`，只生成 debugger location、source-logpoint、rebuild source metadata 和 hook symbol-scope 的 reviewed action plan，不执行 debugger、不写 rebuild、不安装 logpoint 或 hook、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-consumer-materialization` 消费 ready action plan 和可选 lookup / source-content / bundler-symbol-scope descriptors，输出 `workspace/source-map-consumer-materialization.json`，只把 selected action ids / consumers materialize 成 debugger location、source-logpoint、rebuild metadata、hook symbol-scope 的 `reverse-deepagent.source-map-consumer-typed-review-payload.v1` typed review payloads，并在 descriptor / native-web artifact metadata 暴露 `typed_payload_schema_version`、`typed_review_payload_count` 和 `typed_review_payload_consumers`，不执行 debugger、不安装 logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-typed-payload-preflight` 消费 materialization typed payloads 或显式 `typed_review_payloads`，输出 `workspace/source-map-typed-payload-preflight.json`，只校验 debugger / source-logpoint / rebuild / hook follow-through executor input 和 review surface，不执行 debugger、不安装 source-logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-followthrough-review` 消费 ready typed-payload preflight 或显式 preflight payloads，输出 `workspace/source-map-followthrough-review.json`，只把 debugger / source-logpoint / rebuild / hook follow-through surfaces 归一成显式 review handoff，不执行 debugger、不安装 source-logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-followthrough-surface-selection` 消费 ready followthrough review 或显式 review items，输出 `workspace/source-map-followthrough-surface-selection.json`，只显式选择一个 debugger / source-logpoint / rebuild / hook follow-through surface 进入 downstream review，不执行 debugger、不安装 source-logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-selected-executor-input-review` 消费 ready surface selection 或显式 selected review / executor input，输出 `workspace/source-map-selected-executor-input-review.json`，只把选中的 debugger / source-logpoint / rebuild / hook executor input 归一成 downstream review package 与 review gate，不执行 surface、不安装 source-logpoint 或 hook、不执行 rebuild、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-selected-executor-approval-plan` 消费 ready selected executor-input review 或显式 executor review package，输出 `workspace/source-map-selected-executor-approval-plan.json`，只规划 approval requirements 与 future apply contract，固定 `approval_recorded=false`、`ready_to_apply_now=false`，不记录 approval、不写 approval artifact、不执行 debugger / source-logpoint / rebuild / hook surface、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-selected-executor-apply-preflight` 消费 ready approval plan 和 written approved approval record，输出 `workspace/source-map-selected-executor-apply-preflight.json`，只校验 selected action / consumer / review gate / approval-record id / plan digest / executor input / no-side-effect gates，固定 `ready_to_apply_now=false` 与 `future_executor_contract.implemented=false`，不执行 debugger / source-logpoint / rebuild / hook surface、不导出 raw source 或 preview、不 fetch Source Map、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-source-logpoint-install` 是第一个 selected executor application MVP，只在 `mode=apply`、`review_approved=true`、`approve_source_logpoint_install=true`、reviewer、ready source-logpoint apply-preflight 和 reviewed `source_logpoint_install_input` 齐全时安装 source-logpoint，输出 `workspace/source-map-source-logpoint-install-result.json` 并复用 `workspace/source-logpoints.json` / `workspace/source-logpoint-timeline.json`，不调用 MCP，也不触碰移动端完整链路；`source-map-debugger-application` 是 explicit-review-only debugger selected executor application MVP，只在 `mode=apply`、`review_approved=true`、`approve_source_map_debugger_action=true`、reviewer、ready debugger apply-preflight 和 reviewed `source_map_debugger_location_input` 齐全时，复用 `BreakpointManager` 对一个 reviewed bundle URL / line location 发送最小 Debugger breakpoint 命令，输出 `workspace/source-map-debugger-execution-result.json` 并复用 `workspace/breakpoints.json` / `workspace/debugger-paused.json` / `workspace/callframes.json` / 可选 debugger action/session/timeline artifacts；blocked 路径不启动浏览器，成功路径不自动 continuation、不自动 recover live callFrame、不自动 loop、不调用 MCP，也不触碰移动端完整链路；`source-map-debugger-candidates` 是 read-only / review-only / plan-only 的 debugger location candidate descriptor，消费 ready Source Map lookup / `bundler-symbol-scope` 以及可选 reviewed debugger location hints，输出 `workspace/source-map-debugger-candidates.json` / `reverse-deepagent.source-map-debugger-candidates.v1`，只生成 generated-location candidates、confidence signals、review blockers 和 suggested explicit debugger location inputs；它不安装 breakpoint、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不执行 debugger continuation、不 fetch Source Map、不导出 raw source / preview、不调用 MCP，也不触碰移动端完整链路，后续 selected debugger apply 仍必须走 explicit review approval 和 concrete `source_map_debugger_location_input`；`source-map-debugger-candidate-selection` 是 read-only / review-only / plan-only / handoff-only 的 debugger candidate selection descriptor，消费 ready `source-map-debugger-candidates`，选择一个 reviewed candidate，输出 `workspace/source-map-debugger-candidate-selection.json` / `/workspace/debugger/source-map-debugger-candidate-selection.json` 和 `reverse-deepagent.source-map-debugger-candidate-selection.v1`，并生成可传给 `source-map-selected-executor-input-review` 的 `source_map_selected_executor_input_review_context`；它不调用 selected executor review、不安装 breakpoint、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不 recover live callFrame、不执行 debugger continuation、不 fetch Source Map、不导出 raw source / preview、不调用 MCP，也不触碰移动端完整链路；`source-map-debugger-candidate-selected-input-review` / `source-map-debugger-candidate-executor-input-review` 是 read-only / review-only / preflight-only helper，消费 ready `source-map-debugger-candidate-selection` 及其 handoff context，复用现有 `source-map-selected-executor-input-review` manager，输出 canonical `workspace/source-map-selected-executor-input-review.json` / `reverse-deepagent.source-map-selected-executor-input-review.v1`，只生成 downstream executor review package，不安装 breakpoint、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不执行 selected executor、不调用 MCP，也不触碰移动端完整链路；`source-map-hook-application` 是 explicit-review-only hook selected executor application MVP，只在 `mode=apply`、`review_approved=true`、`approve_source_map_hook_install=true`、reviewer、ready hook apply-preflight 和 reviewed concrete `source_map_hook_install_input` 齐全时，复用 native function / module hook manager 安装一个 reviewed hook，输出 `workspace/source-map-hook-install-result.json` 并复用 `workspace/function-hooks.json` / `workspace/function-hook-timeline.json` 或 `workspace/module-hooks.json` / `workspace/module-hook-timeline.json`，blocked 路径不启动浏览器，成功路径不从 Source Map symbol-scope 自动推断 hook path、不发送 CDP debugger command、不调用 MCP，也不触碰移动端完整链路；`source-map-hook-candidates` 是 read-only / review-only / plan-only 的 hook candidate refinement descriptor，消费 ready `bundler-symbol-scope` 以及可选 reviewed function paths / module discovery hints，输出 `workspace/source-map-hook-candidates.json` / `reverse-deepagent.source-map-hook-candidates.v1`，只生成 function-symbol / module-export hook candidates、confidence signals、review blockers 和 suggested explicit hook install inputs；它不安装 hook、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不 fetch Source Map、不导出 raw source / preview、不调用 MCP，也不触碰移动端完整链路，后续 selected hook install 仍必须走 explicit review approval 和 concrete `source_map_hook_install_input`；`source-map-hook-candidate-selection` 是 read-only / review-only / plan-only / handoff-only 的 hook candidate selection descriptor，消费 ready `source-map-hook-candidates`，选择一个 reviewed candidate，输出 `workspace/source-map-hook-candidate-selection.json` / `/workspace/hooks/source-map-hook-candidate-selection.json` 和 `reverse-deepagent.source-map-hook-candidate-selection.v1`，并生成可传给 `source-map-selected-executor-input-review` 的 `source_map_selected_executor_input_review_context`；它不调用 selected executor review、不安装 hook、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不 fetch Source Map、不导出 raw source / preview、不调用 MCP，也不触碰移动端完整链路；`source-map-hook-candidate-selected-input-review` / `source-map-hook-candidate-executor-input-review` 是 read-only / review-only / preflight-only helper，消费 ready `source-map-hook-candidate-selection` 及其 handoff context，复用现有 `source-map-selected-executor-input-review` manager，输出 canonical `workspace/source-map-selected-executor-input-review.json` / `reverse-deepagent.source-map-selected-executor-input-review.v1`，只生成 downstream executor review package，不安装 hook、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不执行 selected executor、不调用 MCP，也不触碰移动端完整链路；`source-map-rebuild-metadata-application` 是 digest-only rebuild selected executor application MVP，只在 `mode=apply`、`review_approved=true`、`approve_source_map_rebuild_metadata=true`、reviewer、ready rebuild apply-preflight 和 reviewed `rebuild_source_metadata_input` 齐全时输出 `workspace/source-map-rebuild-result.json` 审计 metadata，固定 `metadata_only=true`、`rebuild_metadata_applied=true`、`rebuild_bundle_generated=false`、`rebuild_executed=false`，不生成 rebuild bundle、不导出 raw source / preview、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-rebuild-generation` 是 explicit-review-only reviewed rebuild bundle generation MVP，只在 `mode=apply`、`review_approved=true`、`approve_source_map_rebuild_generation=true`、reviewer、successful metadata-only `source_map_rebuild_result`、local `artifact_root`、reviewed `task_card` 和 reviewed `final_result` 齐全时复用 `write_rebuild_bundle(...)` 写 `workspace/rebuild-plan.json` 与 `rebuild/sign_rebuild.py` / `rebuild/replay_demo.py` / `rebuild/scrapy_middleware.py` / Scrapy project，并输出 `workspace/source-map-rebuild-generation-result.json`；blocked 路径不创建目录，成功路径不 fetch Source Map、不导出 raw source / preview、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP、不执行 replay / scrapy / delivery，也不触碰移动端完整链路；`source-map-followthrough-completion-checkpoint` 是 read-only / review-only / checkpoint-only 的 Source Map follow-through completion / next-action descriptor，消费 ready `source-map-selected-executor-result-checkpoint` 和可选 chain-readiness / rebuild-generation evidence，输出 `workspace/source-map-followthrough-completion-checkpoint.json`，只归一 terminal review candidate、followup requirement 和 recommended review action，不调用 selected executor application、不继续 debugger、不安装 hook / source-logpoint、不运行 rebuild generation、不 delivery、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-terminal-review-package` / `source-map-terminal-review-handoff` 是 read-only / review-only / audit-handoff-only terminal review package，消费 ready `source-map-followthrough-completion-checkpoint` 和可选 `source-map-selected-executor-result-checkpoint` evidence，输出 `workspace/source-map-terminal-review-package.json` / `/workspace/review/source-map-terminal-review-package.json`，只包装 terminal review / follow-up review evidence、recommended review action、required artifacts 和 manual review steps，不执行 recommended action、不调用 selected executor application、不继续 debugger、不安装 hook / source-logpoint、不运行 rebuild generation、不 delivery、不 fetch Source Map、不导出 raw source / preview、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-terminal-review-closure-checkpoint` / `source-map-terminal-review-observed-result-checkpoint` 是 read-only / review-only / audit-checkpoint-only observed-result closure checkpoint，消费 ready `source-map-terminal-review-package` 和 reviewer-provided observed result evidence，输出 `workspace/source-map-terminal-review-closure-checkpoint.json` / `/workspace/review/source-map-terminal-review-closure-checkpoint.json`，只记录 observed review action、closure status、required artifacts、package digest、observed-result digest 和 review notes digest，不执行 recommended action、不调用 selected executor application、不继续 debugger、不安装 hook / source-logpoint、不运行 rebuild generation、不 delivery、不 fetch Source Map、不导出 raw source / preview、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-terminal-review-final-audit` / `source-map-terminal-review-closure-summary` 是 read-only / review-only / audit-rollup-only final audit descriptor，消费 ready `source-map-terminal-review-closure-checkpoint` 和可选 terminal package evidence，输出 `workspace/source-map-terminal-review-final-audit.json` / `/workspace/review/source-map-terminal-review-final-audit.json`，只汇总 final audit status、observed review action、recommended review action、required artifacts、closure digest、terminal package digest 和 observed-result digest，不执行 recommended action、不调用 selected executor application、不继续 debugger、不安装 hook / source-logpoint、不运行 rebuild generation、不 delivery、不 fetch Source Map、不导出 raw source / preview、不启动浏览器、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路；`source-map-terminal-review-action-decision` / `record-source-map-terminal-review-action` 是 minimal explicit-review-only terminal review action decision/result recorder，消费 ready terminal review package、closure checkpoint 或 final audit，记录 reviewer、reason、selected action（`defer` / `approve_followup` / `reject` / `request_manual_execution` / `mark_complete`）、source descriptor digest、deterministic decision id、idempotency key 和 decision digest，side-effect policy 固定 `executes_recommended_action=false`、`installs_hook=false`、`installs_logpoint=false`、`continues_debugger=false`、`generates_rebuild=false`、`fetches_source_map=false`、`exports_raw_source=false`，不执行 recommended action、不安装 hook / logpoint、不继续 debugger、不生成 rebuild、不 fetch Source Map、不导出 raw source、不调用 MCP，也不触碰移动端完整链路；`bundler-symbol-scope` 只消费调用方提供的 Source Map / script / module hints，输出 `workspace/bundler-symbol-scope.json`，不 fetch Source Map、不安装 source logpoint、不 evaluate JavaScript、不发送 CDP、不调用 MCP，也不触碰移动端完整链路。
- Heap snapshot readiness / collect / diff readiness / diff executor preflight / approval plan：显式 `heap-snapshot-readiness` / `cdp-heap-snapshot-readiness` 只读预检会输出 `workspace/heap-snapshot-readiness.json` / `virtual://workspace/heap-snapshot-readiness.json`，仅归一调用方提供的 BrowserProvider / CDP / HeapProfiler capability evidence、size budget 和 redaction gate；它不启动浏览器、不调用 provider factory、不发送 CDP、不启用 HeapProfiler、不采集 heap snapshot、不导出 raw heap、不宣称 complete heap traversal。显式 `heap-snapshot-collect` / `cdp-heap-snapshot-collect` 是 review-gated one-shot MVP，只在 `review_approved=true`、`collect_heap_snapshot=true` 且 ready readiness descriptor 齐全时通过当前 BrowserProvider 页面 CDP session 发送 `HeapProfiler.enable` / `HeapProfiler.takeHeapSnapshot` / `HeapProfiler.disable`，输出 `workspace/heap-snapshot-collect.json` / `virtual://workspace/heap-snapshot-collect.json` 的 digest / byte-count / chunk-count metadata；它不导出 raw heap、不计算 heap diff、不宣称 complete heap traversal、不调用 MCP，也不触碰 Android / iOS / 小程序完整链路。显式 `heap-snapshot-diff-readiness` / `review-heap-snapshot-diff` 只消费两个已 review 的 collect metadata descriptor，输出 `workspace/heap-snapshot-diff-readiness.json` / `virtual://workspace/heap-snapshot-diff-readiness.json` 的 pair summary、digest / byte delta 和 future diff executor gate；它不加载 raw heap、不计算 heap diff、不启动浏览器、不发送 CDP、不调用 MCP，也不触碰移动端完整链路。显式 `heap-snapshot-diff-executor-preflight` / `raw-heap-diff-preflight` 是下一层 review-only executor gate，只审查 ready diff-readiness、review approval、raw heap ingestion policy、parser sandbox、redaction plan 和 size budget，输出 `workspace/heap-snapshot-diff-executor-preflight.json` / `virtual://workspace/heap-snapshot-diff-executor-preflight.json`，固定 `diff_executor_implemented=false`，不读取、不解析、不导出 raw heap，也不计算 heap diff。显式 `heap-snapshot-diff-executor-approval-plan` / `raw-heap-diff-approval-plan` 继续只生成 approval / transaction plan，输出 `workspace/heap-snapshot-diff-executor-approval-plan.json` / `virtual://workspace/heap-snapshot-diff-executor-approval-plan.json`，固定 `approval_recorded=false`、`transaction_started=false`、`journal_written_now=false`、`executor_invoked=false` 和 `future_executor_contract.implemented=false`，不记录审批、不写 journal、不调用 executor、不加载 raw heap、不计算 heap diff。显式 `record_heap_snapshot_diff_executor_approval` 只在 `mode=apply`、`write_result=true`、`approve_heap_snapshot_diff_executor=true`、reviewer 和 ready approval-plan guards 齐全时写 `workspace/heap-snapshot-diff-executor-approval-record.json` 审批记录；它不启动 transaction、不写 journal、不写 bounded gate、不调用 executor、不读取 / 解析 / 导出 raw heap、不计算 heap diff。
- Mutation audit：page-level mutation audit、descriptor-safe object-root mutation audit、review-only object graph diff descriptor、explicit scoped runtime-collected object graph diff、MutationObserver timeline；page / object-root / observer 路径围绕显式 trigger 工作，`object-graph-diff` 只消费调用方提供的 before/after snapshots，输出 `workspace/object-graph-diff.json`，不启动浏览器、不采集 heap、不 evaluate JavaScript、不发送 CDP、不调用 MCP；`runtime-object-graph-diff` 只在显式请求时对一个 strict dotted object root 做 bounded descriptor-safe runtime collection，输出 `workspace/runtime-object-graph-diff.json`，可执行显式 trigger，但不调用 getter、不遍历 prototype、不发送 CDP、不调用 MCP、不采集 full heap。
- Paused session：同进程 retained paused-session registry 支持 live inspect / evaluate / step / resume；durable paused-session snapshot 只支持跨进程 inspect / audit，不支持跨进程 resume / step / evaluate；`paused-session-live-continuation-preflight` 提供只读 live continuation preflight，可审计 same-process registry、durable snapshot 或 caller-provided debugger artifact 的 live action blockers，并输出 `live_session_diagnostics`、`target_diagnostics`、`callframe_diagnostics`、`action_capability` 和 blocker details；`paused-session-target-attach-readiness` 进一步生成只读 target attach readiness proof，审计 paused-session source、target URL / targetId correlation、CDP target attachability、stable live callFrameId recovery requirement 和 action matrix；`paused-session-cross-process-execution-plan` 可消费该 readiness proof，生成 `reverse-deepagent.paused-session-cross-process-execution-plan.v1` 的 reviewed executor plan，列出 reviewed attach probe、live callFrame recovery 和单步 live action review gates；`paused-session-cross-process-session-lifecycle` 可消费 preflight / readiness / execution plan / attach probe / live callFrame recovery / checkpoint / multi-step evidence，输出 `reverse-deepagent.paused-session-cross-process-session-lifecycle.v1` 的 read-only lifecycle descriptor，用于审计 retained attached session、target lifecycle evidence、live callFrame freshness、checkpoint readiness 和自动化边界；它不 attach、不 probe、不恢复 callFrame、不订阅事件、不执行 action、不循环；`paused-session-cross-process-attach-probe` 在 `execute_cross_process_attach_probe=true` 且 `review_approved=true` 时可执行一次受控 `Target.attachToTarget`，默认随后 `Target.detachFromTarget`，并输出 `reverse-deepagent.paused-session-cross-process-attach-probe.v1`；`paused-session-live-callframe-recovery` 可在已有 reviewed attach probe 和调用方提供 fresh paused event / callFrames 时输出 `reverse-deepagent.paused-session-live-callframe-recovery.v1`，证明是否获得 attach 后的新鲜 live `callFrameId`；`paused-session-cross-process-one-action` 可在 recovery proof、retained attached session id、显式 `execute_cross_process_one_action=true` 和 `review_approved=true` 都满足时输出 `reverse-deepagent.paused-session-cross-process-one-action-execution.v1`，只发送一次 reviewed `Debugger.resume` / `Debugger.stepOver` / `Debugger.stepInto` / `Debugger.stepOut` / `Debugger.evaluateOnCallFrame`。`paused-session-next-paused-event-capture-plan` 可消费 one-action execution artifact，输出 `reverse-deepagent.paused-session-next-paused-event-capture-plan.v1` 的 review-only 下一次 `Debugger.paused` 捕获计划，用于 step / resume 后规划未来事件订阅、等待窗口和 live callFrame recovery follow-up；它不订阅事件、不发送 CDP、不捕获 paused event、不循环执行。`paused-session-next-paused-event-capture-execution` 可在 ready plan、retained attached session、`execute_next_paused_event_capture=true` 和 `review_approved=true` 都满足时输出 `reverse-deepagent.paused-session-next-paused-event-capture-execution.v1`，只订阅 / 等待一个 bounded `Debugger.paused` 事件或归一化调用方提供的 observed paused event，并把捕获到的 callFrames 交给后续 live callFrame recovery；它不发送 Debugger step / resume / evaluate 命令、不启用 Debugger domain、不循环、不自动恢复 callFrame。`paused-session-cross-process-continuation-checkpoint` 可消费该 capture execution artifact，输出 `reverse-deepagent.paused-session-cross-process-continuation-checkpoint.v1` 的 review-only checkpoint，用于决定下一步恢复 live callFrame 还是规划下一次 reviewed one-action；它不发送 CDP、不订阅事件、不捕获 paused event、不 resume / step / evaluate、不自动恢复 callFrame、不执行 action、不循环、不调用 MCP，也不触碰移动端完整链路。`paused-session-automatic-loop-readiness` 可消费 ready multi-step loop plan、workflow、session lifecycle、latest loop execution 与 continuation checkpoint evidence，输出 `reverse-deepagent.paused-session-automatic-loop-readiness.v1` 的 read-only / review-only / plan-only readiness descriptor，为未来 bounded automatic loop executor 提供机器可读 gate；`paused-session-automatic-loop-execution-plan` 进一步消费 ready readiness descriptor，输出 `reverse-deepagent.paused-session-automatic-loop-execution-plan.v1` 的 review-only / plan-only future executor review input，列出 bounded planned iterations、per-iteration review gate 和 `future_executor_contract.implemented=false`；`paused-session-automatic-loop-executor-preflight` 再消费 ready execution plan，输出 `reverse-deepagent.paused-session-automatic-loop-executor-preflight.v1` 的 read-only / review-only / preflight-only / plan-only gate，为未来 bounded executor 检查 per-iteration review、checkpoint 和预算，但固定 `executor_input_gates.ready_to_execute_now=false` 与 `future_executor_contract.implemented=false`；`paused-session-automatic-loop-executor-approval-plan` 消费 ready executor preflight，输出 `reverse-deepagent.paused-session-automatic-loop-executor-approval-plan.v1` 的 review-only / approval-plan-only / transaction-plan-only descriptor，规划 approval record、idempotency key、transaction journal 和 result artifact 要求，但固定 `approval_recorded=false`、`transaction_started=false`、`journal_written=false`、`ready_to_execute_now=false` 与 `future_executor_contract.implemented=false`；`record_paused_session_automatic_loop_executor_approval` 只在显式审批下写 approval record；`review_paused_session_automatic_loop_transaction_preflight` 再消费 ready approval plan 和 written approved approval record，输出 `reverse-deepagent.paused-session-automatic-loop-transaction-preflight.v1` 的 read-only / transaction-preflight-only descriptor，固定 `ready_to_write_now=false`、`transaction_started=false` 与 `journal_written_now=false`；`record_paused_session_automatic_loop_transaction_journal` 只在显式审批下写 `reverse-deepagent.paused-session-automatic-loop-transaction-journal.v1` transaction journal，标记 journaled transaction 已开始但固定 `ready_to_execute_now=false` 与 `automatic_loop_executed=false`；`review_paused_session_automatic_loop_bounded_executor_gate` 消费 written transaction journal，输出 `reverse-deepagent.paused-session-automatic-loop-bounded-executor-gate.v1` 的 read-only final gate 和未来 result contract，但仍固定 `ready_to_execute_now=false`、`future_executor_contract.implemented=false` 与 `automatic_loop_executed=false`；`execute-paused-session-automatic-loop` / `paused-session-automatic-loop-execution` 在 native-web 中提供 explicit-review-only bounded one-iteration MVP，消费 ready gate、written transaction journal、ready multi-step loop plan、ready workflow、fresh live callFrame recovery 和 retained attached session 后，只有在 `execute_paused_session_automatic_loop=true` 且 `review_approved=true` 时才委托现有 loop executor 执行最多一个 iteration，输出 `reverse-deepagent.paused-session-automatic-loop-execution-result.v1` / `workspace/paused-session-automatic-loop-execution-result.json`，并强制 `checkpoint_required=true`、`loop_advanced=false`、`queue_advanced=false`。`paused-session-automatic-loop-followup-checkpoint` 再消费该执行结果、可选 continuation checkpoint 与可选 next loop plan，输出 `reverse-deepagent.paused-session-automatic-loop-followup-checkpoint.v1` / `workspace/paused-session-automatic-loop-followup-checkpoint.json` 的 read-only / review-only handoff descriptor；它只决定是否还需要 checkpoint、是否需要 next loop plan 或是否可进入下一次 automatic-loop iteration review，不写 checkpoint、不 recover live callFrame、不发送 CDP、不订阅或捕获 paused event、不执行下一轮、不 advance queue / loop。`paused-session-automatic-loop-next-iteration-plan` 消费 ready follow-up checkpoint、当前 continuation checkpoint、ready multi-step loop plan 和可选 live callFrame recovery evidence，输出 `reverse-deepagent.paused-session-automatic-loop-next-iteration-plan.v1` / `workspace/paused-session-automatic-loop-next-iteration-plan.json` 的 read-only / review-only / plan-only execution review input；它只审计 fresh live callFrame 是否已恢复、下一轮 loop iteration 是否可审、显式执行审批 gate 是否齐备，不 recover callFrame、不发送 CDP、不订阅或捕获 paused event、不执行下一轮、不 advance queue / loop。`paused-session-automatic-loop-next-iteration-execution` 可在显式审批后执行这一轮 review input，但仍一次最多一轮并要求后续 checkpoint。`paused-session-automatic-loop-next-iteration-followup-checkpoint` 消费该执行结果、continuation checkpoint 与 next loop plan，输出 `reverse-deepagent.paused-session-automatic-loop-next-iteration-followup-checkpoint.v1` / `workspace/paused-session-automatic-loop-next-iteration-followup-checkpoint.json` 的 read-only handoff descriptor；它只判断是否需要 checkpoint、是否需要 next loop plan 或是否可重新进入下一轮 automatic-loop iteration review，不写 checkpoint、不 recover live callFrame、不发送 CDP、不订阅或捕获 paused event、不执行下一轮、不 advance queue / loop。`paused-session-automatic-loop-following-iteration-plan` 再把 ready follow-up checkpoint 归一成后续 execution review input；`paused-session-automatic-loop-multi-iteration-policy` 只把 following-iteration plan 归一成 bounded multi-iteration policy；`paused-session-automatic-loop-multi-iteration-executor-preflight` 只审计未来多轮 executor 的 policy / budget / transaction journal / per-iteration review / checkpoint / fresh live callFrame / stop-after-checkpoint gates，固定 `ready_to_execute_now=false`、`automatic_multi_iteration_executor_implemented=false` 和 `automatic_multi_iteration_execution_allowed_now=false`，不是多轮 executor。这些 descriptor / writer / executor 不会自动 attach target、自动 recover live callFrame、自动 advance loop / queue、管理长期跨进程 session、调用 MCP 或触碰移动端完整链路；multi-iteration policy 也只是 policy-only review，不是多轮 executor；multi-iteration transaction preflight 只审计 journal writer 输入，multi-iteration transaction journal writer 只写 reviewed journal audit artifact，multi-iteration bounded executor gate 只审计 journal 是否可进入未来 executor review，不执行多轮、不发送 CDP、不恢复 callFrame；readiness 继续固定 `automation_executor_implemented=false` / `automatic_multi_step_loop_supported=false`。execution plan / executor preflight / approval-plan / session lifecycle / readiness / live callFrame recovery 路径仍不会 attach target、probe CDP、resume、step 或 evaluate；attach probe 只允许 attach / detach；one-action executor 不自动 attach、不启用 Debugger domain、不捕获 paused event、不循环执行、不调用 MCP，也不触碰移动端完整链路。
- Flow timeline：native-web recon 会生成 `virtual://workspace/flow-timeline.json`，包含 correlation hints、conservative groups、manual stitch candidates、review-gated stitch proposals、auto-stitch dry-run scoring、policy gate、materialization plan、review-approved materialization result、audit / rollback plan、transaction-log-only records 和 delivery guard rerun artifact model。

显式执行面保持 review-gated：

- `custom-loader-execution` 只执行一个 reviewed arbitrary custom-loader candidate，不执行 dynamic import、webpack `require.e`、federation `get/init` 或递归遍历。
- `custom-loader-traversal-workflow-execution` / `custom-loader-traversal-loop-execution` 一次只处理一个 reviewed step / loop iteration，不自动 rebuild graph、replan workflow、advance queue 或递归。
- `async-chunk-traversal-workflow-execution` / `async-chunk-traversal-loop-execution` / `async-chunk-recursive-traversal-followup` / `async-chunk-recursive-traversal-execution` 一次只处理一个 reviewed chunk-load step、loop iteration 或 recursive checkpoint；followup 最多重建 graph / replan workflow / plan next bounded loop，next-loop execution 最多执行一个 reviewed loop iteration，不自动请求下一批 chunk、advance queue 或递归到耗尽。
- `module-federation-traversal-graph` / `module-federation-traversal-workflow-plan` 只生成远端模块遍历队列和审阅工作流；`module-federation-traversal-workflow-execution` 一次只执行一个 reviewed traversal step，可委托既有 factory invoke / export hook plan / export hook install manager，但不 rebuild graph、不 advance queue、不递归执行；`module-federation-recursive-traversal-plan` 只在一次 reviewed workflow execution 后规划 graph rebuild / workflow replan / next-step review checkpoint，不执行 remote code；`module-federation-recursive-traversal-followup` 可在显式 review approval 后委托已有 graph / workflow planner 重建 graph、重排 workflow 并生成下一步 review checkpoint，但仍不执行 remote factory、不安装 hook、不 advance queue、不递归；`module-federation-recursive-traversal-execution` 可在显式 review approval 后委托既有 traversal workflow executor 执行一个 reviewed next step，并立即停在下一次 recursive checkpoint 前，不 rebuild graph、不 replan workflow、不 advance queue、不递归到耗尽；`module-federation-recursive-continuation-journal` / `module-federation-recursive-traversal-continuation-journal` 只把已审阅的一次 recursive execution 记录为 append-only continuation entry，并生成下一轮 graph rebuild / workflow replan / next-step review checkpoint plan，本身不执行 remote code、不 rebuild、不 advance queue；`module-federation-recursive-continuation-checkpoint` 可在显式 review approval 后从 continuation journal 执行一个 checkpoint，复用既有 review-only graph / workflow planner 并生成下一次 recursive execution review，但仍不调用 remote factory、不安装 hook、不自动 advance queue、不递归到耗尽；`module-federation-export-hook-install` 只包装被审阅的 remote function export，不自动 hook 所有 exports。
- `stitched-flow.json` 只在 reviewer approval 后 materialize；所有 auto-stitch dry-run / policy / conflict resolver 输出默认不写最终链路，也不触发 delivery。

仍未闭环、后续 capability-gated 的 Web-first 工作包括：

- cross-process live CDP paused execution continuation，超过当前只读 live-continuation preflight、target attach readiness proof、cross-process execution plan、reviewed attach/detach probe、read-only live callFrame recovery proof、review-gated resume / step / evaluate one-action executor、review-only next paused-event capture plan、review-gated one-shot next paused-event capture execution、review-only continuation checkpoint baseline、review-gated pre-action subscribe-and-action orchestration baseline、review-only multi-step continuation workflow / journal plan baseline、review-gated one-iteration multi-step continuation execution baseline、read-only cross-process session lifecycle descriptor、review-only paused-session multi-step loop plan descriptor、review-gated paused-session multi-step loop one-iteration execution baseline、read-only / review-only `paused-session-automatic-loop-readiness` descriptor、review-only / plan-only `paused-session-automatic-loop-execution-plan` descriptor、read-only / review-only / preflight-only `paused-session-automatic-loop-executor-preflight` descriptor、review-only / approval-plan-only / transaction-plan-only `paused-session-automatic-loop-executor-approval-plan` descriptor、explicit-review-only `paused-session-automatic-loop-executor-approval-record` writer、explicit-review-only automatic-loop one-iteration execution result、read-only / review-only `paused-session-automatic-loop-followup-checkpoint` descriptor、read-only / review-only / plan-only `paused-session-automatic-loop-next-iteration-plan` descriptor、explicit-review-only `paused-session-automatic-loop-next-iteration-execution` MVP、read-only `paused-session-automatic-loop-next-iteration-followup-checkpoint` descriptor 和 read-only / review-only / plan-only `paused-session-automatic-loop-following-iteration-plan` descriptor，以及 read-only closure-wrapper continuation readiness descriptor、review-only closure-wrapper continuation execution plan descriptor、review-gated one-iteration wrapper continuation execution baseline、read-only closure-wrapper continuation follow-up checkpoint descriptor、review-only closure-wrapper continuation next-iteration plan descriptor；自动多步 live action 循环执行器、自动 wrapper continuation execution 和跨进程长期 session 管理仍未实现；automatic-loop readiness + execution-plan + executor-preflight + approval-plan descriptors 仍只证明 bounded executor 是否可进入 review；approval-record / transaction journal 只证明人工审批和事务记录，实际执行面目前支持显式审批的一轮 initial execution、可重复复用 next-iteration execution 的单轮 review input，以及 Step 264 的 bounded multi-iteration executor MVP：它消费 ready bounded gate / written journal / ready loop workflow / fresh live callFrame evidence 后一次最多委托执行一个 reviewed iteration，输出 `workspace/paused-session-automatic-loop-multi-iteration-execution-result.json`，状态可为 `partial` / `completed`，并强制 `checkpoint_required=true`、`automatic_multi_iteration_loop=false`、不自动 advance queue / loop；Step 265 进一步提供 `workspace/paused-session-automatic-loop-multi-iteration-followup-checkpoint.json`，只把 Step 264 结果、continuation checkpoint 和 next loop plan 归一成下一次 multi-iteration step review handoff，不写 checkpoint、不执行下一轮；Step 266 提供 `workspace/paused-session-automatic-loop-multi-iteration-next-step-plan.json`，把 ready follow-up checkpoint、continuation checkpoint、next loop plan 和可选 fresh live callFrame evidence 归一成下一次显式 Step 264 executor review input，仍不执行 iteration、不恢复 callFrame、不发送 CDP、不 advance queue / loop；Step 267 提供 `workspace/paused-session-automatic-loop-multi-iteration-executor-input-preflight.json`，只读校验 ready Step 266 handoff 与 Step 264 executor 所需 journal / gate / loop plan / workflow / fresh live callFrame / retained session 输入，不调用 executor、不写 checkpoint、不执行 iteration；following-iteration plan 只是把 Step 254 follow-up checkpoint 归一成下一次 execution review，multi-iteration policy / executor-preflight / execution-plan / approval / journal / gate / follow-up checkpoint 现在可进入这个 explicit-review-only MVP 的审阅闭环，但仍不是完整自动多轮 executor。
- closure wrapper replacement hardening，超过当前 review-only assignment safety proof、runtime mutability preflight、review-approved runtime mutability probe/result、strategy descriptor/catalog metadata 与 same-process `log-only-call-through` reviewed install / restore execution baseline，以及 read-only wrapper-continuation readiness descriptor、review-only wrapper-continuation execution plan descriptor、review-gated one-iteration wrapper continuation execution baseline、read-only wrapper-continuation follow-up checkpoint descriptor 与 review-only wrapper-continuation next-iteration plan descriptor，包括 arbitrary closure-local wrapper support、非 `log-only-call-through` 策略的 reviewed executor、automatic wrapper continuation loop 和 cross-process live wrapper execution；当前仍不支持任意闭包内部函数 automatic wrapper hook。
- deeper recursive custom-loader traversal execution，超过当前 bounded continuation / workflow / loop / one-step execution / recursive follow-up planning / reviewed follow-up checkpoint / reviewed recursive next-loop execution / unified readiness descriptor baseline。
- deeper recursive async chunk traversal，超过当前 reviewed workflow / bounded loop / recursive follow-up checkpoint / recursive next-loop execution / chunk load / module diff / unified readiness descriptor baseline。
- deeper federation traversal execution，超过当前 review-only traversal graph / workflow plan、review-gated traversal workflow execution、review-only recursive follow-up plan、review-gated recursive follow-up checkpoint、review-gated recursive next-step execution、review-only recursive continuation journal / multi-step checkpoint plan、review-gated recursive continuation checkpoint execution、unified readiness descriptor、reviewed factory invoke、export hook plan 和 reviewed export hook install baseline。
- full source-map consumer semantics，超过当前 local remap、review-only source-map lookup descriptor、review-only source-map source-content availability descriptor、review-only source-map readiness join descriptor、review-only source-map consumer action plan descriptor、review-only source-map consumer materialization descriptor、read-only source-map typed payload preflight descriptor、review-only source-map followthrough review descriptor、review-only source-map followthrough surface selection descriptor、review-only selected source-map executor-input review descriptor、review-only selected source-map executor approval / apply-plan descriptor、read-only source-map follow-through chain readiness descriptor、review-only source-map follow-through one-step plan descriptor、read-only source-map follow-through dispatch preflight descriptor、review-only source-map follow-through dispatch approval / transaction plan descriptor、explicit-review-only source-map follow-through dispatch approval-record writer、explicit-review-only source-map follow-through dispatch transaction journal writer、read-only source-map follow-through dispatch bounded executor gate descriptor、review-only bundler symbol scope descriptor 与 credentialless URL fetch metadata baseline；当前 descriptors 只给出保守 lookup / source-content availability metadata / readiness / reviewed action plan / reviewed materialized payload / typed payload follow-through preflight / followthrough review handoff / surface selection handoff / selected executor-input review package / selected executor approval-plan handoff / chain readiness next-step normalization / one-step explicit-review plan packaging / dispatch preflight allowlist and input readiness / approval and transaction plan readiness / explicit dispatch approval-record writing / 候选和 hook readiness，不宣称完整符号绑定 / scope 解析，也不导出 raw source content。
- full JS heap diff，超过当前 scoped object-root audit baseline、review-only object graph diff descriptor、scoped runtime-collected object graph diff baseline、`heap-snapshot-readiness` 预检 baseline、explicit review-gated `heap-snapshot-collect` digest-only metadata MVP、`heap-snapshot-diff-readiness` pair-review descriptor、`heap-snapshot-diff-executor-preflight` raw-ingestion safety gate、`heap-snapshot-diff-executor-approval-plan` approval / transaction plan、explicit-review-only `heap-snapshot-diff-executor-approval-record` writer、read-only `heap-snapshot-diff-executor-transaction-preflight` descriptor、explicit-review-only `record_heap_snapshot_diff_executor_transaction_journal` writer、read-only `heap-snapshot-diff-executor-bounded-gate` descriptor 与 explicit-review-only `heap-snapshot-diff-executor-result` summary-diff executor MVP、read-only / review-only `heap-snapshot-diff-followup-checkpoint` result follow-up checkpoint、read-only / review-only `heap-snapshot-diff-selected-analysis-input-preflight` selected follow-up analysis input preflight、read-only / review-only `heap-snapshot-constructor-growth-drilldown` constructor-growth review descriptor、`heap-snapshot-retained-path-preflight` retained-size / path-to-root preflight handoff descriptor、`heap-snapshot-retained-size-input-review` retained-size executor input review / approval-gate descriptor、`heap-snapshot-retained-size-approval-plan` retained-size approval / transaction plan descriptor、explicit-review-only `record_heap_snapshot_retained_size_approval` approval-record writer、read-only / review-only `heap-snapshot-retained-size-transaction-preflight` transaction preflight descriptor、explicit-review-only `record_heap_snapshot_retained_size_transaction_journal` transaction journal writer；当前 `object-graph-diff` 只是基于调用方 snapshots 的保守 diff / review hints，`runtime-object-graph-diff` 只采集一个显式 root 的 bounded descriptor-safe snapshots，`heap-snapshot-readiness` 只归一调用方提供的 BrowserProvider / CDP / HeapProfiler capability evidence 和 size / redaction gate，`heap-snapshot-collect` 只在审批后采集 one-shot HeapProfiler metadata digest，`heap-snapshot-diff-readiness` 只审查两个 digest-only metadata 是否可进入未来 diff executor，`heap-snapshot-diff-executor-preflight` 只审查未来 raw-heap-aware executor 所需的 ingestion / parser sandbox / redaction / size-budget gate，`heap-snapshot-diff-executor-approval-plan` 只规划 approval record、transaction journal、bounded gate 和 result artifact contract，`heap-snapshot-diff-executor-approval-record` 只记录显式 reviewer approval metadata，`heap-snapshot-diff-executor-transaction-preflight` 只验证 ready approval plan 与 written approval record 可进入 journal-writer review，`record_heap_snapshot_diff_executor_transaction_journal` 只在显式 review apply gates 下写 `workspace/heap-snapshot-diff-executor-journal.json` 事务审计记录；`heap-snapshot-diff-executor-bounded-gate` 只消费 written transaction journal，输出 `workspace/heap-snapshot-diff-executor-bounded-gate.json` 的 read-only / review-only bounded executor input descriptor，并固定 `ready_to_execute_now=false`、`bounded_executor_gate_written=false`、`executor_invoked=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`heap_diff_computed=false`；`heap-snapshot-diff-executor-result` 在 `mode=apply`、`review_approved=true`、`approve_heap_snapshot_diff_executor_execution=true`、reviewer、ready bounded gate 和调用方提供的两个 V8 heap snapshot JSON 对象齐全时，只做 bounded parser summary 与 node / edge / constructor count delta，输出 `workspace/heap-snapshot-diff-executor-result.json` / `virtual://workspace/heap-snapshot-diff-executor-result.json`，固定 `raw_heap_exported=false`、`complete_heap_traversal_claimed=false`、不导出 raw strings；`heap-snapshot-diff-followup-checkpoint` 只读消费该 result，输出 `workspace/heap-snapshot-diff-followup-checkpoint.json` / `virtual://workspace/heap-snapshot-diff-followup-checkpoint.json` 的 constructor growth、node-type growth、retained-size / path-to-root planning 建议，并固定 `raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`、`automatic_followup_analysis=false`；`heap-snapshot-diff-selected-analysis-input-preflight` 只读消费 follow-up checkpoint，输出 `workspace/heap-snapshot-diff-selected-analysis-input-preflight.json` / `virtual://workspace/heap-snapshot-diff-selected-analysis-input-preflight.json`，只能选择一个后续 analysis action 与候选输入，并固定 `future_executor_contract.implemented=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`heap-snapshot-constructor-growth-drilldown` 只读消费 ready 的 `review_constructor_growth` selected-analysis input preflight，输出 `workspace/heap-snapshot-constructor-growth-drilldown.json` / `virtual://workspace/heap-snapshot-constructor-growth-drilldown.json` 的 constructor growth candidate summary 与 retained-size / path-to-root 后续 review recommendations，并固定 `constructor_drilldown_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`；`heap-snapshot-retained-path-preflight` 只读消费 ready constructor-growth descriptor，输出 `workspace/heap-snapshot-retained-path-preflight.json` / `virtual://workspace/heap-snapshot-retained-path-preflight.json` 的 retained-size / path-to-root executor input handoff、raw heap requirements 和 future executor contracts，并固定 future executors `implemented=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`raw_strings_exported=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`heap-snapshot-retained-size-input-review` 只读消费 ready retained-path preflight，输出 `workspace/heap-snapshot-retained-size-input-review.json` / `virtual://workspace/heap-snapshot-retained-size-input-review.json` 的 retained-size candidate inputs、raw heap requirements、disabled executor input contract 和 approval gate，并固定 `executor_input_contract.implemented=false`、`approval_gate.ready_to_execute_now=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`raw_strings_exported=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`heap-snapshot-retained-size-approval-plan` 只读消费 ready retained-size input review，输出 `workspace/heap-snapshot-retained-size-approval-plan.json` / `virtual://workspace/heap-snapshot-retained-size-approval-plan.json` 的 approval-record plan、transaction-journal plan、bounded-gate artifact plan、result-artifact plan、candidate digest 和 disabled executor-input contract，并固定 `approval_recorded=false`、`transaction_started=false`、`journal_written_now=false`、`bounded_executor_gate_written=false`、`executor_invoked=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`raw_strings_exported=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`record_heap_snapshot_retained_size_approval` 仅在 `mode=apply`、`write_result=true`、`approve_heap_snapshot_retained_size=true`、reviewer 与可选 digest / plan-id guard 通过时写 `workspace/heap-snapshot-retained-size-approval-record.json`，并固定 `ready_to_execute_now=false`、`transaction_started=false`、`journal_written=false`、`bounded_executor_gate_written=false`、`executor_invoked=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`heap-snapshot-retained-size-transaction-preflight` 只读消费 ready approval plan 与 written approved approval record，输出 `workspace/heap-snapshot-retained-size-transaction-preflight.json` / `virtual://workspace/heap-snapshot-retained-size-transaction-preflight.json` 的 journal-writer review gate，并固定 `ready_to_execute_now=false`、`transaction_started=false`、`journal_written=false`、`bounded_executor_gate_written=false`、`executor_invoked=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`retained_size_proven=false`、`path_to_root_computed=false`；`record_heap_snapshot_retained_size_transaction_journal` 只在显式 apply gates 下写 `workspace/heap-snapshot-retained-size-executor-journal.json` 事务审计记录，可标记 `transaction_started=true` / `journal_written=true`，但固定 `ready_to_execute_now=false`、`bounded_executor_gate_written=false`、`executor_invoked=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`raw_heap_exported=false`、`retained_size_proven=false`、`path_to_root_computed=false`；当前 `heap-snapshot-automatic-followup-plan` 已支持 read-only / review-only / plan-only 自动后续规划 baseline：它只消费既有 retained-size estimate、path-to-root estimate 和 constructor-growth drilldown analysis descriptors，输出 `workspace/heap-snapshot-automatic-followup-plan.json` / `virtual://workspace/heap-snapshot-automatic-followup-plan.json` 的人工 next-action 建议，并固定 `raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`path_to_root_proven=false`、`constructor_drilldown_proven=false`、`automatic_execution_allowed=false`；当前 `heap-snapshot-retained-size-proof-plan` 已支持 read-only / review-only / plan-only retained-size proof planning baseline：它只消费 executed retained-size estimate 和可选 ready automatic follow-up plan，输出 `workspace/heap-snapshot-retained-size-proof-plan.json` / `virtual://workspace/heap-snapshot-retained-size-proof-plan.json` 的 proof requirements、candidate inputs 和 disabled future executor contract，并固定 `proof_plan_only=true`、`future_executor_contract.implemented=false`、`future_executor_contract.ready_to_execute_now=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`、`retained_size_proven=false`、`proof_executor_invoked=false`、`automatic_execution_allowed=false`；当前 `heap-snapshot-path-to-root-proof-plan` 已支持 read-only / review-only / plan-only path-to-root proof planning baseline：它只消费 executed path-to-root estimate 和可选 retained-size estimate / automatic follow-up plan / retained-size proof plan，输出 `workspace/heap-snapshot-path-to-root-proof-plan.json` / `virtual://workspace/heap-snapshot-path-to-root-proof-plan.json` 的 root-set / incoming-edge-walk proof requirements、candidate path inputs 和 disabled future executor contract，并固定 `proof_plan_only=true`、`future_executor_contract.implemented=false`、`future_executor_contract.ready_to_execute_now=false`、`raw_heap_loaded=false`、`raw_heap_parsed=false`、`heap_diff_computed=false`、`path_to_root_proven=false`、`proof_executor_invoked=false`、`automatic_execution_allowed=false`；当前 `heap-snapshot-retained-size-analysis` 已支持 explicit-review-only retained-size executor MVP：在 `mode=apply`、`review_approved=true`、`approve_heap_snapshot_retained_size_execution=true`、reviewer、ready bounded gate 和调用方提供的 V8 heap snapshot JSON 齐全时，输出 `workspace/heap-snapshot-retained-size-analysis.json` / `virtual://workspace/heap-snapshot-retained-size-analysis.json` 的 redacted candidate self-size / directly-owned local retained-size estimate，并固定 `raw_heap_exported=false`、`raw_strings_exported=false`、`retained_size_proven=false`、`path_to_root_computed=false`、`complete_heap_traversal_claimed=false`；当前 `heap-snapshot-path-to-root-analysis` 已支持 explicit-review-only path-to-root executor MVP：在 `mode=apply`、`review_approved=true`、`approve_heap_snapshot_path_to_root_execution=true`、reviewer、executed retained-size analysis 或 ready retained-path preflight 和调用方提供的 V8 heap snapshot JSON 齐全时，输出 `workspace/heap-snapshot-path-to-root-analysis.json` / `virtual://workspace/heap-snapshot-path-to-root-analysis.json` 的 redacted bounded incoming-edge path estimate，并固定 `raw_heap_exported=false`、`raw_strings_exported=false`、`path_to_root_proven=false`、`retained_size_proven=false`、`complete_heap_traversal_claimed=false`；当前 `heap-snapshot-constructor-growth-drilldown-analysis` 已支持 explicit-review-only descriptor-backed constructor-growth drilldown analysis MVP：在 `mode=apply`、`review_approved=true`、`approve_heap_snapshot_constructor_growth_drilldown_execution=true`、reviewer 和 ready constructor-growth review descriptor 齐全时，输出 `workspace/heap-snapshot-constructor-growth-drilldown-analysis.json` / `virtual://workspace/heap-snapshot-constructor-growth-drilldown-analysis.json` 的 descriptor-backed candidate prioritization，并固定 `raw_heap_loaded=false`、`raw_heap_exported=false`、`heap_diff_computed=false`、`constructor_drilldown_proven=false`、`retained_size_proven=false`、`path_to_root_computed=false`、`complete_heap_traversal_claimed=false`；仍不支持完整 heap graph traversal、retained-size proof executor、path-to-root proof executor、raw heap 文件读取 / 导出、raw-heap constructor drilldown proof、larger-budget second pass 或自动后续执行。
- `heap-snapshot-raw-heap-constructor-drilldown-proof-plan` 当前已作为 read-only / review-only / plan-only descriptor 接入：它消费已执行的 constructor-growth drilldown analysis，可结合 automatic follow-up、retained-size proof plan 与 path-to-root proof plan，输出 `workspace/heap-snapshot-raw-heap-constructor-drilldown-proof-plan.json` / `virtual://workspace/heap-snapshot-raw-heap-constructor-drilldown-proof-plan.json`，只规划 parser sandbox、redaction、size budget、constructor reachability graph、retainer edge index 和 disabled future executor contract；它不读取 / 解析 / 导出 raw heap，不证明 constructor reachability，不启动浏览器、不发送 CDP、不调用 MCP，也不触碰 Android / iOS / 小程序完整运行链路。
- 更完整的自动全链路跨请求 conflict resolver、physical rollback state machine、advanced adaptive provider retry、第三方 external delivery provider、broader durable scheduler，以及 broader rollout commit / rollback 双终态之后的生产化编排；这些仍必须保持显式 review / apply intent。

明确延期的范围保持不变：Android / iOS / 小程序完整运行链路、Frida / LLDB / APK / IPA / 小程序私有包深度分析、自动 lease-renewal daemon、自动 lock lifecycle manager、自动 stale lock takeover、Redlock quorum、无审批 automatic materialization / rollback / external delivery 都不属于当前 Web-first 执行 track。


当前 Android / iOS / 小程序后端已具备 registry / factory / 能力元数据 / 轻副作用工具探测 / artifact 导出基础层，并可通过平台中立 `reverse-agent-platform` pipeline 落盘 capabilities、probe、export bundle、manifest 与报告；但还不包含真实 hook、静态分析或 replay 验证。完整约定见 [`docs/runtime/adapter-pluginization-contract.md`](docs/runtime/adapter-pluginization-contract.md)。

## Chrome 调试会话约束

legacy MCP 运行时依赖 `http://127.0.0.1:9222` 这类 Chrome DevTools 端口。

约束：

- Agent 不应该假设 9222 Chrome 已经存在
- 真实 Web recon 前必须先完成 Chrome 调试会话检查
- 如果没有可用 Chrome：
  - 显式使用 `--ensure-chrome` 时，通过推荐脚本启动受管 Chrome
  - 未显式启用时，结构化返回 `status=failed`、`next_action=ensure_browser_session`
- 启动参数必须可调，不要把端口、profile、Chrome 路径硬写死在 Agent prompt 里

推荐启动脚本：

```bash
"<repo-root>/scripts/start_chrome_debug.sh"
```

可调环境变量：

- `CHROME_PATH`，默认 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- `DEBUG_PORT`，默认 `9222`
- `DEBUG_ADDRESS`，默认 `127.0.0.1`
- `USER_DATA_DIR`，默认 `~/.codex/browser-profiles/chrome-jsreverser`
- `STATE_DIR`，默认 `~/.codex/run/reverse-deepagent`
- `START_URL`，默认 `about:blank`
- `WAIT_SECONDS`，默认 `10`
- `EXTRA_CHROME_ARGS`，默认空

示例：

```bash
DEBUG_PORT=9333 \
USER_DATA_DIR="/tmp/reverse-agent-chrome" \
START_URL="http://localhost:3000" \
EXTRA_CHROME_ARGS="--disable-web-security" \
"<repo-root>/scripts/start_chrome_debug.sh"
```

停止受管 Chrome：

```bash
DEBUG_PORT=9333 \
USER_DATA_DIR="/tmp/reverse-agent-chrome" \
"<repo-root>/scripts/stop_chrome_debug.sh"
```

## 运行 legacy MCP 冒烟测试

完整前置条件和故障排查见 [`docs/runtime/jsreverser-mcp-setup.md`](docs/runtime/jsreverser-mcp-setup.md)。

推荐先运行浏览器 / legacy MCP doctor，确认本机 Chrome、调试端口、`jsreverser-mcp` 和 console script 入口是否就绪：

```bash
reverse-agent-doctor --ensure-chrome --legacy-mcp
```

如果当前 shell 没有激活虚拟环境，可以使用绝对路径：

```bash
"<repo-root>/.venv/bin/reverse-agent-doctor" --ensure-chrome --legacy-mcp
```

默认情况下，`reverse-agent-doctor --ensure-chrome` 会在检查后停止受管 Chrome；如果你需要保留调试会话，显式添加 `--keep-chrome`。

先探测真实 `jsreverser-mcp` stdio 协议和工具列表：

```bash
cd "<repo-root>"
PYTHONPATH="<repo-root>/src" \
  "<repo-root>/.venv/bin/python" \
  "<repo-root>/scripts/probe_jsreverser_mcp.py"
```

已验证当前本机 `jsreverser-mcp`：

- 协议：stdio JSON-RPC newline framing
- 协商协议版本：`2025-03-26`
- tools/list 可返回 73 个工具

## 运行最小演示（legacy MCP 运行时）

legacy MCP 运行时会启动 `/opt/homebrew/bin/jsreverser-mcp --browserUrl http://127.0.0.1:9222`。

```bash
reverse-agent-demo \
  --runtime legacy-mcp \
  --ensure-chrome \
  --artifact-root "<repo-root>/artifacts-mcp-smoke"
```

常用可调参数：

```bash
--chrome-debug-port 9333 \
--chrome-user-data-dir "/tmp/reverse-agent-chrome" \
--chrome-start-url "http://localhost:3000" \
--chrome-extra-args "--disable-web-security"
```

如果 `127.0.0.1:9222` 没有可用 Chrome，会得到结构化失败结果：

- `status: failed`
- `next_action: ensure_browser_session`

这属于预期行为，不是脚本崩溃。

## 真实 Chrome 冒烟测试（可调端口）

已验证一条真实冒烟测试链路，可以在隔离端口上启动受管 Chrome，再交给 `jsreverser-mcp`：

```bash
reverse-agent-demo \
  --runtime legacy-mcp \
  --ensure-chrome \
  --chrome-debug-port 9445 \
  --chrome-user-data-dir "/tmp/reverse-agent-chrome-9445" \
  --chrome-start-url "about:blank" \
  --task-text "http://localhost 找 sign 入口，并给出下一步建议" \
  --artifact-root "<repo-root>/artifacts-managed-chrome-smoke"
```

实测结果：

- `chrome_launch.ok = true`
- `chrome_stop.ok = true`
- 端口 9445 在结束后不再保留监听
- `final_result.status = partial`
- `final_result.next_action = stabilize_page_and_expand_runtime_observation`
- `final_result.key_findings.facts` 会包含已连接浏览器、当前活动页面和导航动作

注意：

- `jsreverser-mcp` 的真实输出可能是 Markdown 与 fenced JSON 混合文本，适配层已经做了归一化
- 如果你改了 `--chrome-debug-port`，`reverse-agent-demo` 会把这个端口同步传给 MCP 后端，不会再傻乎乎地默认连 9222

## 测试

```bash
cd "<repo-root>"
"<repo-root>/.venv/bin/python" \
  -m unittest discover -s "<repo-root>/tests" -p "test_*.py"
```


### Source Map follow-through dispatcher handoff

`source-map-followthrough-dispatcher-handoff` 是 Step 297 的 read-only / review-only handoff descriptor，输出 `workspace/source-map-followthrough-dispatcher-handoff.json`。它只消费 ready 的 `workspace/source-map-followthrough-dispatch-bounded-executor-gate.json`，验证 bounded gate、transaction / approval ids、selected consumer、dispatch surface、required artifact、future dispatcher contract 和无运行时副作用，并固定 `ready_to_dispatch_now=false`、`ready_to_execute_now=false`、`dispatcher_invoked=false`、`dispatch_target_invoked=false`、`executor_invoked=false`、`apply_preflight_invoked=false`。它不调用 dispatcher、不运行 apply-preflight、不执行 selected executor、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不调用 MCP、不触碰 Android / iOS / 小程序完整运行链路；后续仍需 dispatcher apply-preflight / dispatcher-result handoff verification / selected-executor application handoff / result checkpoint 和 explicit dispatcher result review。


### Source Map follow-through dispatcher apply-preflight

`source-map-followthrough-dispatcher-apply-preflight` 是 Step 298 的 read-only / review-only / preflight-only descriptor，输出 `workspace/source-map-followthrough-dispatcher-apply-preflight.json`。它只消费 ready 的 `workspace/source-map-followthrough-dispatcher-handoff.json`，验证 handoff、transaction / approval ids、selected consumer、dispatch surface、required artifact、dispatcher handoff payload、selected-executor review contract 和无运行时副作用，并固定 `ready_to_dispatch_now=false`、`ready_to_execute_now=false`、`dispatcher_invoked=false`、`dispatch_target_invoked=false`、`executor_invoked=false`、`selected_executor_apply_preflight_invoked=false`、`runtime_apply_preflight_invoked=false`。它不调用 dispatcher、不运行 selected-executor apply-preflight、不执行 selected executor、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不调用 MCP、不触碰 Android / iOS / 小程序完整运行链路；下一步可进入 explicit dispatcher MVP result review。

### Source Map follow-through dispatcher result

`source-map-followthrough-dispatcher-result` 是 Step 299 的 explicit-review-only dispatcher MVP decision record，输出 `workspace/source-map-followthrough-dispatcher-result.json`。它只消费 ready 的 `workspace/source-map-followthrough-dispatcher-apply-preflight.json`，并且只有在 `mode=apply`、`write_result=true`、`review_approved=true`、`approve_dispatcher_mvp=true` 和 reviewer 非空时，才记录 `dispatcher_decision_recorded=true`。这个 result 不调用 dispatch target、不执行 debugger / source-logpoint / hook / rebuild selected executor、不运行 selected-executor apply-preflight、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不调用 MCP、不触碰 Android / iOS / 小程序完整运行链路；写入后下一步仍必须走 `review_source_map_selected_executor_apply_preflight`。

### Source Map selected-executor result checkpoint

`source-map-selected-executor-result-checkpoint` 是 Step 302 的 read-only / review-only / checkpoint-only descriptor，输出 `workspace/source-map-selected-executor-result-checkpoint.json`。它只消费已经由显式 review 路径产生的 selected executor application result（debugger / source-logpoint / hook / rebuild metadata），可选消费 `source-map-selected-executor-application-handoff` 做 action / consumer / gate / result artifact / digest 对账，并把 observed application side effects 和 checkpoint 自身 side-effect policy 分开记录。它不调用 application route、不继续 debugger、不额外安装 hook / source-logpoint、不执行 rebuild generation、不启动浏览器、不发送 CDP、不 evaluate JavaScript、不调用 MCP、不触碰 Android / iOS / 小程序完整运行链路；后续仍必须人工 review checkpoint，再决定是否进入 rebuild generation、timeline review 或终态审计。

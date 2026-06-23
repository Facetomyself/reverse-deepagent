# Browser Provider Operations

## Doctor Commands

### Browser Provider Doctor

```bash
# metadata-only matrix（不启动浏览器、不调用 MCP）
reverse-agent-doctor --browser-provider-matrix

# 单 provider metadata doctor
reverse-agent-doctor --browser cloakbrowser

# 打印显式 launch-smoke 命令（不启动浏览器）
reverse-agent-doctor --browser cloakbrowser --browser-url "http://127.0.0.1:9222" --print-browser-launch-command

# 真实 launch smoke
reverse-agent-doctor --browser cloakbrowser --launch-browser-smoke --browser-smoke-url "about:blank"
```

`browser_provider_smoke_matrix` 由 `BrowserProviderRegistry` 驱动，列出内置 provider 的 capability flags、alias、supported modes、compatibility、production readiness 和 lifecycle stages。metadata-only 读取 registration metadata 和 `describe()` 输出，不调用 provider factory。

### External Delivery Provider Doctor

```bash
reverse-agent-doctor --external-delivery-providers
```

输出 `external_delivery_provider_matrix`，显示 provider transport、review-only 标记、side-effect policy。

### Runtime Backend Doctor

```bash
reverse-agent-doctor --runtime-backends
```

输出 `runtime_backend_matrix`，列出 backend id / alias / target platforms / capability flags / entry point group / side-effect policy。

### Delivery Transaction Doctor

```bash
reverse-agent-doctor --delivery-transaction-root "artifacts/<run>/delivery"
```

只读读取 transaction artifact，不执行恢复或提交。

## Browser Provider Smoke CLI

### Smoke Evidence Artifact

```bash
reverse-agent-browser-provider-smoke --browser cloakbrowser --artifact-root "<repo>/artifacts/browser-provider-smoke"
```

默认 registry metadata-only，输出 `workspace/browser-provider-smoke.json`。真实启动需显式 `--launch-browser-smoke`：

```bash
reverse-agent-browser-provider-smoke --browser cloakbrowser --launch-browser-smoke --browser-smoke-url about:blank --artifact-root "<repo>/artifacts/browser-provider-smoke-cloak"
```

### Smoke Evidence Review

```bash
# standalone review
reverse-agent-browser-provider-smoke --review-smoke-json "<path>/browser-provider-smoke.json" --expected-provider cloakbrowser

# 带 evidence policy gate
reverse-agent-browser-provider-smoke --review-smoke-json "<path>/browser-provider-smoke.json" --expected-provider cloakbrowser --minimum-evidence-level launch-smoke
```

`--minimum-evidence-level` 支持 `metadata-only` / `availability-check` / `launch-smoke`。输出 `policy_decision=pass|warn|block`。

### Smoke Evidence Attach

```bash
reverse-agent-demo --runtime native-web --browser cloakbrowser --browser-provider-smoke-json "<path>/browser-provider-smoke.json" --artifact-root "<repo>/artifacts/native-web-with-provider-smoke"
```

写入前追加 `attachment_acceptance` 审计，检查 schema、ok、side-effect policy、provider 匹配和 launch-smoke 状态。

### Smoke Policy Gate (CI)

```bash
reverse-agent-browser-provider-smoke-policy --smoke-json "<path>/browser-provider-smoke.json" --expected-provider cloakbrowser
```

exit code `0` = pass, `2` = blocked。详见 [docs/ci/browser-provider-smoke-policy.md](../ci/browser-provider-smoke-policy.md)。

## Browser Provider Registry

通过 `reverse_deepagent.browser_providers` entry point 发现。

内置 provider：`playwright-chromium`、`cloakbrowser`、`remote-cdp`

External provider packages：
- `packages/reverse-deepagent-browser-provider-template/`：通用模板
- `packages/reverse-deepagent-browser-provider-hosted-cdp-template/`：托管浏览器模板
- `packages/reverse-deepagent-browser-provider-hosted-cdp-reference/`：hosted CDP reference
- `packages/reverse-deepagent-browser-provider-browserless-cdp/`：Browserless
- `packages/reverse-deepagent-browser-provider-browserbase-cdp/`：Browserbase
- `packages/reverse-deepagent-browser-provider-fixture/`：fixture provider

## Runtime Backend Registry

`build_default_runtime_registry(include_legacy_mcp=False)` 可构建不带 MCP 的 clean registry。

Core backends：

| Backend | Alias | Target |
|---------|-------|--------|
| `mock` | in-process | 公开 CI / deterministic demo |
| `native-web` | web, browser-native | BrowserProvider-backed |
| `legacy-mcp` | mcp, jsreverser-mcp | optional plugin（需安装 `reverse-deepagent-legacy-mcp`）|
| `playwright-cli` | playwright, pw-cli | 轻量 Playwright CLI 探测 |
| `chrome-cdp` | cdp, devtools | 既有 Chrome DevTools 端点 |
| `browser-cli` | cli-browser | 通用浏览器 CLI 适配 |
| `android-adb` | adb | Android ADB 工具链 |
| `ios-simulator` | simctl, ios-sim | iOS Simulator |
| `mini-program-devtools` | mp-devtools, wechat-devtools | 小程序 devtools |

未安装 `reverse-deepagent-legacy-mcp` 时 `--runtime mcp` 输出结构化安装建议。

# CloakBrowser Provider

## 1. 定位

`cloakbrowser` 是 `native-web` 运行时下的可选 `BrowserProvider`，用于需要更强浏览器指纹控制、持久登录态和 humanized 行为的 Web 逆向任务。

它不是新的运行时中心，也不替代 `NativeWebRuntime`、collector、hook manager 或 artifact exporter。正确边界是：

```text
NativeWebRuntime
  -> CloakBrowserProvider
    -> Playwright-compatible session/page
  -> shared native collectors
  -> shared hooks / debug managers
  -> shared artifact exporters
```

这样做的目的很简单：换浏览器不换证据模型，不因为引入 CloakBrowser 就把采集、分析、导出逻辑再绑死一遍。

## 2. 安装

默认安装不包含 CloakBrowser，避免把可选二进制、平台约束和下载成本强塞给所有用户。

```bash
cd "<repo-root>"
uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cloak]"
```

当前 optional extra：

```toml
cloak = [
  "cloakbrowser>=0.3.30,<0.4",
]
```

`cloakbrowser` 依赖和浏览器二进制由本机环境管理，本仓库不得提交、缓存或再分发 CloakBrowser 相关二进制。

## 3. CLI 用法

最小形态：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --task-text "https://example.com 找 sign 入口"
```

持久 profile：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-profile-dir "./profiles/example" \
  --task-text "https://example.com 查看登录态和关键请求"
```

常用 CloakBrowser 选项：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --no-browser-headless \
  --browser-humanize \
  --browser-locale "zh-CN" \
  --browser-timezone "Asia/Shanghai" \
  --task-text "https://example.com 找 token 生成链路"
```

代理配置也走 BrowserProvider 配置，但注意不要把带认证信息的代理写进共享日志或公开 artifact：

```bash
reverse-agent-demo \
  --runtime native-web \
  --browser cloakbrowser \
  --browser-proxy "http://127.0.0.1:7890" \
  --browser-geoip \
  --task-text "https://example.com 检查 cf 验证状态"
```

provider capability metadata 会将 proxy 脱敏为 `<configured>`。`reverse-agent-browser-provider-smoke` 还会在 `workspace/browser-provider-smoke.json` 写入 redaction-safe `requested_provider_config`：`browser_url` 会移除用户名 / 密码，profile / executable 只保留 basename，proxy 固定为 `<configured>`，高风险 browser args 会被 `<redacted>` 替换。

## 4. 当前实现状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Provider capability metadata | 已实现 | `CloakBrowserProvider.describe()` 不启动浏览器。 |
| 缺依赖错误 | 已实现 | 返回 `BrowserProviderUnavailableError` 和安装建议。 |
| launch 模式 | 已验证 | 通过 `cloakbrowser.launch(...)` 创建 Playwright-compatible session。 |
| persistent context | 已验证 | 配置 `--browser-profile-dir` 时走 `launch_persistent_context(...)`。 |
| connect 模式 | 已实现 baseline | 传入 `--browser-url` / `browser_url` 后通过 Playwright `connect_over_cdp` 连接已有 CloakBrowser / cloakserve CDP endpoint；不负责启动远端进程。 |
| native collectors 复用 | 已接入运行时工厂 | collector 仍由 `NativeWebRuntime` 统一驱动。 |
| doctor 支持 | 已实现 metadata / dependency 检查 | `reverse-agent-doctor --browser cloakbrowser` 默认不启动浏览器。 |
| smoke evidence 配置摘要 | 已实现 | metadata-only / availability / launch-smoke 都会写入脱敏 `requested_provider_config` 和 `review_command_hint`，便于复核 connect / profile / proxy / locale / timezone。 |
| 真实二进制 smoke | 已在本机验证 | 使用 `--launch-browser-smoke` 才会启动 provider。 |

## 4.1 Doctor 检查

默认 BrowserProvider doctor 只做 provider 构建、capability metadata 和 dependency probe，不启动浏览器，也不要求本机安装 `jsreverser-mcp`：

```bash
reverse-agent-doctor --browser cloakbrowser
```

需要传入 CloakBrowser 配置时，可以复用 provider 参数；输出中的 proxy 会脱敏：

```bash
reverse-agent-doctor \
  --browser cloakbrowser \
  --browser-proxy "http://127.0.0.1:7890" \
  --browser-locale "zh-CN" \
  --browser-timezone "Asia/Shanghai"
```

metadata-only smoke evidence 可以先生成配置审计，不启动真实浏览器：

```bash
reverse-agent-browser-provider-smoke \
  --browser cloakbrowser \
  --browser-url "http://127.0.0.1:9222" \
  --browser-profile-dir "./profiles/example" \
  --browser-locale "zh-CN" \
  --browser-timezone "Asia/Shanghai"
```

只有显式加入 `--launch-browser-smoke` 时才会启动真实浏览器：

```bash
reverse-agent-doctor \
  --browser cloakbrowser \
  --launch-browser-smoke \
  --browser-smoke-url "about:blank"
```

## 5. 设计约束

- `cloakbrowser` 必须保持 optional dependency。
- 不允许把 CloakBrowser 相关二进制提交进仓库。
- 不允许让 coordinator 直接依赖 `cloakbrowser` API。
- 不允许在 metadata、report 或公开 artifact 中输出 proxy 密码、cookie、token、Authorization header。
- 真实运行失败时要返回结构化 evidence，不要把 import traceback 当成最终输出。
- 如果 CloakBrowser wrapper API 发生变化，优先在 provider 层兼容，不能把差异扩散到 collector 和 coordinator。

## 6. 后续计划

1. 已在本机验证真实 `cloakbrowser.launch(...)` 与 `launch_persistent_context(...)` 的参数兼容性。
2. 已将 `--launch-browser-smoke` 接入本地 fixture 页面，不再只使用 `about:blank`。
3. 已在真实 CloakBrowser 环境下确认 dependency probe、profile 和 humanize 参数行为。
4. 已接入 connect baseline：`CloakBrowserProvider.connect()` 会在配置 `browser_url` 时通过 Playwright CDP 连接已有 CloakBrowser / cloakserve endpoint，并继续复用 `NativeWebRuntime` collectors。
5. 持续保持 CDP-enhanced collectors 接入 capability gate：支持则采 request initiator、script source、WebSocket frame，不支持则降级为 baseline evidence。
6. 将 CloakBrowser smoke 纳入本地手动测试，不放入默认公开 CI。

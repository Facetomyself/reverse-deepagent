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

provider capability metadata 会将 proxy 脱敏为 `<configured>`。

## 4. 当前实现状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Provider capability metadata | 已实现 | `CloakBrowserProvider.describe()` 不启动浏览器。 |
| 缺依赖错误 | 已实现 | 返回 `BrowserProviderUnavailableError` 和安装建议。 |
| launch 模式 | skeleton 已实现 | 通过 `cloakbrowser.launch(...)` 创建 Playwright-compatible session。 |
| persistent context | skeleton 已实现 | 配置 `--browser-profile-dir` 时走 `launch_persistent_context(...)`。 |
| connect 模式 | 暂不支持 | 后续可拆 `remote-cdp` / `cloakserve` provider。 |
| native collectors 复用 | 已接入运行时工厂 | collector 仍由 `NativeWebRuntime` 统一驱动。 |
| doctor 支持 | 待实现 | 后续加 `reverse-agent-doctor --browser cloakbrowser`。 |
| 真实二进制 smoke | 待验证 | 需要本机安装 CloakBrowser wrapper 和可用浏览器环境。 |

## 5. 设计约束

- `cloakbrowser` 必须保持 optional dependency。
- 不允许把 CloakBrowser 相关二进制提交进仓库。
- 不允许让 coordinator 直接依赖 `cloakbrowser` API。
- 不允许在 metadata、report 或公开 artifact 中输出 proxy 密码、cookie、token、Authorization header。
- 真实运行失败时要返回结构化 evidence，不要把 import traceback 当成最终输出。
- 如果 CloakBrowser wrapper API 发生变化，优先在 provider 层兼容，不能把差异扩散到 collector 和 coordinator。

## 6. 后续计划

1. 增加 `reverse-agent-doctor --browser cloakbrowser`：只检查依赖、版本、配置脱敏和 provider metadata，不默认启动浏览器。
2. 增加可选 `--launch-browser-smoke`：用户明确打开后才启动浏览器，并访问本地 fixture 页面。
3. 验证真实 `cloakbrowser.launch(...)` 与 `launch_persistent_context(...)` 的参数兼容性。
4. 将 CDP-enhanced collectors 接入 capability gate：支持则采 request initiator、script source、WebSocket frame，不支持则降级为 baseline evidence。
5. 将 CloakBrowser smoke 纳入本地手动测试，不放入默认公开 CI。

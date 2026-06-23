# Sign Fixture Profiles & Testing

## Overview

项目内置可重复的 `localhost` Web 逆向样例，验证 sign 入口、请求样本和源码命中链路。

相关 CLI：
- `reverse-agent-fixture`：fixture 服务
- `reverse-agent-fixture-smoke`：fixture 冒烟测试

## Fixture Profiles

| Profile | Sign Algorithm | Context Dep |
|---------|---------------|-------------|
| `default` | `charCodeAt` 求和取模 | 无 |
| `md5` | JS `md5(keyword:timestamp)` | 无 |
| `sha1` | `crypto.subtle.digest('SHA-1')` | 无 |
| `sha256` | `crypto.subtle.digest('SHA-256')` | 无 |
| `base64` | `btoa(keyword:timestamp)` | 无 |
| `context-localstorage` | SHA-256 + `localStorage.device_id` | localStorage |
| `context-cookie` | SHA-256 + `document.cookie.device_id` | cookie |
| `context-navigator` | SHA-256 + `navigator.userAgent` | navigator |
| `webpack-minified` | SHA-256 + webpack 包装 | 无 |
| `token-chain` | SHA-256 + `sessionStorage.fixture_token` | sessionStorage |
| `hybrid-context` | SHA-256 + localStorage + cookie | 多上下文 |

## Running

```bash
# 快速自检
reverse-agent-fixture --check

# 启动本地服务
reverse-agent-fixture --host 127.0.0.1 --port 8765 --profile sha256

# Mock 运行时冒烟
reverse-agent-fixture-smoke --profile default --runtime mock

# Legacy MCP 冒烟
reverse-agent-fixture-smoke --profile default --runtime legacy-mcp --ensure-chrome
```

## Context-Aware Delivery

当 `runtime_context_required` 非空且已采集时，`rebuild-plan.json` 标记 `context_aware_extractable=true`，生成脚本把采集值写成默认常量。

支持的单源绑定：`localStorage.getItem` / `localStorage[]` / `localStorage.` / `sessionStorage` / `document.cookie` / `navigator.*` / timezoneOffset。缺失上下文时不生成假成功脚本。

## Pure Extraction Strategy Fields

`rebuild-plan.json` 包含：

```json
{
  "algorithm_strategy": { "id": "...", "supported": true, "confidence": "medium" },
  "pure_extraction": {
    "pure_extractable": true,
    "runtime_context_required": [],
    "dependencies": ["python-stdlib:hashlib"]
  },
  "review_hints": [
    { "severity": "info", "category": "strategy", "code": "pure_strategy_detected" }
  ]
}
```

运行时上下文（cookie / localStorage / sessionStorage / navigator / timezone / canvas）阻断纯算提取。

## Rebuild Delivery

Mock 或 MCP 流水线后生成：
- `workspace/rebuild-plan.json`
- `rebuild/sign_rebuild.py`：纯 Python sign
- `rebuild/replay_demo.py`：HTTP replay
- `rebuild/scrapy_middleware.py`：Scrapy middleware
- `rebuild/scrapy_project/`：完整 Scrapy 项目
- `rebuild/scrapy_export_manifest.json`：文件索引

```bash
# 自检 sign 脚本
python artifacts/<run>/rebuild/sign_rebuild.py

# HTTP replay（需保持 fixture 服务运行）
python artifacts/<run>/rebuild/replay_demo.py --base-url "http://127.0.0.1:8765" --keyword "sign"

# Scrapy replay
cd artifacts/<run>/rebuild/scrapy_project
python runner.py --base-url "http://127.0.0.1:8765" --output result.json
```

## Algorithm Strategy Registry

管理于 `reverse_deepagent.strategies`，默认顺序：
1. `protected_flow_triage`：WASM / VM / anti-debug 阻断
2. `deterministic_fixture`：fixture seed mod
3. `crypto_hash`：MD5 / SHA-1/256/512 / HMAC
4. `sig_template`：sig_keyword_timestamp
5. `encoding`：Base64 / URL encoding

WASM / JS VM / 混淆边界见 [docs/strategy/wasm-vm-obfuscation-triage.md](../strategy/wasm-vm-obfuscation-triage.md)。

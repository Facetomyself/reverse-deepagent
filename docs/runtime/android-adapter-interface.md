# Android runtime adapter interface draft

This document sketches the Android runtime adapter boundary for future `reverse-deepagent` work. It is a planning contract, not a production Android backend implementation.

The goal is to keep Android support compatible with the existing runtime adapter / artifact manifest architecture without forcing Android workflows through Web-only concepts such as Chrome pages, DOM scripts, or browser storage APIs.

## Non-goals for this draft

- Do not require an Android device in public CI.
- Do not start `adb`, Frida, emulators, or app instrumentation from metadata listing.
- Do not store target APKs, app secrets, cookies, tokens, device identifiers, or proprietary code in public fixtures.
- Do not pretend a native / JNI / packed / obfuscated flow is pure-Python rebuild ready without evidence.

## Backend identity

Recommended backend ids and aliases:

| Backend id | Alias examples | Transport examples | Purpose |
| --- | --- | --- | --- |
| `android-adb` | `adb`, `android-device` | `adb` | Device/app discovery, logs, files, shell, traffic setup. |
| `android-frida` | `frida-adb`, `android-hook` | `frida-adb` | Hook Java / JNI / native functions and capture runtime evidence. |
| `android-static` | `apk-static` | `filesystem` | Offline APK / dex / native library metadata extraction. |

The first implementation can be metadata-only. Real runtime construction should happen only through `build_runtime(...)`, not through registry listing.

## Capability metadata

An Android backend should implement `describe_capabilities()` and return `RuntimeBackendCapabilities` with Android-specific metadata in `config`.

Example:

```json
{
  "backend_id": "android-frida",
  "display_name": "Android Frida runtime",
  "transport": "frida-adb",
  "target_platforms": ["android"],
  "supports_browser_session": false,
  "supports_web_recon": false,
  "supports_protection_patch": true,
  "supports_artifact_export": true,
  "supports_runtime_context": true,
  "supports_replay_validation": true,
  "managed_chrome": false,
  "mcp_backed": false,
  "evidence_kinds": ["static", "dynamic", "hook", "storage", "network", "note"],
  "artifact_kinds": ["json", "markdown", "source", "trace", "binary-metadata"],
  "config": {
    "device_selector": "serial|usb|tcp",
    "package_name": "optional at metadata time",
    "requires_device": true,
    "requires_root": false
  }
}
```

Important: `supports_browser_session=false` is not a weakness. It prevents coordinator code from assuming page indexes, DOM state, or Chrome debug URLs.

## Configuration object

Future implementation should collect Android settings in a serializable config object, for example:

```python
@dataclass(frozen=True, slots=True)
class AndroidRuntimeConfig:
    backend_id: str = "android-frida"
    transport: str = "frida-adb"
    adb_command: str = "adb"
    frida_command: str = "frida"
    device_serial: str | None = None
    package_name: str | None = None
    spawn_app: bool = False
    request_timeout: float = 30.0
    startup_timeout: float = 30.0
    artifact_sample_limit: int = 50
```

The config summary stored in capability metadata must redact secrets and device-specific sensitive values when exported to public artifacts.

## Runtime context model

Android runtime context is not browser storage. Suggested normalized keys:

| Key | Meaning | Sensitivity |
| --- | --- | --- |
| `package` | App package metadata, version, debuggable flag | low |
| `device` | Device model / SDK / ABI summary | medium; redact serials |
| `process` | PID, process name, loaded libraries | low / medium |
| `storage` | SharedPreferences / app files metadata | high if values are included |
| `network` | Observed request metadata / endpoints | medium |
| `hooks` | Hooked method names, arguments, return shapes | can be high |
| `native` | JNI symbols, loaded `.so` metadata, exports | medium |
| `crypto` | Crypto API usage, algorithm names, key source hints | high if keys are included |

Default public artifacts should prefer metadata and hashes over raw sensitive values.

## Evidence normalization

Android adapters should normalize raw ADB / Frida output into existing evidence objects instead of leaking tool-specific logs upward.

Recommended evidence sources:

- `android_package_summary`
- `android_runtime_context`
- `android_method_hook_timeline`
- `android_native_symbol_summary`
- `android_network_observation`
- `android_replay_validation_result`
- `android_static_apk_summary`

Recommended evidence details should include stable identifiers:

```json
{
  "package_name": "com.example.app",
  "process_name": "com.example.app",
  "method": "com.example.SignUtil.sign(java.lang.String)",
  "library": "libsign.so",
  "symbol": "Java_com_example_SignUtil_sign",
  "sample_input_shape": {"keyword": "str", "timestamp": "int"},
  "sample_output_shape": {"sign": "hex|string"}
}
```

Do not put raw keys, auth headers, tokens, cookies, user identifiers, or full proprietary method bodies into public issue comments or public fixtures.

## Artifact manifest expectations

Android outputs should still appear in `workspace/backend-artifact-manifest.json` with `target_platforms=["android"]`.

Example artifact categories:

| Category | Examples |
| --- | --- |
| `runtime-context` | redacted device / package / process context JSON |
| `hook-timeline` | Frida hook call timeline, argument shape summaries |
| `static-analysis` | APK metadata, dex class inventory, native library hash list |
| `network` | request metadata, endpoint map, replay candidate info |
| `rebuild` | pure / context-aware / runtime-assisted delivery plan |
| `triage` | unsupported native packer / VM / dynamic secret analysis |

Binary artifacts such as APKs and `.so` files should usually be referenced by hash and local path only, not committed.

## Rebuild delivery semantics

Android sign flows can fall into the same delivery buckets as Web flows:

1. **Pure rebuild**: algorithm is fully understood and portable to Python.
2. **Context-aware rebuild**: algorithm is portable, but stable app/device context must be modeled as inputs.
3. **Runtime-assisted replay**: safest route is to call the original Java / JNI / native implementation under controlled instrumentation.
4. **Triage-only**: packer, VM, anti-debug, native secret, server challenge, or missing evidence blocks trustworthy delivery.

For native / JNI / packed flows, default to runtime-assisted or triage-only until proven otherwise. 别看见一次 hook 返回 sign 就兴奋，那个只能证明“能观测”，不能证明“能移植”。

## Coordinator integration rules

Coordinator code should not call ADB / Frida directly. It should interact through stable runtime methods and schemas:

- `describe_capabilities()` for routing and UI display.
- future Android-specific collection methods behind an adapter boundary.
- `EvidenceItem` for normalized observations.
- `RuntimeArtifactManifest` for backend-aware artifacts.
- `review_hints` for generated delivery risk.

Android adapters should implement platform-neutral `ReverseRuntime` and expose app/process operations through Android-specific capability layers. Do not implement `WebReverseRuntime` or overload `ensure_browser_session()` to mean “ensure Android app process”.

## Minimal implementation checklist

A future Android adapter PR should include:

1. `AndroidRuntimeConfig` or equivalent serializable config.
2. Capability metadata tests that do not require a device.
3. Registry registration with aliases.
4. Redacted artifact manifest examples.
5. Docs for required local tools and environment variables.
6. Tests proving registry listing does not start external processes.
7. A runtime-unavailable path with clear error messages.

Real device smoke tests should be self-hosted/manual, similar to the current real MCP smoke posture.

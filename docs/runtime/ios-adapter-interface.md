# iOS runtime adapter interface draft

This document sketches the iOS runtime adapter boundary for future `reverse-deepagent` work. It is a planning contract, not a production iOS backend implementation.

The design goal is the same as the Android draft: keep platform runtime support behind stable capability / evidence / artifact schemas instead of forcing iOS workflows through Web-only browser session assumptions.

## Non-goals for this draft

- Do not require an iPhone, simulator, code signing identity, jailbroken device, or Frida server in public CI.
- Do not launch apps, attach debuggers, or start Frida during backend metadata listing.
- Do not store IPA files, app secrets, keychain values, tokens, user identifiers, or proprietary app code in public fixtures.
- Do not claim pure-Python rebuild readiness for Objective-C / Swift / native / packed flows without source-complete evidence.

## Backend identity

Recommended backend ids and aliases:

| Backend id | Alias examples | Transport examples | Purpose |
| --- | --- | --- | --- |
| `ios-frida` | `frida-ios`, `ios-hook` | `frida-usb`, `frida-remote` | Hook Objective-C / Swift / C / native functions and capture runtime evidence. |
| `ios-simulator` | `simctl`, `ios-sim` | `xcrun-simctl` | Simulator app inspection, logs, and controlled local experiments. |
| `ios-static` | `ipa-static`, `macho-static` | `filesystem` | Offline IPA / Mach-O / symbol / class metadata extraction. |

Real backend construction should happen only when explicitly requested. Registry / capability listing must stay side-effect free.

## Capability metadata

Example capability payload:

```json
{
  "backend_id": "ios-frida",
  "display_name": "iOS Frida runtime",
  "transport": "frida-usb",
  "target_platforms": ["ios"],
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
    "device_selector": "usb|remote|simulator",
    "bundle_id": "optional at metadata time",
    "requires_codesign": false,
    "requires_jailbreak_or_debuggable_app": "depends-on-transport"
  }
}
```

`supports_browser_session=false` means the coordinator must not expect DOM, page indexes, cookies, localStorage, or Chrome DevTools state.

## Configuration object

Future implementation should collect settings in a serializable config object, for example:

```python
@dataclass(frozen=True, slots=True)
class IosRuntimeConfig:
    backend_id: str = "ios-frida"
    transport: str = "frida-usb"
    frida_command: str = "frida"
    simctl_command: str = "xcrun simctl"
    device_id: str | None = None
    bundle_id: str | None = None
    spawn_app: bool = False
    attach_timeout: float = 30.0
    request_timeout: float = 30.0
    artifact_sample_limit: int = 50
```

Config summaries exported to artifacts must redact device identifiers and any signing / provisioning details.

## Runtime context model

Suggested normalized context keys:

| Key | Meaning | Sensitivity |
| --- | --- | --- |
| `bundle` | Bundle id, version, executable name, entitlements summary | low / medium |
| `device` | OS version, architecture, simulator/device summary | medium; redact identifiers |
| `process` | PID, loaded images, process name | low / medium |
| `keychain` | Keychain access metadata / key source hints | high |
| `preferences` | `NSUserDefaults` metadata or redacted values | high if values included |
| `network` | Observed request metadata / endpoint map | medium |
| `hooks` | Objective-C / Swift / C hook call summaries | can be high |
| `native` | Mach-O image metadata, exported symbols, class inventory | medium |
| `crypto` | CommonCrypto / CryptoKit / Security.framework usage hints | high if keys included |

Public artifacts should prefer redacted metadata, shape summaries, and hashes over raw values.

## Evidence normalization

Recommended evidence sources:

- `ios_bundle_summary`
- `ios_runtime_context`
- `ios_method_hook_timeline`
- `ios_native_symbol_summary`
- `ios_network_observation`
- `ios_replay_validation_result`
- `ios_static_ipa_summary`

Example normalized evidence detail:

```json
{
  "bundle_id": "com.example.app",
  "process_name": "ExampleApp",
  "method": "-[SignManager signWithKeyword:timestamp:]",
  "module": "ExampleApp",
  "symbol": "_SignWithKeyword",
  "sample_input_shape": {"keyword": "NSString", "timestamp": "NSInteger"},
  "sample_output_shape": {"sign": "NSString"}
}
```

Swift symbols should include both the raw mangled symbol and a best-effort demangled name when available. Objective-C methods should preserve class / selector names.

## Artifact manifest expectations

iOS artifacts should be indexed in `workspace/backend-artifact-manifest.json` with `target_platforms=["ios"]`.

Example categories:

| Category | Examples |
| --- | --- |
| `runtime-context` | redacted bundle / device / process context |
| `hook-timeline` | Frida hook timeline, Objective-C / Swift method call summaries |
| `static-analysis` | IPA metadata, class list, Mach-O image hashes, symbol inventory |
| `network` | request metadata, endpoint map, replay candidate info |
| `rebuild` | pure / context-aware / runtime-assisted delivery plan |
| `triage` | packer / anti-debug / keychain-bound / native secret blockers |

IPA files, dSYMs, Mach-O binaries, and decrypted app dumps should generally be referenced by local path and hash only, not committed.

## Rebuild delivery semantics

iOS signing flows should use the same delivery buckets:

1. **Pure rebuild**: algorithm semantics are complete and portable.
2. **Context-aware rebuild**: portable algorithm plus stable modeled app/device context.
3. **Runtime-assisted replay**: invoke original Objective-C / Swift / C / native implementation under controlled instrumentation.
4. **Triage-only**: keychain-bound secret, Secure Enclave, anti-debug, native packer, server challenge, or missing evidence blocks trustworthy delivery.

Keychain / Secure Enclave / server-bound flows should default to runtime-assisted or triage-only. Observing a return value through a hook is useful evidence, not proof that the signing algorithm is portable.

## Coordinator integration rules

- Coordinator code must not call Frida, `simctl`, LLDB, or device tooling directly.
- Capability metadata must be discoverable without attaching to a device or app.
- iOS runtime evidence must be normalized into `EvidenceItem` objects.
- Artifacts must flow through `RuntimeArtifactManifest` with `target_platforms=["ios"]`.
- Generated delivery risks must be represented as `review_hints`.
- iOS adapters should implement platform-neutral `ReverseRuntime` and expose simulator/device/app operations through iOS-specific capability layers. Do not implement `WebReverseRuntime` or overload `ensure_browser_session()` to mean “attach to iOS app”.

## Minimal implementation checklist

A future iOS adapter PR should include:

1. `IosRuntimeConfig` or equivalent serializable config.
2. Side-effect-free capability metadata tests.
3. Registry registration with aliases.
4. Runtime-unavailable error path for missing device / missing Frida / missing simulator.
5. Redacted artifact manifest examples.
6. Documentation for required local tooling and operational assumptions.
7. Manual/self-hosted smoke workflow for real device or simulator tests.

# WASM / VM / obfuscation triage contract

This document defines how `reverse-deepagent` should handle Web sign flows that involve WASM, custom VM interpreters, heavy obfuscation, anti-debug logic, or other patterns that are not safe to auto-port into pure Python.

The core rule is blunt: **do not pretend a WASM / VM / heavily obfuscated flow is pure-Python extractable just because a sample replay happened to pass once**.

## Scope

This contract applies when source, runtime evidence, or generated artifacts indicate one or more of these patterns:

- WebAssembly modules or glue code (`WebAssembly.instantiate`, `.wasm`, `wasm-bindgen`, Emscripten wrappers).
- Custom bytecode VM dispatchers, opcode tables, interpreter loops, or encrypted function bodies.
- Heavy control-flow flattening, string-array rotation, self-defending code, or runtime code generation.
- Anti-debug / anti-tamper checks such as debugger traps, timing probes, DevTools detection, environment checks, or function integrity checks.
- Runtime-only secrets that are derived from browser/device fingerprinting, session state, native bridges, or server-bound challenges.

These flows may still be analyzed and delivered, but the delivery must be explicit about being triage / runtime-assisted / partial until the algorithm is proven portable.

## Strategy output contract

A triage-only strategy should emit a structured strategy object with these properties:

```json
{
  "id": "triage_wasm_vm_obfuscation",
  "supported": false,
  "confidence": "medium",
  "confidence_score": {
    "score": 0.2,
    "label": "medium",
    "positive_markers": ["WebAssembly.instantiate", "opcode dispatch loop"],
    "caveats": ["triage-only", "runtime-assisted execution required"]
  },
  "description": "WASM / VM / heavy obfuscation indicators were detected; pure-Python rebuild is not safe yet.",
  "dependencies": [],
  "template": "unknown",
  "salt": "",
  "confidence_reason": "Detected runtime-compiled code and VM dispatch markers."
}
```

Required semantics:

1. `supported` must stay `false` until a deterministic, source-complete, browser-independent algorithm has been identified.
2. `id` should be stable and searchable. Recommended ids:
   - `triage_wasm_module`
   - `triage_vm_obfuscation`
   - `triage_anti_debug_runtime`
   - `triage_dynamic_secret`
   - `triage_wasm_vm_obfuscation` for mixed evidence
3. `confidence_score.caveats` must explain why pure extraction is blocked.
4. The rebuild plan must set `pure_extraction.manual_port_required=true` unless a verified context-aware strategy exists.
5. Generated delivery should produce `rebuild/README.md` or a runtime-assisted plan, not a fake `sign_rebuild.py` that hard-codes one observed sample.

## Rebuild plan expectations

For triage-only cases, `workspace/rebuild-plan.json` should make the boundary obvious:

```json
{
  "ready": false,
  "algorithm_strategy": {
    "id": "triage_vm_obfuscation",
    "supported": false
  },
  "pure_extraction": {
    "pure_extractable": false,
    "context_aware_extractable": false,
    "manual_port_required": true,
    "runtime_context_required": ["runtime-js-vm"]
  },
  "review_hints": [
    {
      "severity": "risk",
      "category": "manual_port",
      "code": "manual_port_required",
      "message": "No complete automatic rebuild is available; expand source/runtime evidence or keep a JS runtime backend for this flow.",
      "evidence": ["strategy=triage_vm_obfuscation", "supported=false"]
    }
  ]
}
```

A runtime-assisted delivery may still be useful, but it must be labeled separately from pure extraction. For example:

- `runtime_replay_plan`: how to invoke the original JS / WASM / VM under a controlled runtime.
- `hook_points`: candidate functions, imports, exports, WebAssembly exports, VM dispatcher entrypoints, or bridge calls.
- `context_requirements`: cookies, storage, navigator fields, canvas output, timezone, device id, native bridge state, challenge ids.
- `known_blockers`: anti-debug checks, missing bytecode, server-bound nonce, dynamic native secret, missing WASM binary.

## Evidence expectations

Triage decisions should be backed by artifacts, not vibes. A good artifact bundle should include as many of these as available:

| Evidence | Purpose |
| --- | --- |
| Source snippets around WASM / VM / anti-debug markers | Shows why pure extraction is unsafe. |
| Network request initiator stack | Links target request to the protected code path. |
| Runtime hook timeline | Shows dynamic imports, crypto calls, WebAssembly exports, VM dispatch, eval, or timer probes. |
| WASM metadata | Module URL, hash, exports/imports, instantiation site. |
| Runtime context snapshot / diff | Separates stable constants from volatile replay inputs. |
| Validation sample | Demonstrates observed behavior without overclaiming portability. |
| Generated review hints | Lets CI / subagents block fake pure-Python delivery. |

Do not store secrets, cookies, tokens, or proprietary target code in public fixtures. Keep target-specific sensitive data in local artifacts only.

## Subagent routing

When these markers appear, the coordinator should route work as triage instead of forcing the pure rebuild subagent to fabricate code.

Recommended subagent responsibilities:

1. **Web recon subagent**: collect source, initiator, network, storage, and hook timeline evidence.
2. **Protection subagent**: apply minimal anti-debug / anti-tamper neutralization and record what was changed.
3. **Strategy subagent**: classify the flow as portable, context-aware, runtime-assisted, or triage-only.
4. **Rebuild delivery subagent**: emit either pure code, context-aware code, runtime-assisted instructions, or a not-ready README.
5. **Review subagent**: consume `review_hints`, inspect caveats, and block misleading generated output.

The important bit: the subagent boundary is about truthfulness of the delivery, not about giving up. Triage-only is a valid result when the evidence says so.

## Implemented baseline and future hook points

The current public demo implements a conservative `protected_flow_triage` strategy detector for WASM / VM / anti-debug / heavy-obfuscation / dynamic-secret markers. It runs before supported hash / template detectors, so protected flows stay triage-only even when the same snippet also contains `sha256`, `base64`, or other portable-looking markers.

This is a marker-level baseline, not a full WASM binary inspector, VM bytecode semantics engine, or anti-debug neutralizer. The detector is intentionally conservative about false positives: ordinary `cookie`, `localStorage`, `navigator`, `nonce`, `csrf`, or business variables such as `ip` should not become protected-flow triage by name alone. They should remain runtime-context / manual-port inputs unless stronger evidence appears, such as WASM / VM structure, anti-debug checks, native bridge calls, volatile context, or a strong runtime challenge marker.

Future work should deepen runtime/backend features behind the existing strategy / runtime contracts:

- More strategy detector rules for obfuscator families, packed chunks, bytecode formats, and common self-defending patterns.
- Runtime backend capabilities for WebAssembly export inspection and import hook capture.
- Artifact manifest entries for WASM binaries, hashes, export lists, and hook timelines.
- Runtime-assisted replay renderer that invokes the original protected code in a controlled browser / JS engine.
- Mobile expansion hooks for Android / iOS native bridges where the same sign flow moves behind JNI, Frida-visible native methods, or mini-program JSCore bridges.

## Acceptance checklist

Before marking a protected flow as pure rebuild ready, all of these must be true:

- The algorithm source or equivalent semantics are complete enough to implement outside the browser/runtime.
- Dynamic secrets are either literal, reproducible from captured stable context, or explicitly modeled as inputs.
- The generated implementation passes a deterministic sample self-check.
- Replay validation passes against the intended request path.
- `review_hints` contains no `risk` item blocking pure delivery.
- The artifact bundle explains what was captured, what was inferred, and what remains runtime-bound.

If any item fails, keep the result as partial / triage / runtime-assisted. 别硬装纯算，后面维护的人会骂娘，这锅不该让生成脚本背。

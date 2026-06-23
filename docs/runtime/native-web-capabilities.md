# Native Web Runtime Capabilities

## Overview

`native-web` runtime 通过 `BrowserProviderRegistry` 管理浏览器 provider。metadata / discovery / planning 默认只读，runtime 执行必须显式 protection、参数和 review gate。

## Paused Session Lifecycle

### Live Continuation Preflight
`paused-session-live-continuation-preflight` 输出 `workspace/debugger-paused.json` 只读 live continuation preflight，审计 same-process registry、durable snapshot 的 blockers、`live_session_diagnostics`、`target_diagnostics`。

### Target Attach Readiness
`paused-session-target-attach-readiness` 生成只读 target attach readiness proof，包含 target URL correlation、CDP attachability 和 action matrix。

### Cross-Process Execution
- `paused-session-cross-process-execution-plan`：reviewed executor plan
- `paused-session-cross-process-session-lifecycle`：read-only lifecycle descriptor
- `paused-session-cross-process-attach-probe`：受控 `Target.attachToTarget`/`detachFromTarget`
- `paused-session-live-callframe-recovery`：fresh `callFrameId` 恢复证据
- `paused-session-cross-process-one-action`：一次 reviewed Debugger 命令
- `paused-session-next-paused-event-capture-plan/execution`：catch next `Debugger.paused`
- `paused-session-cross-process-continuation-checkpoint`：下一次 action 的 review-only checkpoint

### Automatic Loop
支持 explicit-review-only bounded one-iteration MVP：
- `readiness` → `execution-plan` → `executor-preflight` → `approval-plan` → `approval-record` → `transaction-preflight` → `transaction-journal` → `bounded-gate` → `execution-result` → `followup-checkpoint`
- 每个 payload 固定 `ready_to_execute_now=false`、`automatic_loop_executed=false`
- Multi-iteration 扩展：policy → preflight → execution-plan → approval → journal → bounded-gate → MVP executor（每次最多一轮）→ followup-checkpoint

## Source Map Follow-Through

### Lookup & Readiness
- `source-map-lookup`：只读 generated/original location 对应
- `source-map-source-content`：`sourcesContent` availability metadata
- `source-map-readiness`：debugger / rebuild / source-logpoint readiness
- `source-map-consumer-action-plan`：reviewed action plan
- `source-map-consumer-materialization`：typed review payloads

### Follow-Through Dispatch
- `source-map-followthrough-review` → `surface-selection` → `selected-executor-input-review` → `approval-plan` → `apply-preflight` → one-shot executor
- Bundle offset remap、sourceRoot、indexed section、names URL equivalence
- Credentialless source-map fetch metadata

### Selected Executor Applications
- **source-logpoint**：reviewed install，输出 `workspace/source-map-source-logpoint-install-result.json`
- **debugger**：reviewed Debugger breakpoint 命令，输出 `workspace/source-map-debugger-execution-result.json`
- **hook**：reviewed function/module hook install（`source-map-hook-candidates` → selection → application）
- **rebuild**：digest-only metadata application + reviewed bundle generation

### Selected Executor Result Chain
`selected-executor-result-checkpoint` → `followthrough-completion-checkpoint` → `terminal-review-package` → `closure-checkpoint` → `final-audit` → `action-decision record`

## Heap Snapshot

- `heap-snapshot-readiness`：BrowserProvider / CDP / HeapProfiler capability 预检
- `heap-snapshot-collect`：review-gated one-shot HeapProfiler metadata digest
- `heap-snapshot-diff-executor-result`：bounded parser summary（node / edge / constructor count delta）
- `followup-checkpoint` → `selected-analysis-input-preflight` → `constructor-growth-drilldown` → `retained-size-analysis` → `path-to-root-analysis`
- `heap-snapshot-retained-size-proof-plan` / `heap-snapshot-path-to-root-proof-plan`：review-only proof planning
- 所有路径固定 `raw_heap_exported=false`、`raw_strings_exported=false`

## Hook & Closure Wrapper

- Global function hook、webpack module export hook、remote federation export hook
- Closure wrapper：assignment-safety proof → runtime-mutability preflight → runtime-mutability probe → `log-only-call-through` reviewed install/restore
- Hook candidate discovery（`source-map-hook-candidates`）→ selection → input-review → application
- Closure continuation：readiness → execution-plan → one-iteration execution → checkpoint → next-iteration

## Module Discovery

- webpack `require.c` / `require.m` 只读 introspection
- custom runtime / federation exposed-module candidate
- 只读 async chunk graph / loader metadata
- Custom-loader traversal：review-only plan → one-step workflow → bounded loop → recursive follow-up
- Federation traversal：graph → workflow → one-step execution → recursive follow-up → continuation journal/checkpoint
- Unified `recursive-continuation-readiness` descriptor

## Flow Timeline

native-web recon 生成 `virtual://workspace/flow-timeline.json`，包含：
- correlation hints、conservative groups、manual stitch candidates
- review-gated stitch proposals
- auto-stitch dry-run scoring、policy gate、materialization plan
- review-approved materialization result、rollback plan、delivery guard rerun

## Mutation Audit

- page-level mutation audit
- descriptor-safe object-root mutation audit
- `object-graph-diff`：调用方提供的 before/after snapshots diff
- `runtime-object-graph-diff`：bounded descriptor-safe runtime collection
- MutationObserver timeline

## Deferred Scope

以下保持不在当前执行 track 范围内：
- Automatic multi-step live action loop executor
- Automatic wrapper continuation loop
- Full heap graph traversal / retained-size proof / path-to-root proof executor
- Raw heap file export
- Android / iOS / 小程序完整运行链路
- Frida / LLDB / APK / IPA 深度分析
- Automatic lease-renewal daemon、stale lock takeover、Redlock quorum
- 无审批 automatic materialization / rollback / external delivery

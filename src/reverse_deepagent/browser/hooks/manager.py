from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reverse_deepagent.browser.base import BrowserPage

HOOK_NAMESPACE = "__reverseDeepAgentHooks"
HOOK_SCRIPT = r"""
(() => {
  const root = window.__reverseDeepAgentHooks = window.__reverseDeepAgentHooks || {
    installedAt: Date.now(),
    events: [],
    installed: {},
    push(type, payload) {
      try {
        this.events.push({ type, ts: Date.now(), payload });
        if (this.events.length > 300) this.events.shift();
      } catch (_) {}
    }
  };

  const sanitizeUrl = (value) => {
    try {
      const url = new URL(String(value || ''), window.location.href);
      return url.origin + url.pathname;
    } catch (_) {
      return String(value || '').split(/[?#]/)[0];
    }
  };
  const payloadPreview = (value) => {
    try {
      if (typeof value === 'string') return { size: value.length, preview: value.slice(0, 240) };
      if (value instanceof ArrayBuffer) return { size: value.byteLength, preview: '<arraybuffer>' };
      if (ArrayBuffer.isView(value)) return { size: value.byteLength, preview: '<typed-array>' };
      if (typeof Blob !== 'undefined' && value instanceof Blob) return { size: value.size, preview: '<blob>' };
      const text = String(value == null ? '' : value);
      return { size: text.length, preview: text.slice(0, 240) };
    } catch (_) {
      return { size: 0, preview: '<unavailable>' };
    }
  };

  if (!root.installed.fetch_xhr) {
    root.installed.fetch_xhr = true;
    const originalFetch = window.fetch;
    if (typeof originalFetch === 'function') {
      window.fetch = function reverseAgentFetch(input, init) {
        const url = sanitizeUrl(typeof input === 'string' ? input : (input && input.url) || String(input));
        const method = (init && init.method) || (input && input.method) || 'GET';
        root.push('fetch', { url, method });
        return originalFetch.apply(this, arguments);
      };
    }
    const OriginalXHR = window.XMLHttpRequest;
    if (typeof OriginalXHR === 'function') {
      const originalOpen = OriginalXHR.prototype.open;
      const originalSend = OriginalXHR.prototype.send;
      OriginalXHR.prototype.open = function reverseAgentXhrOpen(method, url) {
        this.__reverseAgentXhr = { method: method || 'GET', url: sanitizeUrl(url || '') };
        return originalOpen.apply(this, arguments);
      };
      OriginalXHR.prototype.send = function reverseAgentXhrSend(body) {
        const meta = this.__reverseAgentXhr || {};
        root.push('xhr', { url: meta.url || '', method: meta.method || 'GET', bodyType: body == null ? 'none' : typeof body });
        return originalSend.apply(this, arguments);
      };
    }
  }

  if (!root.installed.cookie) {
    root.installed.cookie = true;
    try {
      const descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie') || Object.getOwnPropertyDescriptor(HTMLDocument.prototype, 'cookie');
      if (descriptor && descriptor.configurable && descriptor.get && descriptor.set) {
        Object.defineProperty(document, 'cookie', {
          configurable: true,
          get() { return descriptor.get.call(document); },
          set(value) {
            const raw = String(value || '');
            const cookieName = raw.split('=')[0] || '';
            root.push('cookie_write', { cookieName, valueSize: raw.length });
            return descriptor.set.call(document, value);
          }
        });
      }
    } catch (error) {
      root.push('hook_error', { hook: 'cookie', message: String(error && error.message || error) });
    }
  }

  if (!root.installed.websocket) {
    root.installed.websocket = true;
    try {
      const OriginalWebSocket = window.WebSocket;
      if (typeof OriginalWebSocket === 'function') {
        const WrappedWebSocket = function reverseAgentWebSocket(url, protocols) {
          const socket = protocols === undefined ? new OriginalWebSocket(url) : new OriginalWebSocket(url, protocols);
          const safeUrl = sanitizeUrl(url || '');
          root.push('websocket_open', { url: safeUrl });
          const originalSend = socket.send;
          socket.send = function reverseAgentWebSocketSend(data) {
            const preview = payloadPreview(data);
            root.push('websocket_frame', { direction: 'sent', url: safeUrl, payloadSize: preview.size, payloadPreview: preview.preview });
            return originalSend.apply(this, arguments);
          };
          if (typeof socket.addEventListener === 'function') {
            socket.addEventListener('message', function reverseAgentWebSocketMessage(event) {
              const preview = payloadPreview(event && event.data);
              root.push('websocket_frame', { direction: 'received', url: safeUrl, payloadSize: preview.size, payloadPreview: preview.preview });
            });
            socket.addEventListener('error', function reverseAgentWebSocketError() {
              root.push('websocket_error', { url: safeUrl });
            });
          }
          return socket;
        };
        WrappedWebSocket.prototype = OriginalWebSocket.prototype;
        for (const key of ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED']) {
          try { WrappedWebSocket[key] = OriginalWebSocket[key]; } catch (_) {}
        }
        window.WebSocket = WrappedWebSocket;
      }
    } catch (error) {
      root.push('hook_error', { hook: 'websocket', message: String(error && error.message || error) });
    }
  }

  if (!root.installed.anti_debug) {
    root.installed.anti_debug = true;
    try {
      if (window.console && typeof window.console.clear === 'function') {
        const originalClear = window.console.clear.bind(window.console);
        window.console.clear = function reverseAgentConsoleClear() {
          root.push('console_clear_blocked', {});
          return undefined;
        };
        window.console.clear.__reverseAgentOriginal = originalClear;
      }
      window.__REVERSE_AGENT_ANTI_DEBUG__ = true;
    } catch (error) {
      root.push('hook_error', { hook: 'anti_debug', message: String(error && error.message || error) });
    }
  }

  return { ok: true, namespace: '__reverseDeepAgentHooks', installed: Object.assign({}, root.installed), eventCount: root.events.length };
})()
"""
SNAPSHOT_EXPRESSION = r"""
(() => {
  const root = window.__reverseDeepAgentHooks;
  if (!root) return { ok: false, installed: {}, events: [], eventCount: 0, reason: 'not_installed' };
  return { ok: true, installedAt: root.installedAt, installed: Object.assign({}, root.installed || {}), events: (root.events || []).slice(), eventCount: (root.events || []).length };
})()
"""


@dataclass(slots=True)
class HookInstallResult:
    ok: bool
    installed: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "installed": self.installed, "error": self.error}


@dataclass(slots=True)
class HookSnapshot:
    ok: bool
    installed: dict[str, Any]
    events: list[dict[str, Any]]
    event_count: int
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "installed": self.installed, "events": self.events, "eventCount": self.event_count, "reason": self.reason}


class BrowserHookManager:
    """Install and collect project-owned runtime hook instrumentation."""

    def __init__(self, *, script: str = HOOK_SCRIPT, snapshot_expression: str = SNAPSHOT_EXPRESSION) -> None:
        self.script = script
        self.snapshot_expression = snapshot_expression
        self.last_install: HookInstallResult | None = None
        self.last_snapshot: HookSnapshot | None = None

    def install(self, page: BrowserPage) -> HookInstallResult:
        try:
            payload = page.evaluate(self.script)
        except Exception as exc:
            result = HookInstallResult(ok=False, installed={}, error=str(exc))
            self.last_install = result
            return result
        installed = payload.get("installed", {}) if isinstance(payload, dict) else {}
        result = HookInstallResult(ok=bool(isinstance(payload, dict) and payload.get("ok")), installed=installed)
        self.last_install = result
        return result

    def snapshot(self, page: BrowserPage) -> HookSnapshot:
        try:
            payload = page.evaluate(self.snapshot_expression)
        except Exception as exc:
            result = HookSnapshot(ok=False, installed={}, events=[], event_count=0, reason=str(exc))
            self.last_snapshot = result
            return result
        if not isinstance(payload, dict):
            result = HookSnapshot(ok=False, installed={}, events=[], event_count=0, reason="snapshot_returned_non_object")
            self.last_snapshot = result
            return result
        events = [item for item in payload.get("events", []) if isinstance(item, dict)]
        result = HookSnapshot(
            ok=bool(payload.get("ok")),
            installed=payload.get("installed", {}) if isinstance(payload.get("installed"), dict) else {},
            events=events,
            event_count=int(payload.get("eventCount", len(events)) or 0),
            reason=payload.get("reason"),
        )
        self.last_snapshot = result
        return result

    def protection_result_payload(self) -> dict[str, Any]:
        install = self.last_install.to_dict() if self.last_install else {"ok": False, "installed": {}, "error": "not_installed"}
        snapshot = self.last_snapshot.to_dict() if self.last_snapshot else {"ok": False, "installed": {}, "events": [], "eventCount": 0, "reason": "not_collected"}
        return {"install": install, "snapshot": snapshot, "scriptSize": len(self.script)}

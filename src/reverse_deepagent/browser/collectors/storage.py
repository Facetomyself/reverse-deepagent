from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.redaction import redact_cookie_header, redact_mapping

STORAGE_DUMP_EXPRESSION = """
(() => {
  const dump = (storage) => {
    const out = {};
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      out[key] = storage.getItem(key);
    }
    return out;
  };
  return {
    cookie: document.cookie || "",
    localStorage: dump(window.localStorage),
    sessionStorage: dump(window.sessionStorage),
    navigator: {
      userAgent: navigator.userAgent,
      language: navigator.language,
      platform: navigator.platform,
      webdriver: navigator.webdriver,
    },
    timezoneOffset: new Date().getTimezoneOffset(),
  };
})()
"""


def _redact_storage_result(result: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(result)
    redacted["cookie"] = redact_cookie_header(str(redacted.get("cookie") or ""))
    redacted["localStorage"] = redact_mapping(redacted.get("localStorage") or {})
    redacted["sessionStorage"] = redact_mapping(redacted.get("sessionStorage") or {})
    return redacted


class StorageCollector:
    """Collect browser storage/runtime context through page evaluation."""

    def collect(self, page: BrowserPage) -> dict[str, Any]:
        try:
            result = page.evaluate(STORAGE_DUMP_EXPRESSION)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "cookie": "", "localStorage": {}, "sessionStorage": {}}
        if not isinstance(result, dict):
            return {"ok": False, "error": "storage expression returned non-object", "raw": result}
        return {"ok": True, **_redact_storage_result(result)}

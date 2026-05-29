from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserPage

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


class StorageCollector:
    """Collect browser storage/runtime context through page evaluation."""

    def collect(self, page: BrowserPage) -> dict[str, Any]:
        try:
            result = page.evaluate(STORAGE_DUMP_EXPRESSION)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "cookie": "", "localStorage": {}, "sessionStorage": {}}
        if not isinstance(result, dict):
            return {"ok": False, "error": "storage expression returned non-object", "raw": result}
        return {"ok": True, **result}

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from reverse_deepagent.browser.base import BrowserPage

SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]+src=)[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


class ScriptCollector:
    """Collect script inventory and lightweight source hits from page HTML."""

    def collect(self, page: BrowserPage) -> dict[str, Any]:
        html = page.content()
        scripts: list[dict[str, Any]] = []
        for index, src in enumerate(SCRIPT_SRC_RE.findall(html)):
            scripts.append({"scriptId": f"external-{index}", "url": urljoin(page.url, src), "kind": "external", "source": ""})
        for index, source in enumerate(INLINE_SCRIPT_RE.findall(html)):
            scripts.append({"scriptId": f"inline-{index}", "url": page.url, "kind": "inline", "source": source})
        return {"count": len(scripts), "scripts": scripts}

    def search(self, inventory: dict[str, Any], query: str, limit: int = 20) -> dict[str, Any]:
        query_lower = query.lower()
        hits: list[dict[str, Any]] = []
        if not query_lower:
            return {"count": 0, "results": []}
        for item in inventory.get("scripts", []):
            source = str(item.get("source") or "")
            haystacks = [source, str(item.get("url") or "")]
            if not any(query_lower in haystack.lower() for haystack in haystacks):
                continue
            preview = ""
            for line in source.splitlines():
                if query_lower in line.lower():
                    preview = line.strip()[:240]
                    break
            hits.append({"scriptId": item.get("scriptId"), "url": item.get("url"), "kind": item.get("kind"), "preview": preview})
            if len(hits) >= limit:
                break
        return {"count": len(hits), "results": hits}

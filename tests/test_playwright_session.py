import unittest

from reverse_deepagent.browser import BrowserPage, BrowserSession, PlaywrightBrowserPageAdapter, PlaywrightBrowserSessionAdapter


class FakeCDPSession:
    def __init__(self) -> None:
        self.handlers = {}

    def send(self, method, params=None):
        return {"method": method, "params": params or {}}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)


class FakeContext:
    def __init__(self) -> None:
        self.pages = []
        self.closed = False
        self.cdp_requests = []

    def new_page(self):
        page = FakePage(self, "about:blank", "Blank")
        self.pages.append(page)
        return page

    def new_cdp_session(self, page):
        self.cdp_requests.append(page)
        return FakeCDPSession()

    def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def close(self):
        self.closed = True


class FakeManager:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakePage:
    def __init__(self, context, url: str, title: str) -> None:
        self.context = context
        self.url = url
        self._title = title
        self.goto_calls = []
        self.screenshot_calls = []

    def goto(self, url, **kwargs):
        self.url = url
        self.goto_calls.append((url, kwargs))

    def title(self):
        return self._title

    def content(self):
        return f"<title>{self._title}</title>"

    def evaluate(self, expression):
        return {"evaluated": expression}

    def screenshot(self, **kwargs):
        self.screenshot_calls.append(kwargs)
        return b"png" if "path" not in kwargs else None


class PlaywrightSessionTests(unittest.TestCase):
    def test_page_adapter_exposes_basic_operations_and_cdp(self) -> None:
        context = FakeContext()
        raw = FakePage(context, "https://example.test", "Example")
        page = PlaywrightBrowserPageAdapter(raw)

        self.assertIsInstance(page, BrowserPage)
        self.assertEqual(page.url, "https://example.test")
        page.goto("https://next.test", timeout=1.5)
        self.assertEqual(raw.goto_calls[0], ("https://next.test", {"timeout": 1500.0}))
        self.assertEqual(page.title(), "Example")
        self.assertIn("Example", page.content())
        self.assertEqual(page.evaluate("1 + 1"), {"evaluated": "1 + 1"})
        self.assertEqual(page.screenshot(), b"png")
        self.assertIsNone(page.screenshot(path="/tmp/example.png"))
        cdp = page.cdp_session()
        self.assertEqual(cdp.send("Runtime.enable"), {"method": "Runtime.enable", "params": {}})
        cdp.on("Network.requestWillBeSent", lambda payload: payload)
        self.assertIn("Network.requestWillBeSent", cdp._session.handlers)

    def test_session_adapter_lists_pages_creates_pages_and_closes_resources(self) -> None:
        context = FakeContext()
        browser = FakeBrowser()
        manager = FakeManager()
        context.pages.append(FakePage(context, "https://example.test", "Example"))
        session = PlaywrightBrowserSessionAdapter(
            provider_id="playwright-chromium",
            context=context,
            browser=browser,
            playwright_manager=manager,
        )

        self.assertIsInstance(session, BrowserSession)
        self.assertEqual(session.provider_id, "playwright-chromium")
        self.assertEqual(session.list_pages()[0].url, "https://example.test")
        self.assertEqual(session.get_active_page().title(), "Example")
        created = session.new_page("https://created.test")
        self.assertEqual(created.url, "https://created.test")

        session.close()
        self.assertTrue(context.closed)
        self.assertTrue(browser.closed)
        self.assertTrue(manager.stopped)


if __name__ == "__main__":
    unittest.main()

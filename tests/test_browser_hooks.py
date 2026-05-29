import unittest

from reverse_deepagent.browser.hooks import BrowserHookManager


class HookPage:
    def __init__(self) -> None:
        self.installed = False
        self.events = []
        self.installed_flags = {}

    def evaluate(self, expression):
        if "__reverseDeepAgentHooks" in expression and "namespace:" in expression:
            self.installed = True
            self.installed_flags = {"fetch_xhr": True, "cookie": True, "anti_debug": True}
            self.events.append({"type": "fetch", "payload": {"url": "https://example.test/api", "method": "GET"}})
            return {"ok": True, "installed": self.installed_flags, "eventCount": len(self.events)}
        if "not_installed" in expression:
            return {"ok": self.installed, "installed": self.installed_flags, "events": self.events, "eventCount": len(self.events)}
        raise AssertionError("unexpected expression")


class FailingHookPage:
    def evaluate(self, expression):
        raise RuntimeError("eval blocked")


class BrowserHookManagerTests(unittest.TestCase):
    def test_install_and_snapshot_hook_timeline(self) -> None:
        page = HookPage()
        manager = BrowserHookManager()
        install = manager.install(page)
        snapshot = manager.snapshot(page)
        self.assertTrue(install.ok)
        self.assertTrue(install.installed["fetch_xhr"])
        self.assertTrue(snapshot.ok)
        self.assertEqual(snapshot.event_count, 1)
        self.assertEqual(snapshot.events[0]["type"], "fetch")
        payload = manager.protection_result_payload()
        self.assertEqual(payload["snapshot"]["eventCount"], 1)
        self.assertNotIn("valuePreview", manager.script)
        self.assertIn("sanitizeUrl", manager.script)

    def test_install_failure_is_structured(self) -> None:
        manager = BrowserHookManager()
        install = manager.install(FailingHookPage())
        snapshot = manager.snapshot(FailingHookPage())
        self.assertFalse(install.ok)
        self.assertIn("eval blocked", install.error)
        self.assertFalse(snapshot.ok)
        self.assertEqual(snapshot.event_count, 0)


if __name__ == "__main__":
    unittest.main()

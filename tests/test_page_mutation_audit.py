import unittest

from reverse_deepagent.browser.hooks import PageMutationAuditManager, PageMutationAuditSpec


class PageMutationAuditPage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.html_length = 10
        self.text_length = 4
        self.body_child_count = 1
        self.local_storage_keys = ["device_id"]
        self.session_storage_keys = []
        self.cookie_names = ["sid"]
        self.globals = {"window.__token": {"type": "string", "preview": "before"}}

    def evaluate(self, expression):
        if "__REVERSE_AGENT_PAGE_MUTATION_AUDIT__" in expression:
            return {
                "marker": "__REVERSE_AGENT_PAGE_MUTATION_AUDIT__",
                "ok": True,
                "url": self.url,
                "title": "Fixture",
                "dom": {
                    "html_length": self.html_length,
                    "text_length": self.text_length,
                    "body_child_count": self.body_child_count,
                    "html_preview": "<main></main>",
                    "text_preview": "demo",
                },
                "storage": {
                    "localStorage": {"available": True, "count": len(self.local_storage_keys), "keys": list(self.local_storage_keys)},
                    "sessionStorage": {"available": True, "count": len(self.session_storage_keys), "keys": list(self.session_storage_keys)},
                },
                "cookies": {"count": len(self.cookie_names), "names": list(self.cookie_names)},
                "globals": dict(self.globals),
            }
        if "mutatePage()" in expression:
            self.html_length = 32
            self.text_length = 9
            self.body_child_count = 2
            self.local_storage_keys.append("nonce")
            self.session_storage_keys.append("token")
            self.cookie_names.append("csrf")
            self.globals["window.__token"] = {"type": "string", "preview": "after"}
            return "mutated"
        raise AssertionError(f"unexpected expression: {expression}")


class PageMutationAuditManagerTests(unittest.TestCase):
    def test_from_context_accepts_trigger_and_global_names(self) -> None:
        spec = PageMutationAuditSpec.from_context(
            {
                "trigger_expression": "mutatePage()",
                "global_names": "window.__token, window.__sign",
                "max_preview_length": 32,
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.trigger_expression, "mutatePage()")
        self.assertEqual(spec.global_names, ["window.__token", "window.__sign"])
        self.assertEqual(spec.max_preview_length, 32)

    def test_audit_diffs_dom_storage_cookie_and_globals(self) -> None:
        page = PageMutationAuditPage()
        spec = PageMutationAuditSpec.from_context(
            {
                "trigger_expression": "mutatePage()",
                "global_names": ["window.__token"],
            }
        )

        result = PageMutationAuditManager().audit(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.trigger["ok"])
        self.assertTrue(result.diff["changed"])
        self.assertEqual(result.diff["change_count"], 7)
        self.assertEqual(result.diff["categories"], ["cookie", "dom", "global", "storage"])
        changed_paths = {item["path"] for item in result.diff["changes"]}
        self.assertIn("dom.html_length", changed_paths)
        self.assertIn("dom.text_length", changed_paths)
        self.assertIn("dom.body_child_count", changed_paths)
        self.assertIn("storage.localStorage.keys", changed_paths)
        self.assertIn("storage.sessionStorage.keys", changed_paths)
        self.assertIn("cookies.names", changed_paths)
        self.assertIn("globals.window.__token", changed_paths)

    def test_audit_without_trigger_is_partial_and_records_no_change(self) -> None:
        page = PageMutationAuditPage()
        spec = PageMutationAuditSpec.from_context({"global_names": ["window.__token"]})

        result = PageMutationAuditManager().audit(page, spec)

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.trigger["attempted"])
        self.assertFalse(result.diff["changed"])
        self.assertEqual(result.diff["change_count"], 0)

    def test_snapshot_expression_resolves_globals_without_dynamic_function_eval(self) -> None:
        spec = PageMutationAuditSpec.from_context({"global_names": ["window.__token", "window.__x = 1"]})

        self.assertIsNotNone(spec)
        assert spec is not None
        expression = PageMutationAuditManager._snapshot_expression(spec)
        self.assertIn("resolveGlobal", expression)
        self.assertNotIn('Function("return (" + name + ")")', expression)
        self.assertIn("unsupported_global_path", expression)


if __name__ == "__main__":
    unittest.main()

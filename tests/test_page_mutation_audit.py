import unittest

from reverse_deepagent.browser.hooks import MutationObserverTimelineManager, MutationObserverTimelineSpec, PageMutationAuditManager, PageMutationAuditSpec


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
        if "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__" in expression:
            if "noMutation()" in expression:
                return {
                    "marker": "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__",
                    "ok": True,
                    "status": "partial",
                    "records": [],
                    "trigger": {"attempted": True, "ok": True, "result": {"value": "stable"}},
                    "observer": {"target": "document.body", "options": {"childList": True}},
                    "summary": {"record_count": 0, "types": [], "by_type": {}},
                }
            return {
                "marker": "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__",
                "ok": True,
                "status": "success",
                "records": [
                    {
                        "index": 0,
                        "ts": 1,
                        "type": "childList",
                        "target": {"nodeType": "element", "tag": "body"},
                        "attributeName": None,
                        "oldValue": None,
                        "addedNodes": [{"nodeType": "element", "tag": "div", "text": "after"}],
                        "removedNodes": [],
                    },
                    {
                        "index": 1,
                        "ts": 2,
                        "type": "attributes",
                        "target": {"nodeType": "element", "tag": "main"},
                        "attributeName": "data-token",
                        "oldValue": None,
                        "addedNodes": [],
                        "removedNodes": [],
                    },
                ],
                "trigger": {"attempted": True, "ok": True, "result": {"value": "mutated"}},
                "observer": {"target": "document.body", "options": {"childList": True, "attributes": True}},
                "summary": {
                    "record_count": 2,
                    "types": ["attributes", "childList"],
                    "by_type": {"attributes": 1, "childList": 1},
                },
            }
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


class MutationObserverTimelineManagerTests(unittest.TestCase):
    def test_mutation_observer_timeline_from_context_accepts_options(self) -> None:
        spec = MutationObserverTimelineSpec.from_context(
            {
                "triggerExpression": "mutatePage()",
                "observerWaitMs": 25,
                "mutation_record_limit": 12,
                "maxPreviewLength": 64,
                "observeChildList": False,
                "observeAttributes": True,
                "observeCharacterData": False,
                "subtree": False,
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.trigger_expression, "mutatePage()")
        self.assertEqual(spec.wait_after_trigger_ms, 25)
        self.assertEqual(spec.max_records, 12)
        self.assertEqual(spec.max_preview_length, 64)
        self.assertFalse(spec.observe_child_list)
        self.assertTrue(spec.observe_attributes)
        self.assertFalse(spec.observe_character_data)
        self.assertFalse(spec.subtree)

    def test_mutation_observer_timeline_captures_records_and_summary(self) -> None:
        page = PageMutationAuditPage()
        spec = MutationObserverTimelineSpec.from_context({"trigger_expression": "mutatePage()", "observer_wait_ms": 1})

        result = MutationObserverTimelineManager().observe(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0]["type"], "childList")
        self.assertEqual(result.records[1]["attributeName"], "data-token")
        self.assertTrue(result.trigger["attempted"])
        self.assertTrue(result.trigger["ok"])
        self.assertEqual(result.summary["record_count"], 2)
        self.assertEqual(result.summary["types"], ["attributes", "childList"])

    def test_mutation_observer_timeline_without_records_is_partial(self) -> None:
        page = PageMutationAuditPage()
        spec = MutationObserverTimelineSpec.from_context({"trigger_expression": "noMutation()", "observer_wait_ms": 1})

        result = MutationObserverTimelineManager().observe(page, spec)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.records, [])
        self.assertTrue(result.trigger["attempted"])
        self.assertEqual(result.summary["record_count"], 0)

    def test_mutation_observer_timeline_expression_uses_mutation_observer_marker(self) -> None:
        spec = MutationObserverTimelineSpec.from_context({"trigger_expression": "mutatePage()"})

        self.assertIsNotNone(spec)
        assert spec is not None
        expression = MutationObserverTimelineManager._timeline_expression(spec)
        self.assertIn("__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__", expression)
        self.assertIn("new MutationObserver", expression)
        self.assertIn("observer.takeRecords()", expression)
        self.assertIn("triggerExpression", expression)


if __name__ == "__main__":
    unittest.main()

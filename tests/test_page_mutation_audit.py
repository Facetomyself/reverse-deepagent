import unittest

from reverse_deepagent.browser.hooks import (
    MutationObserverTimelineManager,
    MutationObserverTimelineSpec,
    ObjectGraphDiffManager,
    ObjectGraphDiffSpec,
    ObjectRootMutationAuditManager,
    ObjectRootMutationAuditSpec,
    PageMutationAuditManager,
    PageMutationAuditSpec,
)


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
        self.object_root_mutated = False

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
        if "__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__" in expression:
            token_descriptor = {
                "exists": True,
                "enumerable": True,
                "configurable": True,
                "writable": not self.object_root_mutated,
                "hasGetter": False,
                "hasSetter": False,
                "kind": "data",
            }
            children = {
                "token": {
                    "path": "window.__appState.token",
                    "key": "token",
                    "type": "string",
                    "preview": "after" if self.object_root_mutated else "before",
                    "descriptor": token_descriptor,
                },
                "accessorSecret": {
                    "path": "window.__appState.accessorSecret",
                    "key": "accessorSecret",
                    "type": "accessor",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": False,
                        "hasGetter": True,
                        "hasSetter": False,
                        "kind": "accessor",
                    },
                    "accessor": {"hasGetter": True, "hasSetter": False},
                },
            }
            if self.object_root_mutated:
                children["nonce"] = {
                    "path": "window.__appState.nonce",
                    "key": "nonce",
                    "type": "number",
                    "preview": "7",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": True,
                        "writable": True,
                        "hasGetter": False,
                        "hasSetter": False,
                        "kind": "data",
                    },
                }
            else:
                children["stale"] = {
                    "path": "window.__appState.stale",
                    "key": "stale",
                    "type": "boolean",
                    "preview": "true",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": True,
                        "writable": True,
                        "hasGetter": False,
                        "hasSetter": False,
                        "kind": "data",
                    },
                }
            return {
                "marker": "__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__",
                "ok": True,
                "status": "success",
                "root_path": "window.__appState",
                "root": {"path": "window.__appState", "type": "object", "own_property_count": len(children), "children": children},
                "side_effect_policy": {
                    "default_recon": False,
                    "trigger_required_for_mutation": True,
                    "getter_invocation": False,
                    "prototype_traversal": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
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
        if "mutateObjectRoot()" in expression:
            self.object_root_mutated = True
            return "object-mutated"
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


class ObjectRootMutationAuditManagerTests(unittest.TestCase):
    def test_from_context_accepts_aliases_and_limits(self) -> None:
        spec = ObjectRootMutationAuditSpec.from_context(
            {
                "objectRootPath": "window.__appState",
                "triggerExpression": "mutateObjectRoot()",
                "maxDepth": 3,
                "maxKeys": 12,
                "maxPreviewLength": 48,
                "includeDescriptors": True,
                "includeValues": False,
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.root_path, "window.__appState")
        self.assertEqual(spec.trigger_expression, "mutateObjectRoot()")
        self.assertEqual(spec.max_depth, 3)
        self.assertEqual(spec.max_keys, 12)
        self.assertEqual(spec.max_preview_length, 48)
        self.assertTrue(spec.include_descriptors)
        self.assertFalse(spec.include_values)

    def test_audit_diffs_object_root_without_getter_invocation(self) -> None:
        page = PageMutationAuditPage()
        spec = ObjectRootMutationAuditSpec.from_context({"root_path": "window.__appState", "trigger_expression": "mutateObjectRoot()"})

        result = ObjectRootMutationAuditManager().audit(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.trigger["ok"])
        self.assertTrue(result.diff["changed"])
        self.assertEqual(result.diff["change_count"], 4)
        self.assertEqual(result.diff["categories"], ["added", "descriptor", "removed", "value"])
        self.assertEqual(result.diff["added_paths"], ["window.__appState.nonce"])
        self.assertEqual(result.diff["removed_paths"], ["window.__appState.stale"])
        self.assertIn("window.__appState.token", result.diff["changed_paths"])
        self.assertIn("window.__appState.token", result.diff["descriptor_changed_paths"])
        self.assertFalse(result.side_effect_policy["getter_invocation"])
        accessor = result.before["root"]["children"]["accessorSecret"]
        self.assertEqual(accessor["type"], "accessor")
        self.assertTrue(accessor["descriptor"]["hasGetter"])

    def test_audit_without_trigger_is_partial(self) -> None:
        page = PageMutationAuditPage()
        spec = ObjectRootMutationAuditSpec.from_context({"object_root": "window.__appState"})

        result = ObjectRootMutationAuditManager().audit(page, spec)

        self.assertEqual(result.status, "partial")
        self.assertFalse(result.trigger["attempted"])
        self.assertFalse(result.diff["changed"])
        self.assertEqual(result.diff["change_count"], 0)

    def test_blocks_unsafe_root_path(self) -> None:
        page = PageMutationAuditPage()
        spec = ObjectRootMutationAuditSpec.from_context({"root_path": "window.__appState[token]", "trigger_expression": "mutateObjectRoot()"})

        result = ObjectRootMutationAuditManager().audit(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "unsupported_object_root_path")
        self.assertFalse(page.object_root_mutated)

    def test_snapshot_expression_uses_descriptors_without_dynamic_path_eval(self) -> None:
        spec = ObjectRootMutationAuditSpec.from_context({"root_path": "window.__appState"})

        self.assertIsNotNone(spec)
        assert spec is not None
        expression = ObjectRootMutationAuditManager._snapshot_expression(spec)
        self.assertIn("__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__", expression)
        self.assertIn("Object.getOwnPropertyDescriptor", expression)
        self.assertIn("root_path_accessor_not_invoked", expression)
        self.assertNotIn('Function("return (" + config.rootPath', expression)
        self.assertIn("prototype_traversal: false", expression)


class ObjectGraphDiffManagerTests(unittest.TestCase):
    def test_reviews_object_root_snapshots_without_runtime_side_effects(self) -> None:
        before = {
            "root_path": "window.__appState",
            "root": {
                "path": "window.__appState",
                "type": "object",
                "children": {
                    "token": {"path": "window.__appState.token", "type": "string", "preview": "before"},
                    "count": {"path": "window.__appState.count", "type": "number", "value": 1},
                },
            },
        }
        after = {
            "root_path": "window.__appState",
            "root": {
                "path": "window.__appState",
                "type": "object",
                "children": {
                    "token": {"path": "window.__appState.token", "type": "string", "preview": "after"},
                    "count": {"path": "window.__appState.count", "type": "number", "value": 2},
                    "nonce": {"path": "window.__appState.nonce", "type": "string", "preview": "n1"},
                },
            },
        }
        spec = ObjectGraphDiffSpec.from_context(
            {
                "object_graph_diff": True,
                "before_snapshot": before,
                "after_snapshot": after,
                "graph_roots": ["window.__appState"],
            }
        )

        result = ObjectGraphDiffManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.object-graph-diff.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertEqual(descriptor["diff"]["diff_engine"], "object_root_snapshot")
        self.assertTrue(descriptor["changed"])
        self.assertEqual(descriptor["change_count"], 3)
        self.assertIn("window.__appState.nonce", descriptor["diff"]["added_paths"])
        redacted_changes = {item["path"]: item for item in descriptor["diff"]["changes"]}
        self.assertEqual(redacted_changes["window.__appState.token"]["before"], "<redacted>")
        self.assertEqual(redacted_changes["window.__appState.token"]["after"], "<redacted>")
        self.assertTrue(redacted_changes["window.__appState.token"]["redacted"])
        self.assertEqual(descriptor["risk_summary"]["risk"], "high")
        self.assertIn("sensitive_like_path_changed", descriptor["risk_summary"]["reasons"])
        self.assertFalse(descriptor["side_effect_policy"]["browser_started"])
        self.assertFalse(descriptor["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(descriptor["side_effect_policy"]["runtime_evaluated"])
        self.assertFalse(descriptor["side_effect_policy"]["calls_mcp"])

    def test_reviews_generic_json_graph_and_redacts_sensitive_values(self) -> None:
        spec = ObjectGraphDiffSpec.from_context(
            {
                "jsObjectGraphDiff": True,
                "before": {"store": {"authToken": "before", "items": [1], "optional": None}},
                "after": {"store": {"authToken": "after", "items": [1, 2], "optional": "set"}},
                "includeValues": True,
            }
        )

        result = ObjectGraphDiffManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        changes = {item["path"]: item for item in result.descriptor["diff"]["changes"]}
        self.assertEqual(changes["graph.store.authToken"]["before"], "<redacted>")
        self.assertEqual(changes["graph.store.authToken"]["after"], "<redacted>")
        self.assertEqual(changes["graph.store.items"]["category"], "structure")
        self.assertEqual(changes["graph.store.optional"]["category"], "type")
        self.assertEqual(changes["graph.store.optional"]["before"], "null")
        self.assertEqual(changes["graph.store.optional"]["after"], "string")
        self.assertEqual(result.descriptor["risk_summary"]["risk"], "high")

    def test_blocks_missing_before_or_after_snapshot_without_side_effects(self) -> None:
        spec = ObjectGraphDiffSpec.from_context({"object_graph_diff": True, "before_snapshot": {"root": {"type": "object"}}})

        result = ObjectGraphDiffManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "missing_before_or_after_snapshot")
        self.assertEqual(result.descriptor["blockers"], ["missing_before_or_after_snapshot"])
        self.assertFalse(result.side_effect_policy["browser_started"])


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

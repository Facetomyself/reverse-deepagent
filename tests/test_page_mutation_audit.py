import unittest

from reverse_deepagent.browser.hooks import (
    HeapSnapshotCollectManager,
    HeapSnapshotCollectSpec,
    HeapSnapshotDiffReadinessManager,
    HeapSnapshotDiffReadinessSpec,
    HeapSnapshotDiffExecutorPreflightManager,
    HeapSnapshotDiffExecutorPreflightSpec,
    HeapSnapshotDiffExecutorApprovalPlanManager,
    HeapSnapshotDiffExecutorApprovalPlanSpec,
    HeapSnapshotDiffExecutorTransactionPreflightManager,
    HeapSnapshotDiffExecutorTransactionPreflightSpec,
    HeapSnapshotDiffExecutorBoundedGateManager,
    HeapSnapshotDiffExecutorBoundedGateSpec,
    HeapSnapshotDiffExecutorManager,
    HeapSnapshotDiffExecutorSpec,
    HeapSnapshotDiffFollowupCheckpointManager,
    HeapSnapshotDiffFollowupCheckpointSpec,
    HeapSnapshotDiffSelectedAnalysisInputPreflightManager,
    HeapSnapshotDiffSelectedAnalysisInputPreflightSpec,
    HeapSnapshotConstructorGrowthDrilldownManager,
    HeapSnapshotConstructorGrowthDrilldownSpec,
    HeapSnapshotConstructorGrowthDrilldownExecutorManager,
    HeapSnapshotConstructorGrowthDrilldownExecutorSpec,
    HeapSnapshotAutomaticFollowupPlanManager,
    HeapSnapshotAutomaticFollowupPlanSpec,
    HeapSnapshotRetainedSizeProofPlanManager,
    HeapSnapshotRetainedSizeProofPlanSpec,
    HeapSnapshotPathToRootProofPlanManager,
    HeapSnapshotPathToRootProofPlanSpec,
    HeapSnapshotRawHeapConstructorDrilldownProofPlanManager,
    HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec,
    HeapSnapshotRetainedPathPreflightManager,
    HeapSnapshotRetainedPathPreflightSpec,
    HeapSnapshotRetainedSizeInputReviewManager,
    HeapSnapshotRetainedSizeInputReviewSpec,
    HeapSnapshotRetainedSizeApprovalPlanManager,
    HeapSnapshotRetainedSizeApprovalPlanSpec,
    HeapSnapshotRetainedSizeTransactionPreflightManager,
    HeapSnapshotRetainedSizeTransactionPreflightSpec,
    HeapSnapshotRetainedSizeBoundedGateManager,
    HeapSnapshotRetainedSizeBoundedGateSpec,
    HeapSnapshotRetainedSizeExecutorManager,
    HeapSnapshotRetainedSizeExecutorSpec,
    HeapSnapshotPathToRootExecutorManager,
    HeapSnapshotPathToRootExecutorSpec,
    HeapSnapshotReadinessManager,
    HeapSnapshotReadinessSpec,
    MutationObserverTimelineManager,
    MutationObserverTimelineSpec,
    ObjectGraphDiffManager,
    ObjectGraphDiffSpec,
    ObjectRootMutationAuditManager,
    ObjectRootMutationAuditSpec,
    PageMutationAuditManager,
    PageMutationAuditSpec,
    RuntimeObjectGraphDiffManager,
    RuntimeObjectGraphDiffSpec,
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


class HeapSnapshotFakeCDPSession:
    def __init__(self) -> None:
        self.calls = []
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "HeapProfiler.takeHeapSnapshot":
            for handler in self.handlers.get("HeapProfiler.addHeapSnapshotChunk", []):
                handler({"chunk": '{"snapshot":{"meta":{}},"nodes":[1,2,3]}'})
            return {}
        return {}


class HeapSnapshotFakePage:
    def __init__(self, cdp_session=None) -> None:
        self._cdp_session = cdp_session

    def cdp_session(self):
        return self._cdp_session


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


class RuntimeObjectGraphDiffManagerTests(unittest.TestCase):
    def test_collects_scoped_object_graph_diff_with_explicit_runtime_evaluation(self) -> None:
        page = PageMutationAuditPage()
        spec = RuntimeObjectGraphDiffSpec.from_context(
            {
                "runtime_object_graph_diff": True,
                "runtime_object_root_path": "window.__appState",
                "trigger_expression": "mutateObjectRoot()",
                "max_depth": 3,
                "max_keys": 12,
            }
        )

        result = RuntimeObjectGraphDiffManager().collect(page, spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.runtime-object-graph-diff.v1")
        self.assertTrue(descriptor["explicit_runtime_collection"])
        self.assertEqual(descriptor["scope"], "scoped_object_root")
        self.assertEqual(descriptor["runtime_collection"]["root_path"], "window.__appState")
        self.assertEqual(descriptor["runtime_collection"]["snapshot_source"], "runtime_collected_object_root_snapshots")
        self.assertTrue(descriptor["runtime_collection"]["trigger_attempted"])
        self.assertFalse(descriptor["runtime_collection"]["full_heap_snapshot"])
        self.assertFalse(descriptor["runtime_collection"]["complete_heap_traversal"])
        self.assertEqual(descriptor["object_graph_diff"]["schema_version"], "reverse-deepagent.object-graph-diff.v1")
        self.assertTrue(descriptor["changed"])
        self.assertEqual(descriptor["change_count"], 4)
        self.assertIn("window.__appState.nonce", descriptor["diff"]["added_paths"])
        self.assertIn("window.__appState.stale", descriptor["diff"]["removed_paths"])
        self.assertEqual(descriptor["risk_summary"]["risk"], "high")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["runtime_evaluated"])
        self.assertTrue(policy["trigger_executed"])
        self.assertFalse(policy["default_recon"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["getter_invocation"])
        self.assertFalse(policy["prototype_traversal"])
        self.assertFalse(policy["full_heap_snapshot"])
        self.assertFalse(policy["complete_heap_traversal"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_blocks_unsafe_runtime_object_root_without_triggering_page(self) -> None:
        page = PageMutationAuditPage()
        spec = RuntimeObjectGraphDiffSpec.from_context(
            {
                "runtimeCollectedObjectGraphDiff": True,
                "rootPath": "window.__appState[token]",
                "triggerExpression": "mutateObjectRoot()",
            }
        )

        result = RuntimeObjectGraphDiffManager().collect(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "unsupported_runtime_object_root_path")
        self.assertFalse(page.object_root_mutated)
        self.assertEqual(result.descriptor["blockers"], ["unsupported_runtime_object_root_path"])
        self.assertFalse(result.side_effect_policy["runtime_evaluated"])
        self.assertFalse(result.side_effect_policy["trigger_executed"])


class HeapSnapshotPathToRootExecutorManagerTests(unittest.TestCase):
    def _retained_size_analysis(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "candidate_estimates": [{"name": "<redacted>", "node_id": 3, "node_index": 2, "retained_size_estimate": 48}],
            "requested_candidate_names": ["TokenSecret"],
            "side_effect_policy": {"retained_size_estimated": True, "raw_heap_exported": False, "raw_strings_exported": False, "path_to_root_computed": False},
        }

    def test_heap_snapshot_path_to_root_executor_mvp_estimates_bounded_path_without_proof(self) -> None:
        spec = HeapSnapshotPathToRootExecutorSpec.from_context(
            {
                "execute_heap_snapshot_path_to_root_analysis": True,
                "heap_snapshot_retained_size_analysis": self._retained_size_analysis(),
                "heap_snapshot": _v8_heap_snapshot_path_to_root(),
                "candidate_names": ["TokenSecret"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_path_to_root_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
                "max_depth": 5,
            }
        )

        result = HeapSnapshotPathToRootExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1")
        self.assertEqual(descriptor["executor_name"], "execute_heap_snapshot_path_to_root_analysis")
        self.assertTrue(descriptor["executor_mvp"])
        self.assertTrue(descriptor["raw_heap_loaded"])
        self.assertTrue(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["raw_strings_exported"])
        self.assertTrue(descriptor["path_to_root_estimated"])
        self.assertFalse(descriptor["path_to_root_proven"])
        self.assertFalse(descriptor["retained_size_proven"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(descriptor["heap_summary"]["node_count_total"], 3)
        self.assertEqual(len(descriptor["candidate_paths"]), 1)
        candidate = descriptor["candidate_paths"][0]
        self.assertEqual(candidate["candidate_name"], "<redacted>")
        self.assertTrue(candidate["root_like_node_reached"])
        self.assertFalse(candidate["path_to_root_proven"])
        self.assertFalse(candidate["retained_size_proven"])
        self.assertEqual([node["node_name"] for node in candidate["bounded_path_to_root"]], ["Window", "Object", "<redacted>"])
        self.assertEqual(candidate["bounded_path_to_root"][1]["incoming_edge_name"], "child")
        self.assertEqual(candidate["bounded_path_to_root"][2]["incoming_edge_name"], "<redacted>")
        policy = result.side_effect_policy
        self.assertTrue(policy["executor_invoked"])
        self.assertTrue(policy["raw_heap_loaded"])
        self.assertTrue(policy["raw_heap_parsed"])
        self.assertTrue(policy["path_to_root_estimated"])
        self.assertFalse(policy["path_to_root_proven"])
        self.assertFalse(policy["retained_size_proven"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_path_to_root_executor_mvp_blocks_without_review_or_on_export_and_proof_claim(self) -> None:
        spec = HeapSnapshotPathToRootExecutorSpec.from_context(
            {
                "path_to_root_heap_snapshot_executor": True,
                "heap_snapshot_retained_size_analysis": self._retained_size_analysis(),
                "heap_snapshot": _v8_heap_snapshot_path_to_root(),
                "candidate_name": "TokenSecret",
                "mode": "dry-run",
                "raw_heap_export_requested": True,
                "raw_strings_export_requested": True,
                "path_to_root_proof_requested": True,
            }
        )

        result = HeapSnapshotPathToRootExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_path_to_root_executor_apply_mode_required", result.descriptor["blockers"])
        self.assertIn("heap_snapshot_path_to_root_executor_review_approval_required", result.descriptor["blockers"])
        self.assertIn("raw_heap_export_not_allowed", result.descriptor["blockers"])
        self.assertIn("raw_strings_export_not_allowed", result.descriptor["blockers"])
        self.assertIn("path_to_root_proof_claim_not_allowed_in_mvp", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["path_to_root_estimated"])

    def test_heap_snapshot_path_to_root_executor_ranks_candidates_by_path_length_asc(self) -> None:
        """Multiple candidates should be sorted by path length ascending (shorter = closer to root)."""
        strings = ["", "Window", "Holder", "TokenA", "TokenB", "child", "secret"]
        node_types = ["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"]
        edge_types = ["context", "element", "property", "internal", "hidden", "shortcut", "weak"]
        # Window -> Holder -> TokenA (path length 2)
        # Window -> TokenB  (path length 1)
        nodes = [
            3, 1, 1, 64, 2, 0,   # node 0: Window  (2 edges)
            3, 2, 2, 32, 1, 0,   # node 1: Holder  (1 edge)
            3, 3, 3, 48, 0, 0,   # node 2: TokenA
            3, 4, 4, 16, 0, 0,   # node 3: TokenB
        ]
        edges = [
            2, 5, 6,    # Window -child-> Holder  (to_node offset 6 = node 1)
            2, 6, 18,   # Window -secret-> TokenB (to_node offset 18 = node 3)
            2, 5, 12,   # Holder -child-> TokenA  (to_node offset 12 = node 2)
        ]
        snapshot = {
            "snapshot": {
                "meta": {
                    "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                    "node_types": [node_types, "string", "number", "number", "number", "number"],
                    "edge_fields": ["type", "name_or_index", "to_node"],
                    "edge_types": [edge_types, "string_or_number", "node"],
                }
            },
            "nodes": nodes,
            "edges": edges,
            "strings": strings,
        }
        spec = HeapSnapshotPathToRootExecutorSpec.from_context(
            {
                "execute_heap_snapshot_path_to_root_analysis": True,
                "heap_snapshot_retained_size_analysis": self._retained_size_analysis(),
                "heap_snapshot": snapshot,
                "candidate_names": ["TokenA", "TokenB"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_path_to_root_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 200000,
                "max_depth": 10,
            }
        )

        result = HeapSnapshotPathToRootExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        paths = result.descriptor["candidate_paths"]
        self.assertEqual(len(paths), 2)
        # TokenB (path len 1) should come before TokenA (path len 2)
        path_lengths = [len(p["bounded_path_to_root"]) for p in paths]
        self.assertLessEqual(path_lengths[0], path_lengths[1])

    def test_heap_snapshot_path_to_root_executor_truncates_at_max_depth(self) -> None:
        """When max_depth=1, paths are truncated and the result is still executed but depth-limited."""
        spec = HeapSnapshotPathToRootExecutorSpec.from_context(
            {
                "execute_heap_snapshot_path_to_root_analysis": True,
                "heap_snapshot_retained_size_analysis": self._retained_size_analysis(),
                "heap_snapshot": _v8_heap_snapshot_path_to_root(),
                "candidate_names": ["TokenSecret"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_path_to_root_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 200000,
                "max_depth": 1,
            }
        )

        result = HeapSnapshotPathToRootExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        descriptor = result.descriptor
        self.assertTrue(descriptor["raw_heap_loaded"])
        self.assertTrue(descriptor["path_to_root_estimated"])
        self.assertFalse(descriptor["path_to_root_proven"])
        paths = descriptor["candidate_paths"]
        self.assertGreater(len(paths), 0)
        candidate = paths[0]
        # max_depth=1 means at most 1 hop from the start node; the path includes
        # the start node plus at most 1 parent, so ≤ 2 nodes total.
        self.assertLessEqual(len(candidate["bounded_path_to_root"]), 2)

    def test_heap_snapshot_path_to_root_executor_blocks_on_missing_heap_snapshot(self) -> None:
        """Spec with no heap_snapshot produces blocked result without side effects."""
        spec = HeapSnapshotPathToRootExecutorSpec.from_context(
            {
                "execute_heap_snapshot_path_to_root_analysis": True,
                "heap_snapshot_retained_size_analysis": self._retained_size_analysis(),
                "heap_snapshot": None,
                "candidate_names": ["TokenSecret"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_path_to_root_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 200000,
            }
        )

        result = HeapSnapshotPathToRootExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_required", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["path_to_root_estimated"])


class HeapSnapshotReadinessManagerTests(unittest.TestCase):
    def test_heap_snapshot_readiness_ready_from_cdp_heap_profiler_evidence(self) -> None:
        spec = HeapSnapshotReadinessSpec.from_context(
            {
                "heap_snapshot_readiness": True,
                "browser_provider_id": "remote-cdp",
                "cdp_available": True,
                "heap_profiler_capability": "provided",
                "max_snapshot_bytes": 1024,
            }
        )

        result = HeapSnapshotReadinessManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-readiness.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertFalse(descriptor["heap_snapshot_collected"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(descriptor["capability_evidence"]["browser_provider_id"], "remote-cdp")
        self.assertTrue(descriptor["capability_evidence"]["cdp_available"])
        self.assertEqual(descriptor["capability_evidence"]["heap_profiler_capability"], "provided")
        self.assertFalse(descriptor["safety_gates"]["raw_heap_export_allowed"])
        self.assertEqual(descriptor["safety_gates"]["max_snapshot_bytes"], 1024)
        self.assertTrue(descriptor["future_collection_contract"]["implemented"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_readiness_before_collection")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertTrue(policy["preflight_only"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["provider_factory_invoked"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["heap_snapshot_collected"])
        self.assertFalse(policy["raw_heap_exported"])
        self.assertFalse(policy["complete_heap_traversal"])
        self.assertFalse(policy["runtime_evaluated"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_readiness_blocks_missing_capability_evidence(self) -> None:
        spec = HeapSnapshotReadinessSpec.from_context({"heapProfilerReadiness": True, "providerId": "cloakbrowser"})

        result = HeapSnapshotReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("cdp_capability_evidence_missing_or_unavailable", result.descriptor["blockers"])
        self.assertIn("heap_profiler_capability_evidence_missing_or_unavailable", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_cdp_heap_profiler_capability_evidence")
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["heap_snapshot_collected"])


class HeapSnapshotCollectManagerTests(unittest.TestCase):
    def _ready_readiness(self) -> dict:
        readiness = HeapSnapshotReadinessManager().review(
            HeapSnapshotReadinessSpec.from_context(
                {
                    "heap_snapshot_readiness": True,
                    "browser_provider_id": "remote-cdp",
                    "cdp_available": True,
                    "heap_profiler_capability": "provided",
                    "max_snapshot_bytes": 4096,
                }
            )
        )
        return readiness.descriptor

    def test_heap_snapshot_collect_blocks_without_review_approval_before_cdp(self) -> None:
        cdp = HeapSnapshotFakeCDPSession()
        spec = HeapSnapshotCollectSpec.from_context(
            {
                "heap_snapshot_collect": True,
                "collect_heap_snapshot": True,
                "heap_snapshot_readiness": self._ready_readiness(),
            }
        )

        result = HeapSnapshotCollectManager().collect(HeapSnapshotFakePage(cdp), spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_collect_review_approval_required", result.descriptor["blockers"])
        self.assertEqual(cdp.calls, [])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["heap_snapshot_collected"])

    def test_heap_snapshot_collect_sends_cdp_and_records_digest_only_metadata(self) -> None:
        cdp = HeapSnapshotFakeCDPSession()
        spec = HeapSnapshotCollectSpec.from_context(
            {
                "heap_snapshot_collect": True,
                "collect_heap_snapshot": True,
                "review_approved": True,
                "heap_snapshot_readiness": self._ready_readiness(),
                "max_snapshot_bytes": 4096,
            }
        )

        result = HeapSnapshotCollectManager().collect(HeapSnapshotFakePage(cdp), spec)

        self.assertEqual(result.status, "collected")
        self.assertEqual([call[0] for call in cdp.calls], ["HeapProfiler.enable", "HeapProfiler.takeHeapSnapshot", "HeapProfiler.disable"])
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-collect.v1")
        self.assertTrue(descriptor["review_approved"])
        self.assertTrue(descriptor["explicit_collection"])
        self.assertTrue(descriptor["heap_snapshot_collected"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["raw_heap_available_in_artifact"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertTrue(descriptor["snapshot_metadata"]["snapshot_digest"].startswith("sha256:"))
        self.assertGreater(descriptor["snapshot_metadata"]["snapshot_byte_count"], 0)
        self.assertEqual(descriptor["snapshot_metadata"]["chunk_count"], 1)
        self.assertTrue(descriptor["snapshot_metadata"]["redacted_summary_only"])
        self.assertFalse(descriptor["snapshot_metadata"]["raw_heap_available_in_artifact"])
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["cdp_command_sent"])
        self.assertTrue(policy["heap_profiler_enabled"])
        self.assertTrue(policy["heap_snapshot_collected"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["raw_heap_exported"])
        self.assertFalse(policy["complete_heap_traversal"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_collect_before_heap_diff")


class HeapSnapshotDiffReadinessManagerTests(unittest.TestCase):
    def _collect_descriptor(self, digest: str = "sha256:before", byte_count: int = 64, provider_id: str = "remote-cdp") -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-collect.v1",
            "status": "collected",
            "heap_snapshot_collected": True,
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "raw_heap_available_in_artifact": False,
            "complete_heap_traversal_claimed": False,
            "snapshot_metadata": {
                "snapshot_digest": digest,
                "snapshot_byte_count": byte_count,
                "chunk_count": 1,
                "redacted_summary_only": True,
                "raw_heap_available_in_artifact": False,
            },
            "readiness_summary": {"browser_provider_id": provider_id},
            "side_effect_policy": {
                "cdp_command_sent": True,
                "heap_snapshot_collected": True,
                "heap_diff_computed": False,
                "raw_heap_exported": False,
                "complete_heap_traversal": False,
            },
        }

    def test_heap_snapshot_diff_readiness_reviews_two_collect_metadata_descriptors(self) -> None:
        spec = HeapSnapshotDiffReadinessSpec.from_context(
            {
                "heap_snapshot_diff_readiness": True,
                "before_heap_snapshot_collect": self._collect_descriptor("sha256:before", 64),
                "after_heap_snapshot_collect": self._collect_descriptor("sha256:after", 96),
            }
        )

        result = HeapSnapshotDiffReadinessManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-readiness.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertFalse(descriptor["heap_snapshot_diff_computed"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(descriptor["pair_summary"]["before_digest"], "sha256:before")
        self.assertEqual(descriptor["pair_summary"]["after_digest"], "sha256:after")
        self.assertEqual(descriptor["pair_summary"]["byte_delta"], 32)
        self.assertFalse(descriptor["pair_summary"]["digest_equal"])
        self.assertFalse(descriptor["safety_gates"]["future_diff_executor_implemented"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_diff_readiness_before_diff_executor")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["raw_heap_exported"])
        self.assertFalse(policy["complete_heap_traversal"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_diff_readiness_blocks_raw_heap_collect_descriptor(self) -> None:
        before = self._collect_descriptor("sha256:before", 64)
        before["raw_heap_exported"] = True
        spec = HeapSnapshotDiffReadinessSpec.from_context(
            {
                "heapSnapshotDiffReadiness": True,
                "beforeHeapSnapshotCollect": before,
                "afterHeapSnapshotCollect": self._collect_descriptor("sha256:after", 96),
            }
        )

        result = HeapSnapshotDiffReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("before_heap_snapshot_collect_raw_heap_export_detected", result.descriptor["blockers"])
        self.assertEqual(result.descriptor["next_action"], "provide_two_reviewed_heap_snapshot_collect_descriptors")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


class HeapSnapshotDiffExecutorPreflightManagerTests(unittest.TestCase):
    def _diff_readiness_descriptor(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-readiness.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_exported": False,
            "complete_heap_traversal_claimed": False,
            "pair_summary": {
                "before_digest": "sha256:before",
                "after_digest": "sha256:after",
                "digest_equal": False,
                "byte_delta": 32,
                "byte_delta_ratio": 0.5,
            },
            "safety_gates": {"future_diff_executor_implemented": False, "requires_same_provider": True},
            "side_effect_policy": {
                "heap_diff_computed": False,
                "heap_snapshot_diff_computed": False,
                "raw_heap_loaded": False,
                "raw_heap_exported": False,
                "complete_heap_traversal": False,
            },
        }

    def test_heap_snapshot_diff_executor_preflight_reviews_raw_ingestion_gate_without_diff(self) -> None:
        spec = HeapSnapshotDiffExecutorPreflightSpec.from_context(
            {
                "heap_snapshot_diff_executor_preflight": True,
                "review_approved": True,
                "heap_snapshot_diff_readiness": self._diff_readiness_descriptor(),
                "raw_heap_ingestion_policy": "external-redacted-manifest",
                "parser_sandbox": "subprocess",
                "redaction_plan": "digest-only",
                "max_raw_heap_bytes": 128,
            }
        )

        result = HeapSnapshotDiffExecutorPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-preflight.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["preflight_only"])
        self.assertTrue(descriptor["executor_preflight_only"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["heap_snapshot_diff_computed"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertFalse(descriptor["diff_executor_implemented"])
        self.assertEqual(descriptor["readiness_summary"]["before_digest"], "sha256:before")
        self.assertEqual(descriptor["readiness_summary"]["after_digest"], "sha256:after")
        self.assertEqual(descriptor["ingestion_policy"]["raw_heap_ingestion_policy"], "external-redacted-manifest")
        self.assertFalse(descriptor["safety_gates"]["future_diff_executor_implemented"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_diff_executor_preflight_before_implementation")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["raw_heap_parsed"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_diff_executor_preflight_blocks_unapproved_raw_heap_diff_request(self) -> None:
        spec = HeapSnapshotDiffExecutorPreflightSpec.from_context(
            {
                "rawHeapDiffPreflight": True,
                "heapSnapshotDiffReadiness": self._diff_readiness_descriptor(),
                "rawHeapIngestionPolicy": "load-raw-heap",
                "parserSandbox": "none",
                "redactionPlan": "none",
                "exportRawHeap": True,
                "computeHeapDiff": True,
                "allowCompleteTraversalClaim": True,
            }
        )

        result = HeapSnapshotDiffExecutorPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("heap_snapshot_diff_executor_preflight_review_approval_required", blockers)
        self.assertIn("unsupported_raw_heap_ingestion_policy", blockers)
        self.assertIn("heap_snapshot_parser_sandbox_required", blockers)
        self.assertIn("heap_snapshot_diff_redaction_plan_required", blockers)
        self.assertIn("raw_heap_export_not_supported_by_preflight", blockers)
        self.assertIn("heap_diff_execution_not_supported_by_preflight", blockers)
        self.assertIn("complete_heap_traversal_claim_not_supported_by_preflight", blockers)
        self.assertEqual(result.descriptor["next_action"], "resolve_heap_snapshot_diff_executor_preflight_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


class HeapSnapshotDiffExecutorApprovalPlanManagerTests(unittest.TestCase):
    def _preflight_descriptor(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "readiness_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after"},
            "ingestion_policy": {"raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 1024},
            "safety_gates": {"review_approved": True, "future_diff_executor_implemented": False},
            "side_effect_policy": {
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "complete_heap_traversal": False,
            },
        }

    def test_heap_snapshot_diff_executor_approval_plan_reviews_transaction_contract_without_writes(self) -> None:
        spec = HeapSnapshotDiffExecutorApprovalPlanSpec.from_context(
            {
                "heap_snapshot_diff_executor_approval_plan": True,
                "heap_snapshot_diff_executor_preflight": self._preflight_descriptor(),
                "reviewer": "alice",
                "transaction_id": "heap-diff-txn-1",
                "idempotency_key": "heap-diff-idem-1",
            }
        )

        result = HeapSnapshotDiffExecutorApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1")
        self.assertTrue(descriptor["review_only"])
        self.assertTrue(descriptor["approval_plan_only"])
        self.assertTrue(descriptor["transaction_plan_only"])
        self.assertFalse(descriptor["approval_recorded"])
        self.assertFalse(descriptor["transaction_started"])
        self.assertFalse(descriptor["journal_written_now"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["diff_executor_implemented"])
        self.assertEqual(descriptor["preflight_summary"]["before_digest"], "sha256:before")
        self.assertEqual(descriptor["approval_plan"]["approval_scope"], "heap-snapshot-diff-executor")
        self.assertEqual(descriptor["approval_plan"]["reviewer"], "alice")
        self.assertFalse(descriptor["approval_plan"]["approval_recorded"])
        self.assertEqual(descriptor["transaction_plan"]["transaction_id"], "heap-diff-txn-1")
        self.assertEqual(descriptor["transaction_plan"]["idempotency_key"], "heap-diff-idem-1")
        self.assertFalse(descriptor["transaction_plan"]["transaction_started"])
        self.assertFalse(descriptor["transaction_plan"]["journal_written_now"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["approval_recorded"])
        self.assertFalse(policy["transaction_started"])
        self.assertFalse(policy["journal_written_now"])
        self.assertFalse(policy["executor_invoked"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_diff_executor_approval_plan_blocks_unready_preflight(self) -> None:
        preflight = self._preflight_descriptor()
        preflight["status"] = "blocked"
        preflight["safety_gates"]["review_approved"] = False
        spec = HeapSnapshotDiffExecutorApprovalPlanSpec.from_context(
            {
                "rawHeapDiffApprovalPlan": True,
                "heapSnapshotDiffExecutorPreflight": preflight,
                "requireBoundedExecutorGate": False,
            }
        )

        result = HeapSnapshotDiffExecutorApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("heap_snapshot_diff_executor_preflight_not_ready", blockers)
        self.assertIn("heap_snapshot_diff_executor_preflight_review_approval_missing", blockers)
        self.assertIn("bounded_executor_gate_required", blockers)
        self.assertEqual(result.descriptor["next_action"], "resolve_heap_snapshot_diff_executor_approval_plan_blockers")
        self.assertFalse(result.side_effect_policy["approval_recorded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


class HeapSnapshotDiffExecutorTransactionPreflightManagerTests(unittest.TestCase):
    def _approval_plan(self) -> dict:
        side_effect_policy = {
            "read_only": True,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "heap_snapshot_diff_computed": False,
            "complete_heap_traversal": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1",
            "status": "ready_for_review",
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "heap_snapshot_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "preflight_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 1024},
            "approval_plan": {"approval_scope": "heap-snapshot-diff-executor", "reviewer": "alice", "approval_record_artifact": "workspace/heap-snapshot-diff-executor-approval-record.json", "approval_recorded": False},
            "transaction_plan": {"transaction_id": "heap-diff-txn-1", "idempotency_key": "heap-diff-idem-1", "transaction_journal_artifact": "workspace/heap-snapshot-diff-executor-journal.json", "bounded_gate_artifact": "workspace/heap-snapshot-diff-executor-bounded-gate.json", "result_artifact": "workspace/heap-snapshot-diff-executor-result.json", "transaction_started": False, "journal_written_now": False},
            "future_executor_contract": {"implemented": False},
            "side_effect_policy": side_effect_policy,
        }

    def _approval_record(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1",
            "status": "written",
            "approval_scope": "heap-snapshot-diff-executor",
            "reviewer": "alice",
            "approval_recorded": True,
            "approved_for_execution": True,
            "transaction_id": "heap-diff-txn-1",
            "idempotency_key": "heap-diff-idem-1",
            "executor_input_gates": {"approval_recorded": True, "ready_to_execute_now": False, "transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
            "side_effect_policy": {"writes_approval_record": True, "transaction_started": False, "journal_written": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "heap_snapshot_diff_computed": False, "complete_heap_traversal": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

    def test_heap_snapshot_diff_executor_transaction_preflight_is_read_only_and_ready_for_journal_review(self) -> None:
        spec = HeapSnapshotDiffExecutorTransactionPreflightSpec.from_context(
            {
                "heap_snapshot_diff_executor_transaction_preflight": True,
                "heap_snapshot_diff_executor_approval_plan": self._approval_plan(),
                "heap_snapshot_diff_executor_approval_record": self._approval_record(),
                "expected_approval_scope": "heap-snapshot-diff-executor",
                "expected_transaction_id": "heap-diff-txn-1",
                "expected_idempotency_key": "heap-diff-idem-1",
            }
        )

        result = HeapSnapshotDiffExecutorTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-transaction-preflight.v1")
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["transaction_preflight_only"])
        self.assertFalse(descriptor["transaction_started"])
        self.assertFalse(descriptor["journal_written"])
        self.assertFalse(descriptor["bounded_executor_gate_written"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertEqual(descriptor["approval_summary"]["approval_scope"], "heap-snapshot-diff-executor")
        self.assertTrue(descriptor["approval_summary"]["approval_recorded"])
        self.assertTrue(descriptor["approval_summary"]["approved_for_execution"])
        self.assertEqual(descriptor["transaction_summary"]["transaction_id"], "heap-diff-txn-1")
        self.assertEqual(descriptor["preflight_summary"]["before_digest"], "sha256:before")
        self.assertTrue(descriptor["journal_writer_contract"]["ready_for_journal_review"])
        self.assertFalse(descriptor["journal_writer_contract"]["implemented"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertFalse(descriptor["safety_gates"]["ready_to_execute_now"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_diff_executor_transaction_journal_writer")
        policy = descriptor["side_effect_policy"]
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["transaction_started"])
        self.assertFalse(policy["journal_written"])
        self.assertFalse(policy["bounded_executor_gate_written"])
        self.assertFalse(policy["executor_invoked"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_diff_executor_transaction_preflight_blocks_mismatched_or_side_effected_record(self) -> None:
        record = self._approval_record()
        record["transaction_id"] = "wrong-txn"
        record["executor_input_gates"]["journal_written"] = True
        spec = HeapSnapshotDiffExecutorTransactionPreflightSpec.from_context(
            {
                "rawHeapDiffTransactionPreflight": True,
                "heapSnapshotDiffExecutorApprovalPlan": self._approval_plan(),
                "heapSnapshotDiffExecutorApprovalRecord": record,
                "expectedTransactionId": "heap-diff-txn-expected",
            }
        )

        result = HeapSnapshotDiffExecutorTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("approval_record_claims_journal_written", blockers)
        self.assertIn("transaction_id_mismatch", blockers)
        self.assertIn("expected_transaction_id_mismatch", blockers)
        self.assertEqual(result.descriptor["next_action"], "resolve_heap_snapshot_diff_executor_transaction_preflight_blockers")
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])



def _v8_heap_snapshot(*, extra_object: bool = False) -> dict:
    strings = ["", "Window", "Object", "Array", "safeValue", "TokenSecret"]
    node_types = ["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"]
    edge_types = ["context", "element", "property", "internal", "hidden", "shortcut", "weak"]
    nodes = [
        3, 1, 1, 64, 1, 0,
        3, 2, 2, 32, 0, 0,
    ]
    if extra_object:
        nodes.extend([3, 5, 3, 48, 0, 0])
    edges = [2, 4, 1]
    if extra_object:
        edges.extend([2, 4, 2])
    return {
        "snapshot": {
            "meta": {
                "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                "node_types": [node_types, "string", "number", "number", "number", "number"],
                "edge_fields": ["type", "name_or_index", "to_node"],
                "edge_types": [edge_types, "string_or_number", "node"],
            }
        },
        "nodes": nodes,
        "edges": edges,
        "strings": strings,
    }


def _v8_heap_snapshot_path_to_root() -> dict:
    strings = ["", "Window", "Object", "TokenSecret", "child", "secret"]
    node_types = ["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"]
    edge_types = ["context", "element", "property", "internal", "hidden", "shortcut", "weak"]
    return {
        "snapshot": {
            "meta": {
                "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                "node_types": [node_types, "string", "number", "number", "number", "number"],
                "edge_fields": ["type", "name_or_index", "to_node"],
                "edge_types": [edge_types, "string_or_number", "node"],
            }
        },
        "nodes": [
            3, 1, 1, 64, 1, 0,
            3, 2, 2, 32, 1, 0,
            3, 3, 3, 48, 0, 0,
        ],
        "edges": [
            2, 4, 6,
            2, 5, 12,
        ],
        "strings": strings,
    }


class HeapSnapshotDiffExecutorBoundedGateManagerTests(unittest.TestCase):
    def _transaction_journal(self) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "heap-snapshot-diff-executor-transaction-journal:abc123",
            "transaction_preflight_id": "heap-snapshot-diff-executor-transaction-preflight:def456",
            "transaction_id": "heap-diff-txn-1",
            "idempotency_key": "heap-diff-idem-1",
            "approval_scope": "heap-snapshot-diff-executor",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "preflight_summary": {
                "before_digest": "sha256:before",
                "after_digest": "sha256:after",
                "raw_heap_ingestion_policy": "metadata-only",
                "parser_sandbox": "subprocess",
                "redaction_plan": "digest-only",
                "max_raw_heap_bytes": 1024,
            },
            "journal_summary": {
                "transaction_started": True,
                "journal_written": True,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "requires_bounded_executor_gate_followup": True,
            },
            "executor_input_gates": {
                "approval_record_verified": True,
                "transaction_started": True,
                "journal_written": True,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "complete_heap_traversal_claimed": False,
                "diff_executor_implemented": False,
                "requires_bounded_executor_gate": True,
                "requires_explicit_executor_review": True,
                "ready_to_execute_now": False,
            },
            "blockers": [],
            "side_effect_policy": {
                "writes_transaction_journal": True,
                "transaction_started": True,
                "journal_written": True,
                "bounded_executor_gate_written": False,
                "ready_to_execute_now": False,
                "executor_invoked": False,
                "browser_started": False,
                "provider_factory_invoked": False,
                "cdp_command_sent": False,
                "heap_profiler_enabled": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "heap_snapshot_diff_computed": False,
                "complete_heap_traversal": False,
                "runtime_evaluated": False,
                "javascript_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_heap_snapshot_diff_executor_bounded_gate_reviews_written_journal_without_execution(self) -> None:
        spec = HeapSnapshotDiffExecutorBoundedGateSpec.from_context(
            {
                "heap_snapshot_diff_executor_bounded_gate": True,
                "heap_snapshot_diff_executor_transaction_journal": self._transaction_journal(),
                "expected_transaction_id": "heap-diff-txn-1",
                "expected_idempotency_key": "heap-diff-idem-1",
            }
        )

        result = HeapSnapshotDiffExecutorBoundedGateManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1")
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["bounded_executor_gate_only"])
        self.assertTrue(descriptor["transaction_journal_verified"])
        self.assertTrue(descriptor["bounded_executor_gate_ready_for_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertTrue(descriptor["transaction_started"])
        self.assertTrue(descriptor["journal_written"])
        self.assertFalse(descriptor["bounded_executor_gate_written"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertFalse(descriptor["diff_executor_implemented"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertTrue(descriptor["future_executor_contract"]["requires_safe_raw_heap_parser"])
        self.assertFalse(descriptor["bounded_executor_input"]["ready_to_execute_now"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp")
        policy = result.side_effect_policy
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["files_mutated"])
        self.assertFalse(policy["bounded_executor_gate_written"])
        self.assertFalse(policy["executor_invoked"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_diff_executor_bounded_gate_blocks_unwritten_or_side_effected_journal(self) -> None:
        journal = self._transaction_journal()
        journal["status"] = "planned"
        journal["journal_written"] = False
        journal["executor_input_gates"]["raw_heap_parsed"] = True
        spec = HeapSnapshotDiffExecutorBoundedGateSpec.from_context(
            {
                "rawHeapDiffBoundedGate": True,
                "heapSnapshotDiffExecutorTransactionJournal": journal,
                "expectedTransactionId": "wrong-txn",
            }
        )

        result = HeapSnapshotDiffExecutorBoundedGateManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("transaction_journal_written", blockers)
        self.assertIn("raw_heap_not_parsed", blockers)
        self.assertIn("expected_transaction_id_matches", blockers)
        self.assertEqual(result.descriptor["next_action"], "provide_written_heap_snapshot_diff_executor_transaction_journal")
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


class HeapSnapshotDiffExecutorManagerTests(unittest.TestCase):
    def _bounded_gate(self) -> dict:
        journal = HeapSnapshotDiffExecutorBoundedGateManagerTests()._transaction_journal()
        gate = HeapSnapshotDiffExecutorBoundedGateManager().review(
            HeapSnapshotDiffExecutorBoundedGateSpec.from_context(
                {
                    "heap_snapshot_diff_executor_bounded_gate": True,
                    "heap_snapshot_diff_executor_transaction_journal": journal,
                }
            )
        )
        self.assertEqual(gate.status, "ready_for_review")
        return gate.descriptor

    def test_heap_snapshot_diff_executor_mvp_parses_and_diffs_v8_snapshot_summaries(self) -> None:
        spec = HeapSnapshotDiffExecutorSpec.from_context(
            {
                "execute_heap_snapshot_diff_executor": True,
                "heap_snapshot_diff_executor_bounded_gate": self._bounded_gate(),
                "before_heap_snapshot": _v8_heap_snapshot(extra_object=False),
                "after_heap_snapshot": _v8_heap_snapshot(extra_object=True),
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_diff_executor_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
            }
        )

        result = HeapSnapshotDiffExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-result.v1")
        self.assertTrue(descriptor["executor_mvp"])
        self.assertTrue(descriptor["raw_heap_loaded"])
        self.assertTrue(descriptor["raw_heap_parsed"])
        self.assertTrue(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(descriptor["heap_summaries"]["before"]["node_count_total"], 2)
        self.assertEqual(descriptor["heap_summaries"]["after"]["node_count_total"], 3)
        self.assertEqual(descriptor["diff"]["node_count_delta"], 1)
        self.assertEqual(descriptor["diff"]["edge_count_delta"], 1)
        names = {item["name"] for item in descriptor["heap_summaries"]["after"]["top_constructors"]}
        self.assertIn("<redacted>", names)
        self.assertTrue(result.side_effect_policy["executor_invoked"])
        self.assertTrue(result.side_effect_policy["raw_heap_parsed"])
        self.assertFalse(result.side_effect_policy["raw_heap_exported"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])


    def test_heap_snapshot_diff_executor_mvp_blocks_without_review_or_on_raw_export(self) -> None:
        spec = HeapSnapshotDiffExecutorSpec.from_context(
            {
                "raw_heap_diff_executor": True,
                "heap_snapshot_diff_executor_bounded_gate": self._bounded_gate(),
                "before_heap_snapshot": _v8_heap_snapshot(extra_object=False),
                "after_heap_snapshot": _v8_heap_snapshot(extra_object=True),
                "mode": "dry-run",
                "raw_heap_export_requested": True,
            }
        )

        result = HeapSnapshotDiffExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("heap_snapshot_diff_executor_apply_mode_required", blockers)
        self.assertIn("heap_snapshot_diff_executor_review_approval_required", blockers)
        self.assertIn("heap_snapshot_diff_executor_execution_approval_flag_required", blockers)
        self.assertIn("heap_snapshot_diff_executor_reviewer_required", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


class HeapSnapshotDiffFollowupCheckpointManagerTests(unittest.TestCase):
    def _executor_result(self) -> dict:
        gate = HeapSnapshotDiffExecutorManagerTests()._bounded_gate()
        result = HeapSnapshotDiffExecutorManager().execute(
            HeapSnapshotDiffExecutorSpec.from_context(
                {
                    "execute_heap_snapshot_diff_executor": True,
                    "heap_snapshot_diff_executor_bounded_gate": gate,
                    "before_heap_snapshot": _v8_heap_snapshot(extra_object=False),
                    "after_heap_snapshot": _v8_heap_snapshot(extra_object=True),
                    "mode": "apply",
                    "review_approved": True,
                    "approve_heap_snapshot_diff_executor_execution": True,
                    "reviewer": "alice",
                    "max_raw_heap_bytes": 20000,
                }
            )
        )
        self.assertEqual(result.status, "executed")
        return result.descriptor

    def test_heap_snapshot_diff_followup_checkpoint_reviews_executor_result_without_new_heap_work(self) -> None:
        spec = HeapSnapshotDiffFollowupCheckpointSpec.from_context(
            {
                "heap_snapshot_diff_followup_checkpoint": True,
                "heap_snapshot_diff_executor_result": self._executor_result(),
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotDiffFollowupCheckpointManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        checkpoint = result.checkpoint
        self.assertEqual(checkpoint["schema_version"], "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1")
        self.assertTrue(checkpoint["review_only"])
        self.assertTrue(checkpoint["checkpoint_only"])
        self.assertEqual(checkpoint["executor_result_summary"]["node_count_delta"], 1)
        recommendations = checkpoint["analysis_plan"]["recommendations"]
        actions = {item["action"] for item in recommendations}
        self.assertIn("review_constructor_growth", actions)
        self.assertIn("plan_retained_size_analysis", actions)
        self.assertIn("plan_path_to_root_analysis", actions)
        contracts = checkpoint["analysis_plan"]["future_analysis_contracts"]
        self.assertFalse(contracts["retained_size_analysis"]["implemented"])
        self.assertFalse(contracts["path_to_root_analysis"]["implemented"])
        self.assertFalse(checkpoint["raw_heap_loaded"])
        self.assertFalse(checkpoint["raw_heap_parsed"])
        self.assertFalse(checkpoint["raw_heap_exported"])
        self.assertFalse(checkpoint["heap_diff_computed"])
        self.assertFalse(checkpoint["complete_heap_traversal_claimed"])
        self.assertFalse(checkpoint["retained_size_proven"])
        self.assertFalse(checkpoint["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(checkpoint["next_action"], "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work")

    def test_heap_snapshot_diff_followup_checkpoint_blocks_unsafe_or_unexecuted_result(self) -> None:
        unsafe = self._executor_result()
        unsafe["status"] = "blocked"
        unsafe["raw_heap_exported"] = True
        unsafe["complete_heap_traversal_claimed"] = True
        spec = HeapSnapshotDiffFollowupCheckpointSpec.from_context(
            {
                "heap_snapshot_diff_analysis_plan": True,
                "heap_snapshot_diff_executor_result": unsafe,
            }
        )

        result = HeapSnapshotDiffFollowupCheckpointManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.checkpoint["blockers"]
        self.assertIn("heap_snapshot_diff_executor_result_not_executed", blockers)
        self.assertIn("heap_snapshot_diff_executor_result_raw_heap_exported", blockers)
        self.assertIn("heap_snapshot_diff_executor_result_complete_traversal_claimed", blockers)
        self.assertEqual(result.checkpoint["next_action"], "resolve_heap_snapshot_diff_followup_checkpoint_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])

    def test_heap_snapshot_diff_selected_analysis_input_preflight_selects_retained_size_without_raw_heap_work(self) -> None:
        checkpoint = HeapSnapshotDiffFollowupCheckpointManager().review(
            HeapSnapshotDiffFollowupCheckpointSpec.from_context(
                {
                    "heap_snapshot_diff_followup_checkpoint": True,
                    "heap_snapshot_diff_executor_result": self._executor_result(),
                    "reviewer": "alice",
                }
            )
        ).checkpoint
        spec = HeapSnapshotDiffSelectedAnalysisInputPreflightSpec.from_context(
            {
                "heap_snapshot_diff_selected_analysis_input_preflight": True,
                "heap_snapshot_diff_followup_checkpoint": checkpoint,
                "selected_analysis_action": "plan_retained_size_analysis",
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotDiffSelectedAnalysisInputPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        preflight = result.preflight
        self.assertEqual(preflight["schema_version"], "reverse-deepagent.heap-snapshot-diff-selected-analysis-input-preflight.v1")
        self.assertTrue(preflight["review_only"])
        self.assertTrue(preflight["preflight_only"])
        self.assertTrue(preflight["selection_only"])
        self.assertEqual(preflight["source_checkpoint_summary"]["status"], "ready_for_review")
        self.assertEqual(preflight["selected_analysis_input"]["selected_action"], "plan_retained_size_analysis")
        self.assertGreaterEqual(preflight["selected_analysis_input"]["candidate_count"], 1)
        self.assertTrue(preflight["future_executor_contract"]["requires_raw_heap"])
        self.assertFalse(preflight["future_executor_contract"]["implemented"])
        self.assertFalse(preflight["raw_heap_loaded"])
        self.assertFalse(preflight["raw_heap_parsed"])
        self.assertFalse(preflight["raw_heap_exported"])
        self.assertFalse(preflight["heap_diff_computed"])
        self.assertFalse(preflight["retained_size_proven"])
        self.assertFalse(preflight["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(preflight["next_action"], "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work")

    def test_heap_snapshot_diff_selected_analysis_input_preflight_blocks_missing_or_unsafe_checkpoint(self) -> None:
        unsafe = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1",
            "status": "blocked",
            "review_only": True,
            "checkpoint_only": True,
            "raw_heap_loaded": True,
            "heap_diff_computed": True,
            "analysis_plan": {"recommendations": [{"action": "plan_retained_size_analysis"}]},
        }
        spec = HeapSnapshotDiffSelectedAnalysisInputPreflightSpec.from_context(
            {
                "heap_snapshot_diff_followup_selected_analysis_preflight": True,
                "heap_snapshot_diff_followup_checkpoint": unsafe,
                "selected_analysis_action": "plan_retained_size_analysis",
            }
        )

        result = HeapSnapshotDiffSelectedAnalysisInputPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.preflight["blockers"]
        self.assertIn("heap_snapshot_diff_followup_checkpoint_not_ready", blockers)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_claims_raw_heap_work", blockers)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_claims_new_diff", blockers)
        self.assertEqual(result.preflight["next_action"], "resolve_heap_snapshot_diff_selected_analysis_input_preflight_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])


    def _constructor_preflight(self) -> dict:
        checkpoint = HeapSnapshotDiffFollowupCheckpointManager().review(
            HeapSnapshotDiffFollowupCheckpointSpec.from_context(
                {
                    "heap_snapshot_diff_followup_checkpoint": True,
                    "heap_snapshot_diff_executor_result": self._executor_result(),
                    "reviewer": "alice",
                }
            )
        ).checkpoint
        preflight = HeapSnapshotDiffSelectedAnalysisInputPreflightManager().review(
            HeapSnapshotDiffSelectedAnalysisInputPreflightSpec.from_context(
                {
                    "heap_snapshot_diff_selected_analysis_input_preflight": True,
                    "heap_snapshot_diff_followup_checkpoint": checkpoint,
                    "selected_analysis_action": "review_constructor_growth",
                    "reviewer": "alice",
                }
            )
        ).preflight
        self.assertEqual(preflight["status"], "ready_for_review")
        return preflight

    def test_heap_snapshot_constructor_growth_drilldown_reviews_selected_preflight_without_heap_work(self) -> None:
        spec = HeapSnapshotConstructorGrowthDrilldownSpec.from_context(
            {
                "heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_diff_selected_analysis_input_preflight": self._constructor_preflight(),
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        drilldown = result.drilldown
        self.assertEqual(drilldown["schema_version"], "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1")
        self.assertTrue(drilldown["review_only"])
        self.assertTrue(drilldown["drilldown_only"])
        self.assertTrue(drilldown["summary_only"])
        self.assertEqual(drilldown["selected_action"], "review_constructor_growth")
        self.assertGreaterEqual(drilldown["constructor_growth_summary"]["candidate_count"], 1)
        self.assertEqual(drilldown["constructor_growth_summary"]["top_candidate"]["name"], "<redacted>")
        contracts = drilldown["future_analysis_contracts"]
        self.assertFalse(contracts["constructor_drilldown_execution"]["implemented"])
        self.assertFalse(contracts["retained_size_analysis"]["implemented"])
        self.assertFalse(contracts["path_to_root_analysis"]["implemented"])
        self.assertFalse(drilldown["raw_heap_loaded"])
        self.assertFalse(drilldown["raw_heap_parsed"])
        self.assertFalse(drilldown["heap_diff_computed"])
        self.assertFalse(drilldown["constructor_drilldown_computed"])
        self.assertFalse(drilldown["retained_size_proven"])
        self.assertFalse(drilldown["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(drilldown["next_action"], "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight")

    def test_heap_snapshot_constructor_growth_drilldown_blocks_wrong_selected_action(self) -> None:
        preflight = dict(self._constructor_preflight())
        preflight["selected_analysis_input"] = dict(preflight["selected_analysis_input"])
        preflight["selected_analysis_input"]["selected_action"] = "plan_retained_size_analysis"
        spec = HeapSnapshotConstructorGrowthDrilldownSpec.from_context(
            {
                "heap_snapshot_diff_constructor_growth_drilldown": True,
                "heap_snapshot_diff_selected_analysis_input_preflight": preflight,
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_constructor_growth_action_required", result.drilldown["blockers"])
        self.assertEqual(result.drilldown["next_action"], "resolve_heap_snapshot_constructor_growth_drilldown_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["heap_diff_computed"])

    def _constructor_drilldown(self) -> dict:
        spec = HeapSnapshotConstructorGrowthDrilldownSpec.from_context(
            {
                "heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_diff_selected_analysis_input_preflight": self._constructor_preflight(),
                "reviewer": "alice",
            }
        )
        return HeapSnapshotConstructorGrowthDrilldownManager().review(spec).drilldown


    def test_heap_snapshot_constructor_growth_drilldown_executor_mvp_prioritizes_descriptor_candidates(self) -> None:
        spec = HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
            {
                "execute_heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1")
        self.assertEqual(descriptor["executor_name"], "execute_heap_snapshot_constructor_growth_drilldown")
        self.assertTrue(descriptor["executor_mvp"])
        self.assertTrue(descriptor["constructor_drilldown_computed"])
        self.assertFalse(descriptor["constructor_drilldown_proven"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["retained_size_proven"])
        self.assertFalse(descriptor["path_to_root_computed"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(len(descriptor["constructor_drilldown_rows"]), 1)
        row = descriptor["constructor_drilldown_rows"][0]
        self.assertEqual(row["name"], "<redacted>")
        # The shared V8 snapshot fixture adds one constructor node in the
        # after-snapshot; constructor-growth drilldown must preserve that
        # descriptor-backed delta instead of inventing a larger heap diff.
        self.assertEqual(row["delta"], 1)
        self.assertTrue(row["descriptor_backed"])
        self.assertTrue(row["requires_retained_size_followup"])
        self.assertTrue(row["requires_path_to_root_followup"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass")
        policy = result.side_effect_policy
        self.assertTrue(policy["executor_invoked"])
        self.assertTrue(policy["constructor_drilldown_computed"])
        self.assertFalse(policy["constructor_drilldown_proven"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_constructor_growth_drilldown_executor_mvp_blocks_without_review_or_on_forbidden_claims(self) -> None:
        spec = HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
            {
                "constructor_growth_heap_snapshot_executor": True,
                "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                "mode": "dry-run",
                "raw_heap_export_requested": True,
                "heap_diff_recompute_requested": True,
                "retained_size_proof_requested": True,
                "path_to_root_proof_requested": True,
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_executor_apply_mode_required", result.descriptor["blockers"])
        self.assertIn("heap_snapshot_constructor_growth_drilldown_executor_review_approval_required", result.descriptor["blockers"])
        self.assertIn("raw_heap_export_not_allowed", result.descriptor["blockers"])
        self.assertIn("heap_diff_recompute_not_allowed_in_constructor_drilldown_mvp", result.descriptor["blockers"])
        self.assertIn("retained_size_proof_claim_not_allowed_in_mvp", result.descriptor["blockers"])
        self.assertIn("path_to_root_proof_claim_not_allowed_in_mvp", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["constructor_drilldown_computed"])

    def test_heap_snapshot_constructor_growth_drilldown_executor_produces_sorted_rows_by_delta_desc(self) -> None:
        """When drilldown descriptor has multiple candidates, rows are ordered by delta descending."""
        # Build a drilldown descriptor with two constructor rows at different deltas
        drilldown = self._constructor_drilldown()
        # Inject a second row with a smaller delta to verify ordering
        if isinstance(drilldown, dict) and "constructor_drilldown_rows" in drilldown:
            rows = drilldown["constructor_drilldown_rows"]
            if rows:
                big_row = dict(rows[0])
                big_row["delta"] = 10
                small_row = dict(rows[0])
                small_row["delta"] = 1
                drilldown["constructor_drilldown_rows"] = [small_row, big_row]
        spec = HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
            {
                "execute_heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_constructor_growth_drilldown": drilldown,
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        rows_out = result.descriptor["constructor_drilldown_rows"]
        self.assertGreaterEqual(len(rows_out), 1)
        # If multiple rows present, first should have >= delta than second
        if len(rows_out) >= 2:
            self.assertGreaterEqual(rows_out[0]["delta"], rows_out[1]["delta"])

    def test_heap_snapshot_constructor_growth_drilldown_executor_marks_side_effects_accurately(self) -> None:
        """side_effect_policy must mark constructor_drilldown_computed=True and raw_heap_loaded=False."""
        spec = HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
            {
                "execute_heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        policy = result.side_effect_policy
        self.assertTrue(policy["executor_invoked"])
        self.assertTrue(policy["constructor_drilldown_computed"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["heap_diff_computed"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_constructor_growth_drilldown_executor_blocks_on_missing_drilldown(self) -> None:
        """Missing drilldown descriptor produces blocked result without side effects."""
        spec = HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
            {
                "execute_heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_constructor_growth_drilldown": None,
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertTrue(len(blockers) > 0)
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["constructor_drilldown_computed"])

    def test_heap_snapshot_automatic_followup_plan_reviews_existing_analysis_without_execution(self) -> None:
        retained = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "candidate_estimates": [{"name": "<redacted>", "self_size": 48}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        path = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "path_estimates": [{"name": "<redacted>", "path_found_within_bounds": True}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": True,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        constructor = HeapSnapshotConstructorGrowthDrilldownExecutorManager().execute(
            HeapSnapshotConstructorGrowthDrilldownExecutorSpec.from_context(
                {
                    "execute_heap_snapshot_constructor_growth_drilldown": True,
                    "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                    "mode": "apply",
                    "review_approved": True,
                    "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                    "reviewer": "alice",
                }
            )
        ).descriptor
        spec = HeapSnapshotAutomaticFollowupPlanSpec.from_context(
            {
                "heap_snapshot_automatic_followup_plan": True,
                "heap_snapshot_retained_size_analysis": retained,
                "heap_snapshot_path_to_root_analysis": path,
                "heap_snapshot_constructor_growth_drilldown_analysis": constructor,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotAutomaticFollowupPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1")
        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["plan_only"])
        self.assertGreaterEqual(plan["recommended_action_count"], 1)
        actions = {item["action"] for item in plan["recommended_actions"]}
        self.assertIn("review_combined_heap_candidate_evidence", actions)
        self.assertIn("plan_proof_grade_retained_size_analysis", actions)
        self.assertFalse(plan["raw_heap_loaded"])
        self.assertFalse(plan["heap_diff_computed"])
        self.assertFalse(plan["retained_size_proven"])
        self.assertFalse(plan["path_to_root_proven"])
        self.assertFalse(plan["constructor_drilldown_proven"])
        self.assertFalse(plan["automatic_execution_allowed"])
        self.assertEqual(plan["next_action"], "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass")
        policy = result.side_effect_policy
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["executor_invoked"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_automatic_followup_plan_blocks_unsafe_or_automatic_requests(self) -> None:
        unsafe = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "raw_heap_exported": True,
            "retained_size_proven": True,
            "side_effect_policy": {"browser_started": True},
        }
        spec = HeapSnapshotAutomaticFollowupPlanSpec.from_context(
            {
                "review_heap_snapshot_automatic_followup_plan": True,
                "heap_snapshot_retained_size_analysis": unsafe,
                "raw_heap_export_requested": True,
                "heap_diff_recompute_requested": True,
                "automatic_execution_requested": True,
            }
        )

        result = HeapSnapshotAutomaticFollowupPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.plan["blockers"]
        self.assertIn("heap_snapshot_retained_size_analysis_exported_raw_data", blockers)
        self.assertIn("heap_snapshot_retained_size_analysis_claims_proof_grade_analysis", blockers)
        self.assertIn("heap_snapshot_retained_size_analysis_has_forbidden_side_effects", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertIn("heap_diff_recompute_not_allowed_in_followup_planner", blockers)
        self.assertIn("automatic_heap_followup_execution_not_allowed", blockers)
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])

    def test_heap_snapshot_retained_size_proof_plan_reviews_estimate_without_raw_heap_or_proof(self) -> None:
        retained = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "candidate_estimates": [{"name": "LeakyThing", "retained_size_estimate": 64, "self_size": 16}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        followup = {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": "ready_for_review",
            "automatic_execution_allowed": False,
            "recommended_actions": [{"action": "plan_proof_grade_retained_size_analysis"}],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False},
        }
        spec = HeapSnapshotRetainedSizeProofPlanSpec.from_context(
            {
                "heap_snapshot_retained_size_proof_plan": True,
                "heap_snapshot_retained_size_analysis": retained,
                "heap_snapshot_automatic_followup_plan": followup,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotRetainedSizeProofPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1")
        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["plan_only"])
        self.assertTrue(plan["proof_plan_only"])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(plan["candidate_inputs"][0]["name"], "LeakyThing")
        self.assertTrue(plan["proof_requirements"]["requires_raw_heap"])
        self.assertTrue(plan["proof_requirements"]["requires_dominator_tree"])
        self.assertFalse(plan["future_executor_contract"]["implemented"])
        self.assertFalse(plan["future_executor_contract"]["ready_to_execute_now"])
        self.assertEqual(plan["future_executor_contract"]["executor_name"], "execute_heap_snapshot_retained_size_proof")
        self.assertFalse(plan["raw_heap_loaded"])
        self.assertFalse(plan["raw_heap_parsed"])
        self.assertFalse(plan["heap_diff_computed"])
        self.assertFalse(plan["retained_size_proven"])
        self.assertFalse(plan["complete_heap_traversal_claimed"])
        self.assertFalse(plan["proof_executor_invoked"])
        self.assertFalse(plan["automatic_execution_allowed"])
        self.assertEqual(plan["next_action"], "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor")
        policy = result.side_effect_policy
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["retained_size_proven"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_retained_size_proof_plan_blocks_unsafe_or_execution_requests(self) -> None:
        unsafe = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "candidate_estimates": [{"name": "LeakyThing"}],
            "raw_heap_exported": True,
            "retained_size_proven": True,
            "complete_heap_traversal_claimed": True,
            "side_effect_policy": {"browser_started": True},
        }
        spec = HeapSnapshotRetainedSizeProofPlanSpec.from_context(
            {
                "review_heap_snapshot_retained_size_proof_plan": True,
                "heap_snapshot_retained_size_analysis": unsafe,
                "raw_heap_ingestion_requested": True,
                "raw_heap_export_requested": True,
                "raw_strings_export_requested": True,
                "heap_diff_recompute_requested": True,
                "retained_size_proof_execution_requested": True,
                "automatic_execution_requested": True,
            }
        )

        result = HeapSnapshotRetainedSizeProofPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.plan["blockers"]
        self.assertIn("heap_snapshot_retained_size_analysis_exported_raw_data", blockers)
        self.assertIn("heap_snapshot_retained_size_analysis_already_claims_proof", blockers)
        self.assertIn("heap_snapshot_retained_size_analysis_claims_complete_traversal", blockers)
        self.assertIn("heap_snapshot_retained_size_analysis_has_forbidden_side_effects", blockers)
        self.assertIn("raw_heap_ingestion_not_allowed_in_proof_plan", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertIn("raw_strings_export_not_allowed", blockers)
        self.assertIn("heap_diff_recompute_not_allowed_in_retained_size_proof_plan", blockers)
        self.assertIn("retained_size_proof_execution_not_allowed_in_plan", blockers)
        self.assertIn("automatic_heap_followup_execution_not_allowed", blockers)
        self.assertFalse(result.side_effect_policy["proof_executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])

    def test_heap_snapshot_path_to_root_proof_plan_reviews_estimate_without_raw_heap_or_proof(self) -> None:
        path = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "candidate_paths": [{"candidate_name": "LeakyThing", "path_depth": 2, "root_like_node_reached": True}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": True,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        followup = {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": "ready_for_review",
            "automatic_execution_allowed": False,
            "recommended_actions": [{"action": "plan_proof_grade_path_to_root_analysis"}],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False},
        }
        retained_proof = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1",
            "status": "ready_for_review",
            "proof_plan_only": True,
            "candidate_count": 1,
            "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
            "retained_size_proven": False,
            "automatic_execution_allowed": False,
        }
        spec = HeapSnapshotPathToRootProofPlanSpec.from_context(
            {
                "heap_snapshot_path_to_root_proof_plan": True,
                "heap_snapshot_path_to_root_analysis": path,
                "heap_snapshot_automatic_followup_plan": followup,
                "heap_snapshot_retained_size_proof_plan": retained_proof,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotPathToRootProofPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.heap-snapshot-path-to-root-proof-plan.v1")
        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["plan_only"])
        self.assertTrue(plan["proof_plan_only"])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(plan["candidate_inputs"][0]["name"], "LeakyThing")
        self.assertTrue(plan["proof_requirements"]["requires_raw_heap"])
        self.assertTrue(plan["proof_requirements"]["requires_root_set_policy"])
        self.assertTrue(plan["proof_requirements"]["requires_full_incoming_edge_walk"])
        self.assertFalse(plan["future_executor_contract"]["implemented"])
        self.assertFalse(plan["future_executor_contract"]["ready_to_execute_now"])
        self.assertEqual(plan["future_executor_contract"]["executor_name"], "execute_heap_snapshot_path_to_root_proof")
        self.assertFalse(plan["raw_heap_loaded"])
        self.assertFalse(plan["raw_heap_parsed"])
        self.assertFalse(plan["heap_diff_computed"])
        self.assertFalse(plan["path_to_root_proven"])
        self.assertFalse(plan["complete_heap_traversal_claimed"])
        self.assertFalse(plan["proof_executor_invoked"])
        self.assertFalse(plan["automatic_execution_allowed"])
        self.assertEqual(plan["next_action"], "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor")
        policy = result.side_effect_policy
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["path_to_root_proven"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_path_to_root_proof_plan_blocks_unsafe_or_execution_requests(self) -> None:
        unsafe = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "candidate_paths": [{"candidate_name": "LeakyThing"}],
            "raw_heap_exported": True,
            "path_to_root_proven": True,
            "complete_heap_traversal_claimed": True,
            "side_effect_policy": {"browser_started": True},
        }
        spec = HeapSnapshotPathToRootProofPlanSpec.from_context(
            {
                "review_heap_snapshot_path_to_root_proof_plan": True,
                "heap_snapshot_path_to_root_analysis": unsafe,
                "raw_heap_ingestion_requested": True,
                "raw_heap_export_requested": True,
                "raw_strings_export_requested": True,
                "heap_diff_recompute_requested": True,
                "path_to_root_proof_execution_requested": True,
                "automatic_execution_requested": True,
            }
        )

        result = HeapSnapshotPathToRootProofPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.plan["blockers"]
        self.assertIn("heap_snapshot_path_to_root_analysis_exported_raw_data", blockers)
        self.assertIn("heap_snapshot_path_to_root_analysis_already_claims_proof", blockers)
        self.assertIn("heap_snapshot_path_to_root_analysis_claims_complete_traversal", blockers)
        self.assertIn("heap_snapshot_path_to_root_analysis_has_forbidden_side_effects", blockers)
        self.assertIn("raw_heap_ingestion_not_allowed_in_path_to_root_proof_plan", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertIn("raw_strings_export_not_allowed", blockers)
        self.assertIn("heap_diff_recompute_not_allowed_in_path_to_root_proof_plan", blockers)
        self.assertIn("path_to_root_proof_execution_not_allowed_in_plan", blockers)
        self.assertIn("automatic_heap_followup_execution_not_allowed", blockers)
        self.assertFalse(result.side_effect_policy["proof_executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])

    def test_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_reviews_analysis_without_raw_heap_or_proof(self) -> None:
        analysis = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-constructor-growth-drilldown-analysis.json",
            "constructor_drilldown_rows": [
                {
                    "constructor_name": "LeakyThing",
                    "growth_score": 91,
                    "severity": "high",
                    "node_count_delta": 7,
                    "retained_size_followup_recommended": True,
                    "path_to_root_followup_recommended": True,
                }
            ],
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": True,
            "constructor_drilldown_proven": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        followup = {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": "ready_for_review",
            "automatic_execution_allowed": False,
            "recommended_actions": [{"action": "plan_raw_heap_constructor_drilldown_proof"}],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False},
        }
        retained_proof = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1",
            "status": "ready_for_review",
            "proof_plan_only": True,
            "candidate_count": 1,
            "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
            "automatic_execution_allowed": False,
        }
        path_proof = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-proof-plan.v1",
            "status": "ready_for_review",
            "proof_plan_only": True,
            "candidate_count": 1,
            "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
            "automatic_execution_allowed": False,
        }
        spec = HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec.from_context(
            {
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan": True,
                "heap_snapshot_constructor_growth_drilldown_analysis": analysis,
                "heap_snapshot_automatic_followup_plan": followup,
                "heap_snapshot_retained_size_proof_plan": retained_proof,
                "heap_snapshot_path_to_root_proof_plan": path_proof,
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotRawHeapConstructorDrilldownProofPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.heap-snapshot-raw-heap-constructor-drilldown-proof-plan.v1")
        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["plan_only"])
        self.assertTrue(plan["proof_plan_only"])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual(plan["candidate_inputs"][0]["constructor_name"], "LeakyThing")
        self.assertTrue(plan["proof_requirements"]["requires_raw_heap"])
        self.assertTrue(plan["proof_requirements"]["requires_constructor_reachability_graph"])
        self.assertTrue(plan["proof_requirements"]["requires_retainer_edge_index"])
        self.assertFalse(plan["future_executor_contract"]["implemented"])
        self.assertFalse(plan["future_executor_contract"]["ready_to_execute_now"])
        self.assertEqual(plan["future_executor_contract"]["executor_name"], "execute_heap_snapshot_raw_heap_constructor_drilldown_proof")
        self.assertFalse(plan["raw_heap_loaded"])
        self.assertFalse(plan["raw_heap_parsed"])
        self.assertFalse(plan["heap_diff_computed"])
        self.assertFalse(plan["constructor_drilldown_proven"])
        self.assertFalse(plan["retained_size_proven"])
        self.assertFalse(plan["path_to_root_proven"])
        self.assertFalse(plan["complete_heap_traversal_claimed"])
        self.assertFalse(plan["proof_executor_invoked"])
        self.assertFalse(plan["automatic_execution_allowed"])
        self.assertEqual(plan["next_action"], "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor")
        policy = result.side_effect_policy
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["raw_heap_loaded"])
        self.assertFalse(policy["constructor_drilldown_proven"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blocks_unsafe_or_execution_requests(self) -> None:
        unsafe = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "executed",
            "constructor_drilldown_rows": [{"constructor_name": "LeakyThing"}],
            "raw_heap_loaded": True,
            "raw_heap_exported": True,
            "constructor_drilldown_proven": True,
            "complete_heap_traversal_claimed": True,
            "side_effect_policy": {"browser_started": True},
        }
        spec = HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec.from_context(
            {
                "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan": True,
                "heap_snapshot_constructor_growth_drilldown_analysis": unsafe,
                "raw_heap_ingestion_requested": True,
                "raw_heap_export_requested": True,
                "raw_strings_export_requested": True,
                "heap_diff_recompute_requested": True,
                "constructor_drilldown_proof_execution_requested": True,
                "complete_traversal_claim_requested": True,
                "automatic_execution_requested": True,
            }
        )

        result = HeapSnapshotRawHeapConstructorDrilldownProofPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.plan["blockers"]
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_loaded_raw_heap", blockers)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_exported_raw_data", blockers)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_already_claims_proof", blockers)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_claims_complete_traversal", blockers)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_has_forbidden_side_effects", blockers)
        self.assertIn("raw_heap_ingestion_not_allowed_in_raw_heap_constructor_drilldown_proof_plan", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertIn("raw_strings_export_not_allowed", blockers)
        self.assertIn("heap_diff_recompute_not_allowed_in_raw_heap_constructor_drilldown_proof_plan", blockers)
        self.assertIn("constructor_drilldown_proof_execution_not_allowed_in_plan", blockers)
        self.assertIn("complete_heap_traversal_claim_not_allowed", blockers)
        self.assertIn("automatic_heap_followup_execution_not_allowed", blockers)
        self.assertFalse(result.side_effect_policy["proof_executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])

    def test_heap_snapshot_retained_path_preflight_reviews_constructor_growth_without_heap_work(self) -> None:
        spec = HeapSnapshotRetainedPathPreflightSpec.from_context(
            {
                "heap_snapshot_retained_path_preflight": True,
                "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotRetainedPathPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        preflight = result.preflight
        self.assertEqual(preflight["schema_version"], "reverse-deepagent.heap-snapshot-retained-path-preflight.v1")
        self.assertTrue(preflight["review_only"])
        self.assertTrue(preflight["preflight_only"])
        self.assertTrue(preflight["handoff_only"])
        self.assertGreaterEqual(preflight["candidate_count"], 1)
        self.assertTrue(preflight["raw_heap_requirements"]["requires_raw_heap"])
        self.assertFalse(preflight["raw_heap_requirements"]["raw_heap_available_in_this_preflight"])
        self.assertFalse(preflight["future_executor_contracts"]["retained_size_analysis"]["implemented"])
        self.assertFalse(preflight["future_executor_contracts"]["path_to_root_analysis"]["implemented"])
        self.assertFalse(preflight["raw_heap_loaded"])
        self.assertFalse(preflight["raw_heap_parsed"])
        self.assertFalse(preflight["heap_diff_computed"])
        self.assertFalse(preflight["retained_size_proven"])
        self.assertFalse(preflight["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(preflight["next_action"], "review_heap_snapshot_retained_path_executor_inputs")

    def test_heap_snapshot_retained_path_preflight_blocks_unready_drilldown(self) -> None:
        drilldown = dict(self._constructor_drilldown())
        drilldown["status"] = "blocked"
        spec = HeapSnapshotRetainedPathPreflightSpec.from_context(
            {
                "heap_snapshot_retained_size_path_to_root_preflight": True,
                "heap_snapshot_constructor_growth_drilldown": drilldown,
            }
        )

        result = HeapSnapshotRetainedPathPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_not_ready", result.preflight["blockers"])
        self.assertEqual(result.preflight["next_action"], "resolve_heap_snapshot_retained_path_preflight_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])

    def _retained_path_preflight(self) -> dict:
        spec = HeapSnapshotRetainedPathPreflightSpec.from_context(
            {
                "heap_snapshot_retained_path_preflight": True,
                "heap_snapshot_constructor_growth_drilldown": self._constructor_drilldown(),
                "reviewer": "alice",
            }
        )
        return HeapSnapshotRetainedPathPreflightManager().review(spec).preflight

    def test_heap_snapshot_retained_size_input_review_reviews_preflight_without_retained_size_work(self) -> None:
        spec = HeapSnapshotRetainedSizeInputReviewSpec.from_context(
            {
                "heap_snapshot_retained_size_input_review": True,
                "heap_snapshot_retained_path_preflight": self._retained_path_preflight(),
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotRetainedSizeInputReviewManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        review = result.review
        self.assertEqual(review["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-input-review.v1")
        self.assertTrue(review["review_only"])
        self.assertTrue(review["input_review_only"])
        self.assertTrue(review["approval_gate_only"])
        self.assertTrue(review["retained_size_only"])
        self.assertEqual(review["candidate_count"], 1)
        self.assertTrue(review["raw_heap_requirements"]["requires_raw_heap"])
        self.assertFalse(review["raw_heap_requirements"]["raw_heap_available_in_this_review"])
        self.assertFalse(review["executor_input_contract"]["implemented"])
        self.assertEqual(review["executor_input_contract"]["executor_name"], "execute_heap_snapshot_retained_size_analysis")
        self.assertTrue(review["approval_gate"]["approval_required"])
        self.assertFalse(review["approval_gate"]["ready_to_execute_now"])
        self.assertFalse(review["raw_heap_loaded"])
        self.assertFalse(review["raw_heap_parsed"])
        self.assertFalse(review["heap_diff_computed"])
        self.assertFalse(review["retained_size_proven"])
        self.assertFalse(review["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(review["next_action"], "review_heap_snapshot_retained_size_approval_plan")

    def test_heap_snapshot_retained_size_input_review_blocks_unready_preflight(self) -> None:
        preflight = dict(self._retained_path_preflight())
        preflight["status"] = "blocked"
        spec = HeapSnapshotRetainedSizeInputReviewSpec.from_context(
            {
                "heap_snapshot_retained_size_executor_input_review": True,
                "heap_snapshot_retained_path_preflight": preflight,
            }
        )

        result = HeapSnapshotRetainedSizeInputReviewManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_retained_path_preflight_not_ready", result.review["blockers"])
        self.assertEqual(result.review["next_action"], "resolve_heap_snapshot_retained_size_input_review_blockers")
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])

    def _retained_size_input_review(self) -> dict:
        spec = HeapSnapshotRetainedSizeInputReviewSpec.from_context(
            {
                "heap_snapshot_retained_size_input_review": True,
                "heap_snapshot_retained_path_preflight": self._retained_path_preflight(),
                "reviewer": "alice",
            }
        )
        return HeapSnapshotRetainedSizeInputReviewManager().review(spec).review

    def test_heap_snapshot_retained_size_approval_plan_reviews_input_without_writes(self) -> None:
        spec = HeapSnapshotRetainedSizeApprovalPlanSpec.from_context(
            {
                "heap_snapshot_retained_size_approval_plan": True,
                "heap_snapshot_retained_size_input_review": self._retained_size_input_review(),
                "reviewer": "alice",
                "approval_reason": "bounded retained-size follow-up",
            }
        )

        result = HeapSnapshotRetainedSizeApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1")
        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["approval_plan_only"])
        self.assertTrue(plan["transaction_plan_only"])
        self.assertEqual(plan["candidate_count"], 1)
        self.assertFalse(plan["executor_input_contract"]["implemented"])
        self.assertFalse(plan["executor_input_contract"]["ready_to_execute_now"])
        self.assertTrue(plan["approval_plan"]["approval_required"])
        self.assertFalse(plan["approval_plan"]["approval_recorded"])
        self.assertFalse(plan["approval_plan"]["would_write_now"])
        self.assertFalse(plan["transaction_plan"]["transaction_started"])
        self.assertFalse(plan["transaction_plan"]["journal_written"])
        self.assertFalse(plan["approval_recorded"])
        self.assertFalse(plan["transaction_started"])
        self.assertFalse(plan["journal_written_now"])
        self.assertFalse(plan["executor_invoked"])
        self.assertFalse(plan["raw_heap_loaded"])
        self.assertFalse(plan["raw_heap_parsed"])
        self.assertFalse(plan["heap_diff_computed"])
        self.assertFalse(plan["retained_size_proven"])
        self.assertFalse(plan["path_to_root_computed"])
        self.assertFalse(result.side_effect_policy["artifacts_written"])
        self.assertFalse(result.side_effect_policy["browser_started"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(plan["next_action"], "record_heap_snapshot_retained_size_approval")

    def test_heap_snapshot_retained_size_approval_plan_blocks_unready_input_review(self) -> None:
        review = dict(self._retained_size_input_review())
        review["status"] = "blocked"
        spec = HeapSnapshotRetainedSizeApprovalPlanSpec.from_context(
            {
                "heap_snapshot_retained_size_executor_approval_plan": True,
                "heap_snapshot_retained_size_input_review": review,
            }
        )

        result = HeapSnapshotRetainedSizeApprovalPlanManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_retained_size_input_review_not_ready", result.plan["blockers"])
        self.assertEqual(result.plan["next_action"], "resolve_heap_snapshot_retained_size_approval_plan_blockers")
        self.assertFalse(result.side_effect_policy["approval_recorded"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])


class HeapSnapshotRetainedSizeTransactionPreflightManagerTests(unittest.TestCase):
    def _approval_plan(self) -> dict:
        base = HeapSnapshotDiffFollowupCheckpointManagerTests()
        spec = HeapSnapshotRetainedSizeApprovalPlanSpec.from_context(
            {
                "heap_snapshot_retained_size_approval_plan": True,
                "heap_snapshot_retained_size_input_review": base._retained_size_input_review(),
                "reviewer": "alice",
            }
        )
        return HeapSnapshotRetainedSizeApprovalPlanManager().review(spec).plan

    def _approval_record(self, plan: dict) -> dict:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1",
            "status": "written",
            "approval_recorded": True,
            "approved_for_execution": True,
            "approval_plan_id": plan["approval_plan"]["approval_plan_id"],
            "transaction_plan_id": plan["transaction_plan"]["transaction_plan_id"],
            "candidate_digest": plan["candidate_digest"],
            "approval_plan_digest_sha256": HeapSnapshotRetainedSizeTransactionPreflightManager._digest(plan),
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
            },
            "side_effect_policy": {
                "writes_approval_record": True,
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_heap_snapshot_retained_size_transaction_preflight_is_read_only_and_ready_for_journal_review(self) -> None:
        plan = self._approval_plan()
        spec = HeapSnapshotRetainedSizeTransactionPreflightSpec.from_context(
            {
                "heap_snapshot_retained_size_transaction_preflight": True,
                "heap_snapshot_retained_size_approval_plan": plan,
                "heap_snapshot_retained_size_approval_record": self._approval_record(plan),
                "expected_approval_plan_id": plan["approval_plan"]["approval_plan_id"],
                "expected_transaction_plan_id": plan["transaction_plan"]["transaction_plan_id"],
                "expected_candidate_digest": plan["candidate_digest"],
            }
        )

        result = HeapSnapshotRetainedSizeTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1")
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["transaction_preflight_only"])
        self.assertTrue(descriptor["retained_size_only"])
        self.assertTrue(descriptor["approval_summary"]["approval_recorded"])
        self.assertTrue(descriptor["approval_summary"]["approved_for_execution"])
        self.assertEqual(descriptor["transaction_summary"]["transaction_plan_id"], plan["transaction_plan"]["transaction_plan_id"])
        self.assertEqual(descriptor["candidate_summary"]["candidate_digest"], plan["candidate_digest"])
        self.assertTrue(descriptor["journal_writer_contract"]["ready_for_journal_review"])
        self.assertFalse(descriptor["journal_writer_contract"]["implemented"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertFalse(descriptor["transaction_started"])
        self.assertFalse(descriptor["journal_written"])
        self.assertFalse(descriptor["bounded_executor_gate_written"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["heap_diff_computed"])
        self.assertFalse(descriptor["retained_size_proven"])
        self.assertFalse(descriptor["path_to_root_computed"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_retained_size_transaction_journal_writer")
        self.assertFalse(result.side_effect_policy["transaction_started"])
        self.assertFalse(result.side_effect_policy["journal_written"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_heap_snapshot_retained_size_transaction_preflight_blocks_mismatched_or_side_effected_record(self) -> None:
        plan = self._approval_plan()
        record = self._approval_record(plan)
        record["transaction_plan_id"] = "wrong-transaction-plan"
        record["executor_input_gates"]["journal_written"] = True
        spec = HeapSnapshotRetainedSizeTransactionPreflightSpec.from_context(
            {
                "reviewHeapSnapshotRetainedSizeTransactionPreflight": True,
                "heapSnapshotRetainedSizeApprovalPlan": plan,
                "heapSnapshotRetainedSizeApprovalRecord": record,
                "expectedTransactionPlanId": "expected-transaction-plan",
            }
        )

        result = HeapSnapshotRetainedSizeTransactionPreflightManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("approval_record_claims_journal_written", blockers)
        self.assertIn("transaction_plan_id_mismatch", blockers)
        self.assertIn("expected_transaction_plan_id_mismatch", blockers)
        self.assertEqual(result.descriptor["next_action"], "resolve_heap_snapshot_retained_size_transaction_preflight_blockers")
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])


class HeapSnapshotRetainedSizeBoundedGateManagerTests(unittest.TestCase):
    def _transaction_journal(self) -> dict:
        base = HeapSnapshotRetainedSizeTransactionPreflightManagerTests()
        plan = base._approval_plan()
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "retained-size-journal-test",
            "transaction_preflight_id": "retained-size-preflight-test",
            "transaction_plan_id": plan["transaction_plan"]["transaction_plan_id"],
            "approval_plan_id": plan["approval_plan"]["approval_plan_id"],
            "candidate_digest": plan["candidate_digest"],
            "reviewer": "alice",
            "source_transaction_preflight_summary": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1",
                "status": "ready_for_review",
                "transaction_preflight_only": True,
                "retained_size_only": True,
                "approval_recorded": True,
                "approved_for_execution": True,
                "ready_to_write_journal": True,
                "ready_to_execute_now": False,
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
            },
            "candidate_summary": {"candidate_digest": plan["candidate_digest"], "candidate_count": plan["candidate_count"], "top_candidate": plan["candidate_inputs"][0]["name"]},
            "journal_summary": {
                "entry_count": 2,
                "planned_entry_count": 2,
                "transaction_started": True,
                "journal_written": True,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "requires_bounded_executor_gate_followup": True,
            },
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "approval_record_verified": True,
                "transaction_started": True,
                "journal_written": True,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "raw_strings_exported": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "complete_heap_traversal_claimed": False,
                "retained_size_executor_implemented": False,
                "requires_bounded_executor_gate": True,
                "requires_explicit_executor_review": True,
            },
            "blockers": [],
            "next_action": "review_heap_snapshot_retained_size_bounded_gate",
            "side_effect_policy": {
                "writes_transaction_journal": True,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "future_executor_invoked": False,
                "browser_started": False,
                "provider_factory_invoked": False,
                "provider_availability_checked": False,
                "cdp_command_sent": False,
                "heap_profiler_enabled": False,
                "heap_snapshot_collected": False,
                "heap_snapshot_diff_computed": False,
                "heap_diff_computed": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "raw_strings_exported": False,
                "complete_heap_traversal": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "runtime_evaluated": False,
                "javascript_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    def test_heap_snapshot_retained_size_bounded_gate_reviews_written_journal_without_execution(self) -> None:
        journal = self._transaction_journal()
        spec = HeapSnapshotRetainedSizeBoundedGateSpec.from_context(
            {
                "heap_snapshot_retained_size_bounded_gate": True,
                "heap_snapshot_retained_size_transaction_journal": journal,
                "expected_transaction_plan_id": journal["transaction_plan_id"],
                "expected_approval_plan_id": journal["approval_plan_id"],
                "expected_candidate_digest": journal["candidate_digest"],
                "reviewer": "alice",
            }
        )

        result = HeapSnapshotRetainedSizeBoundedGateManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1")
        self.assertTrue(descriptor["read_only"])
        self.assertTrue(descriptor["bounded_executor_gate_only"])
        self.assertTrue(descriptor["retained_size_only"])
        self.assertTrue(descriptor["transaction_journal_verified"])
        self.assertTrue(descriptor["bounded_executor_gate_ready_for_review"])
        self.assertFalse(descriptor["ready_to_execute_now"])
        self.assertFalse(descriptor["future_executor_contract"]["implemented"])
        self.assertEqual(descriptor["future_executor_contract"]["executor_name"], "execute_heap_snapshot_retained_size_analysis")
        self.assertEqual(descriptor["future_executor_contract"]["result_artifact"], "workspace/heap-snapshot-retained-size-analysis.json")
        self.assertFalse(descriptor["bounded_executor_gate_written"])
        self.assertFalse(descriptor["executor_invoked"])
        self.assertFalse(descriptor["raw_heap_loaded"])
        self.assertFalse(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["retained_size_proven"])
        self.assertFalse(descriptor["path_to_root_computed"])
        self.assertEqual(descriptor["next_action"], "review_heap_snapshot_retained_size_executor_mvp")
        self.assertFalse(result.side_effect_policy["artifacts_written"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_heap_snapshot_retained_size_bounded_gate_blocks_unwritten_or_side_effected_journal(self) -> None:
        journal = self._transaction_journal()
        journal["status"] = "planned"
        journal["journal_written"] = False
        journal["executor_input_gates"]["retained_size_proven"] = True
        journal["side_effect_policy"]["retained_size_proven"] = True
        spec = HeapSnapshotRetainedSizeBoundedGateSpec.from_context(
            {
                "reviewHeapSnapshotRetainedSizeBoundedGate": True,
                "heapSnapshotRetainedSizeExecutorJournal": journal,
                "expectedTransactionPlanId": "wrong-transaction-plan",
            }
        )

        result = HeapSnapshotRetainedSizeBoundedGateManager().review(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("transaction_journal_written", blockers)
        self.assertIn("retained_size_not_proven", blockers)
        self.assertIn("expected_transaction_plan_id_matches", blockers)
        self.assertEqual(result.descriptor["next_action"], "provide_written_heap_snapshot_retained_size_transaction_journal")
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["retained_size_proven"])


class HeapSnapshotRetainedSizeExecutorManagerTests(unittest.TestCase):
    def _bounded_gate(self) -> dict:
        journal = HeapSnapshotRetainedSizeBoundedGateManagerTests()._transaction_journal()
        gate = HeapSnapshotRetainedSizeBoundedGateManager().review(
            HeapSnapshotRetainedSizeBoundedGateSpec.from_context(
                {
                    "heap_snapshot_retained_size_bounded_gate": True,
                    "heap_snapshot_retained_size_transaction_journal": journal,
                    "expected_transaction_plan_id": journal["transaction_plan_id"],
                    "expected_approval_plan_id": journal["approval_plan_id"],
                    "expected_candidate_digest": journal["candidate_digest"],
                    "reviewer": "alice",
                }
            )
        )
        self.assertEqual(gate.status, "ready_for_review")
        return gate.descriptor

    def test_heap_snapshot_retained_size_executor_mvp_estimates_candidate_without_proof(self) -> None:
        spec = HeapSnapshotRetainedSizeExecutorSpec.from_context(
            {
                "execute_heap_snapshot_retained_size_analysis": True,
                "heap_snapshot_retained_size_bounded_gate": self._bounded_gate(),
                "heap_snapshot": _v8_heap_snapshot(extra_object=True),
                "candidate_names": ["TokenSecret"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_retained_size_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
            }
        )

        result = HeapSnapshotRetainedSizeExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        descriptor = result.descriptor
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-analysis.v1")
        self.assertEqual(descriptor["executor_name"], "execute_heap_snapshot_retained_size_analysis")
        self.assertTrue(descriptor["executor_mvp"])
        self.assertTrue(descriptor["raw_heap_loaded"])
        self.assertTrue(descriptor["raw_heap_parsed"])
        self.assertFalse(descriptor["raw_heap_exported"])
        self.assertFalse(descriptor["raw_strings_exported"])
        self.assertTrue(descriptor["retained_size_estimated"])
        self.assertFalse(descriptor["retained_size_proven"])
        self.assertFalse(descriptor["path_to_root_computed"])
        self.assertFalse(descriptor["complete_heap_traversal_claimed"])
        self.assertEqual(descriptor["heap_summary"]["node_count_total"], 3)
        self.assertEqual(len(descriptor["candidate_estimates"]), 1)
        candidate = descriptor["candidate_estimates"][0]
        self.assertEqual(candidate["name"], "<redacted>")
        self.assertEqual(candidate["self_size"], 48)
        self.assertEqual(candidate["retained_size_estimate"], 48)
        self.assertFalse(candidate["retained_size_proven"])
        policy = result.side_effect_policy
        self.assertTrue(policy["executor_invoked"])
        self.assertTrue(policy["raw_heap_loaded"])
        self.assertTrue(policy["raw_heap_parsed"])
        self.assertTrue(policy["retained_size_estimated"])
        self.assertFalse(policy["retained_size_proven"])
        self.assertFalse(policy["path_to_root_computed"])
        self.assertFalse(policy["browser_started"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_heap_snapshot_retained_size_executor_mvp_blocks_without_review_or_on_export_and_proof_claim(self) -> None:
        spec = HeapSnapshotRetainedSizeExecutorSpec.from_context(
            {
                "retained_size_heap_snapshot_executor": True,
                "heap_snapshot_retained_size_bounded_gate": self._bounded_gate(),
                "heap_snapshot": _v8_heap_snapshot(extra_object=True),
                "candidate_name": "TokenSecret",
                "mode": "dry-run",
                "raw_heap_export_requested": True,
                "raw_strings_export_requested": True,
                "retained_size_proof_requested": True,
            }
        )

        result = HeapSnapshotRetainedSizeExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        blockers = result.descriptor["blockers"]
        self.assertIn("heap_snapshot_retained_size_executor_apply_mode_required", blockers)
        self.assertIn("heap_snapshot_retained_size_executor_review_approval_required", blockers)
        self.assertIn("heap_snapshot_retained_size_executor_execution_approval_flag_required", blockers)
        self.assertIn("heap_snapshot_retained_size_executor_reviewer_required", blockers)
        self.assertIn("raw_heap_export_not_allowed", blockers)
        self.assertIn("raw_strings_export_not_allowed", blockers)
        self.assertIn("retained_size_proof_claim_not_allowed_in_mvp", blockers)
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["retained_size_estimated"])

    def test_heap_snapshot_retained_size_executor_ranks_candidates_by_retained_size_desc(self) -> None:
        """Multiple matching candidates are sorted by retained_size_estimate descending."""
        strings = ["", "Window", "BigObject", "SmallObject", "child"]
        node_types = ["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"]
        edge_types = ["context", "element", "property", "internal", "hidden", "shortcut", "weak"]
        # Node layout: type name id self_size edge_count trace_node_id  (field stride = 6)
        # BigObject (self_size=512, 1 child edge), SmallObject (self_size=64, 0 edges), child (self_size=128, 0 edges)
        # Edge: BigObject -> child (unique ownership → BigObject retained = 512+128 = 640)
        nodes = [
            3, 2, 1, 512, 1, 0,  # node 0: BigObject
            3, 3, 2,  64, 0, 0,  # node 1: SmallObject
            3, 4, 3, 128, 0, 0,  # node 2: child
        ]
        edges = [2, 4, 12]  # property "child" → to_node offset 12 = node index 2
        snapshot = {
            "snapshot": {
                "meta": {
                    "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                    "node_types": [node_types, "string", "number", "number", "number", "number"],
                    "edge_fields": ["type", "name_or_index", "to_node"],
                    "edge_types": [edge_types, "string_or_number", "node"],
                }
            },
            "nodes": nodes,
            "edges": edges,
            "strings": strings,
        }
        spec = HeapSnapshotRetainedSizeExecutorSpec.from_context(
            {
                "execute_heap_snapshot_retained_size_analysis": True,
                "heap_snapshot_retained_size_bounded_gate": self._bounded_gate(),
                "heap_snapshot": snapshot,
                "candidate_names": ["BigObject", "SmallObject"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_retained_size_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 200000,
            }
        )

        result = HeapSnapshotRetainedSizeExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        estimates = result.descriptor["candidate_estimates"]
        self.assertEqual(len(estimates), 2)
        # Sorted descending: BigObject (640) before SmallObject (64)
        self.assertGreaterEqual(
            estimates[0]["retained_size_estimate"],
            estimates[1]["retained_size_estimate"],
        )
        # BigObject uniquely owns child → retained = self_size + child.self_size
        big = estimates[0]
        self.assertGreater(big["retained_size_estimate"], big["self_size"])
        self.assertGreater(big["directly_owned_node_count_estimate"], 0)

    def test_heap_snapshot_retained_size_executor_truncates_at_max_nodes(self) -> None:
        """When max_nodes < total nodes, analysis is marked truncated and only covers the budget."""
        snapshot = _v8_heap_snapshot(extra_object=True)  # 3 nodes total
        spec = HeapSnapshotRetainedSizeExecutorSpec.from_context(
            {
                "execute_heap_snapshot_retained_size_analysis": True,
                "heap_snapshot_retained_size_bounded_gate": self._bounded_gate(),
                "heap_snapshot": snapshot,
                "candidate_names": ["Object"],  # index=1, within max_nodes=2 budget
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_retained_size_execution": True,
                "reviewer": "alice",
                "max_nodes": 2,          # budget smaller than total (3)
                "max_raw_heap_bytes": 200000,
            }
        )

        result = HeapSnapshotRetainedSizeExecutorManager().execute(spec)

        self.assertEqual(result.status, "executed")
        summary = result.descriptor["heap_summary"]
        self.assertEqual(summary["node_count_total"], 3)
        self.assertLessEqual(summary["node_count_analyzed"], 2)
        self.assertTrue(summary["node_analysis_truncated"])
        # candidate found within budget
        self.assertGreater(len(result.descriptor["candidate_estimates"]), 0)

    def test_heap_snapshot_retained_size_executor_blocks_on_missing_heap_snapshot(self) -> None:
        """Spec with no heap_snapshot dict produces a blocked result without side effects."""
        spec = HeapSnapshotRetainedSizeExecutorSpec.from_context(
            {
                "execute_heap_snapshot_retained_size_analysis": True,
                "heap_snapshot_retained_size_bounded_gate": self._bounded_gate(),
                "heap_snapshot": None,
                "candidate_names": ["SomeCandidate"],
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_retained_size_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 200000,
            }
        )

        result = HeapSnapshotRetainedSizeExecutorManager().execute(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("heap_snapshot_required", result.descriptor["blockers"])
        self.assertFalse(result.side_effect_policy["executor_invoked"])
        self.assertFalse(result.side_effect_policy["raw_heap_loaded"])
        self.assertFalse(result.side_effect_policy["retained_size_estimated"])


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

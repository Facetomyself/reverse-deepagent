import unittest

from reverse_deepagent.browser.hooks import SourceLogpointManager, SourceLogpointSpec
from tests.test_source_maps import encode_vlq_segment


class SourceLogpointPage:
    def __init__(self) -> None:
        self.installed = False
        self.events = []
        self.session = SourceLogpointCDP(self)
        self.set_breakpoint_params = {}
        self.logpoint_id = "smoke-logpoint"
        self.url_pattern = ".*app\\.js$"
        self.line_number = 7
        self.column_number = 0
        self.label = "smoke"
        self.pause_on_hit = False

    def evaluate(self, expression):
        if "__reverseDeepAgentSourceLogpoints" in expression and "installed: [{" in expression:
            self.installed = True
            return {
                "ok": True,
                "installed": [
                    {
                        "logpointId": self.logpoint_id,
                        "urlPattern": self.url_pattern,
                        "lineNumber": self.line_number,
                        "columnNumber": self.column_number,
                        "label": self.label,
                        "pauseOnHit": self.pause_on_hit,
                    }
                ],
                "missing": [],
                "eventCount": len(self.events),
            }
        if "__reverseDeepAgentSourceLogpoints" in expression and "eventCount" in expression:
            return {"ok": self.installed, "events": list(self.events), "eventCount": len(self.events), "installed": {self.logpoint_id: self.installed}}
        raise AssertionError(f"unexpected expression: {expression}")

    def cdp_session(self):
        return self.session


class SourceLogpointCDP:
    def __init__(self, owner: SourceLogpointPage) -> None:
        self.owner = owner
        self.handlers = {}
        self.calls = []

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Debugger.enable":
            return {}
        if method == "Debugger.setBreakpointByUrl":
            self.owner.set_breakpoint_params = params or {}
            return {"breakpointId": "bp-logpoint-1", "locations": [{"scriptId": "script-1", "lineNumber": params.get("lineNumber", 0)}]}
        if method == "Runtime.evaluate":
            if self.owner.installed:
                self.owner.events.append(
                    {
                        "type": "source_logpoint",
                        "payload": {
                            "logpointId": self.owner.logpoint_id,
                            "urlPattern": self.owner.url_pattern,
                            "lineNumber": self.owner.line_number,
                            "columnNumber": self.owner.column_number,
                            "label": self.owner.label,
                            "pauseOnHit": self.owner.pause_on_hit,
                            "ok": True,
                            "value": {"type": "string", "preview": "sig-demo"},
                            "error": None,
                        },
                    }
                )
            return {"result": {"type": "string", "value": "scheduled"}}
        if method == "Debugger.resume":
            return {}
        return {}


class SourceLogpointManagerTests(unittest.TestCase):
    def test_from_context_remaps_bundle_offset_to_generated_location(self) -> None:
        spec = SourceLogpointSpec.from_context(
            {
                "url_pattern": ".*bundle\\.js$",
                "line_number": 99,
                "column_number": 9,
                "bundle_source": "alpha\nbeta\ngamma",
                "bundle_offset": 6,
                "log_expression": "raw",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.line_number, 1)
        self.assertEqual(spec.column_number, 0)
        self.assertEqual(spec.remap["status"], "success")
        self.assertEqual(spec.remap["strategy"], "bundle_offset")
        self.assertEqual(spec.remap["requested"], {"line_number": 99, "column_number": 9})
        self.assertEqual(spec.remap["generated"]["line_number"], 1)
        self.assertEqual(spec.remap["generated"]["column_number"], 0)

    def test_from_context_remaps_source_map_original_location(self) -> None:
        spec = SourceLogpointSpec.from_context(
            {
                "url_pattern": ".*bundle\\.js$",
                "line_number": 99,
                "column_number": 9,
                "source_map": {"version": 3, "sources": ["src/app.js"], "names": [], "mappings": "AAAA"},
                "original_source": "src/app.js",
                "original_line": 0,
                "original_column": 0,
                "log_expression": "raw",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.line_number, 0)
        self.assertEqual(spec.column_number, 0)
        self.assertEqual(spec.remap["status"], "success")
        self.assertEqual(spec.remap["strategy"], "source_map_exact")

    def test_from_context_remaps_source_map_with_bias(self) -> None:
        source_map = {
            "version": 3,
            "sources": ["src/app.js"],
            "names": [],
            "mappings": f"{encode_vlq_segment([0, 0, 0, 0])},{encode_vlq_segment([10, 0, 0, 5])}",
        }
        spec = SourceLogpointSpec.from_context(
            {
                "url_pattern": ".*bundle\\.js$",
                "line_number": 99,
                "column_number": 9,
                "source_map": source_map,
                "original_source": "src/app.js",
                "original_line": 0,
                "original_column": 7,
                "log_expression": "raw",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.line_number, 0)
        self.assertEqual(spec.column_number, 10)
        self.assertEqual(spec.remap["status"], "success")
        self.assertEqual(spec.remap["strategy"], "source_map_bias_glb")
        self.assertEqual(spec.remap["generated"]["metadata"]["matched_original_column_number"], 5)

    def test_install_and_snapshot_source_logpoint(self) -> None:
        page = SourceLogpointPage()
        manager = SourceLogpointManager()
        spec = SourceLogpointSpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 7,
                "column_number": 0,
                "log_expression": "window.buildSign('sign', 1700000000000)",
                "label": "smoke",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            }
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        result = manager.install(page, spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.breakpoints[0]["breakpointId"], "bp-logpoint-1")
        self.assertEqual(result.events[0]["type"], "source_logpoint")
        self.assertEqual(result.trigger["ok"], True)
        self.assertEqual(result.trigger["result"]["result"]["value"], "scheduled")
        self.assertEqual(page.set_breakpoint_params["condition"].count("source_logpoint"), 1)
        self.assertIn("return false", page.set_breakpoint_params["condition"])

    def test_install_uses_remapped_location_for_breakpoint(self) -> None:
        page = SourceLogpointPage()
        manager = SourceLogpointManager()
        spec = SourceLogpointSpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 99,
                "column_number": 9,
                "bundle_source": "alpha\nbeta\ngamma",
                "bundle_offset": 6,
                "log_expression": "window.buildSign('sign', 1700000000000)",
                "label": "smoke",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        result = manager.install(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(page.set_breakpoint_params["lineNumber"], 1)
        self.assertEqual(page.set_breakpoint_params["columnNumber"], 0)
        self.assertEqual(result.remap["status"], "success")
        self.assertEqual(result.remap["strategy"], "bundle_offset")
        self.assertIn('"remap"', page.set_breakpoint_params["condition"])


if __name__ == "__main__":
    unittest.main()

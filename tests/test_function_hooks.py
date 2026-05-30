import unittest

from reverse_deepagent.browser.hooks import FunctionHookManager, FunctionHookSpec


class FunctionHookPage:
    def __init__(self) -> None:
        self.installed = False
        self.events = []

    def evaluate(self, expression):
        if "__reverseDeepAgentHooks" in expression and "function_hooks" in expression and "functionPaths" in expression:
            self.installed = True
            return {
                "ok": True,
                "installed": [{"path": "window.buildSign", "functionName": "buildSign", "candidateId": "script-1:buildSign"}],
                "missing": [],
                "eventCount": len(self.events),
            }
        if "__reverseDeepAgentHooks" in expression and "function_" in expression and "eventCount" in expression:
            return {"ok": True, "events": list(self.events), "eventCount": len(self.events), "installed": {"window.buildSign": True}}
        if "window.buildSign" in expression and "functionPaths" not in expression:
            if self.installed:
                self.events.append({"type": "function_call", "payload": {"path": "window.buildSign", "functionName": "buildSign", "argCount": 2}})
                self.events.append({"type": "function_return", "payload": {"path": "window.buildSign", "functionName": "buildSign", "result": {"type": "string", "preview": "sig-demo"}}})
            return "sig-demo"
        raise AssertionError(f"unexpected expression: {expression}")


class FunctionHookManagerTests(unittest.TestCase):
    def test_install_and_snapshot_function_hook(self) -> None:
        page = FunctionHookPage()
        manager = FunctionHookManager()
        spec = FunctionHookSpec.from_context(
            {
                "function_name": "buildSign",
                "function_paths": ["window.buildSign"],
                "candidate_id": "script-1:buildSign",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            }
        )
        self.assertIsNotNone(spec)
        assert spec is not None
        result = manager.install(page, spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.installed[0]["path"], "window.buildSign")
        self.assertEqual(result.events[0]["type"], "function_call")
        self.assertEqual(result.trigger["ok"], True)
        self.assertEqual(result.trigger["result"]["value"], "sig-demo")

    def test_from_context_defaults_candidate_paths(self) -> None:
        spec = FunctionHookSpec.from_context({"functionName": "buildSign"})
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertIn("window.buildSign", spec.function_paths)
        self.assertIn("window.reverseFixture.buildSign", spec.function_paths)

    def test_missing_function_name_is_unsupported(self) -> None:
        self.assertIsNone(FunctionHookSpec.from_context({}))


if __name__ == "__main__":
    unittest.main()

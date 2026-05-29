import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from reverse_deepagent.adapters.native_web import NativeWebRuntime
from reverse_deepagent.browser import BrowserPageRef, BrowserProviderCapabilities, PlaywrightBrowserPageAdapter
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline


class FakeRawPage:
    def __init__(self, context) -> None:
        self.context = context
        self.url = "about:blank"
        self.handlers = {}

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event, payload):
        for handler in self.handlers.get(event, []):
            handler(payload)

    def goto(self, url, **kwargs):
        self.url = url
        request = FakeRequest(url.rstrip("/") + "/api/search")
        self.emit("request", request)
        self.emit("response", FakeResponse(request))

    def title(self):
        return "Native Fixture"

    def content(self):
        return """
        <html>
          <head><script src="/assets/app.js"></script></head>
          <body><script>function buildSign(){ return "x-sign"; }</script></body>
        </html>
        """

    def evaluate(self, expression):
        return {
            "cookie": "",
            "localStorage": {"demo": "1"},
            "sessionStorage": {},
            "navigator": {"userAgent": "fake-native", "webdriver": False},
            "timezoneOffset": 0,
        }

    def screenshot(self, **kwargs):
        return b"png"


class FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url
        self.method = "GET"
        self.resource_type = "xhr"
        self.headers = {}


class FakeResponse:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.status = 200
        self.ok = True
        self.headers = {"content-type": "application/json"}


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakeRawPage(self)]
        self.closed = False

    def new_page(self):
        page = FakeRawPage(self)
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeSession:
    provider_id = "fake-native"

    def __init__(self) -> None:
        self.context = FakeContext()

    def list_pages(self):
        return [BrowserPageRef(page_id=str(index), url=page.url, title=page.title(), selected=index == 0) for index, page in enumerate(self.context.pages)]

    def new_page(self, url=None):
        page = PlaywrightBrowserPageAdapter(self.context.new_page())
        if url:
            page.goto(url)
        return page

    def get_active_page(self):
        return PlaywrightBrowserPageAdapter(self.context.pages[0])

    def close(self):
        self.context.close()


class FakeProvider:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = False
        self.session = FakeSession()

    def describe(self):
        return BrowserProviderCapabilities(
            provider_id="fake-native",
            display_name="Fake Native Browser",
            engine="chromium",
            transport="fake",
            supports_launch=True,
            supports_playwright_api=True,
            supports_network_events=True,
            supports_runtime_eval=True,
            managed_browser=True,
        )

    def start(self):
        self.started += 1
        return self.session

    def connect(self):
        return self.start()

    def stop(self):
        self.stopped = True

    def is_available(self):
        return True


class NativeWebRuntimeTests(unittest.TestCase):
    def test_registry_lists_native_web_without_starting_playwright(self) -> None:
        metadata = {item["backend_id"]: item for item in list_runtime_backends()}
        self.assertIn("native-web", metadata)
        self.assertFalse(metadata["native-web"]["mcp_backed"])
        self.assertEqual(metadata["native-web"]["config"]["default_browser_provider"], "playwright-chromium")

        runtime = build_runtime("native-web")
        capabilities = runtime.describe_capabilities().model_dump(mode="json")
        self.assertEqual(capabilities["backend_id"], "native-web")
        self.assertEqual(capabilities["config"]["provider"]["provider_id"], "playwright-chromium")

    def test_native_web_runtime_pipeline_writes_core_artifacts_without_mcp(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.test/app 找 buildSign 入口",
                artifact_root=Path(tmpdir),
                runtime_kind="native-web",
                runtime=runtime,
            )
            artifacts = output.artifacts
            self.assertEqual(output.final_result.status.value, "success")
            self.assertEqual(output.final_result.next_action, "move_to_source_analysis")
            self.assertIn("workspace_network_requests", artifacts)
            self.assertIn("workspace_source_hits", artifacts)
            self.assertIn("workspace_runtime_context", artifacts)
            self.assertIn("workspace_dom_snapshot", artifacts)
            self.assertIn("workspace_script_inventory", artifacts)
            self.assertIn("workspace_console_messages", artifacts)
            self.assertIn("workspace_navigation_events", artifacts)
            network = json.loads(Path(artifacts["workspace_network_requests"]).read_text(encoding="utf-8"))
            source_hits = json.loads(Path(artifacts["workspace_source_hits"]).read_text(encoding="utf-8"))
            runtime_context = json.loads(Path(artifacts["workspace_runtime_context"]).read_text(encoding="utf-8"))
            dom_snapshot = json.loads(Path(artifacts["workspace_dom_snapshot"]).read_text(encoding="utf-8"))
            script_inventory = json.loads(Path(artifacts["workspace_script_inventory"]).read_text(encoding="utf-8"))
            console_messages = json.loads(Path(artifacts["workspace_console_messages"]).read_text(encoding="utf-8"))
            navigation_events = json.loads(Path(artifacts["workspace_navigation_events"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))

        self.assertEqual(provider.started, 1)
        self.assertEqual(network["count"], 1)
        self.assertEqual(source_hits["count"], 1)
        self.assertTrue(runtime_context["ok"])
        self.assertGreater(dom_snapshot["html_size"], 0)
        self.assertEqual(script_inventory["count"], 2)
        self.assertEqual(console_messages["count"], 0)
        self.assertEqual(navigation_events["events"], ["navigated:https://example.test/app"])
        manifest_by_key = {entry["artifact_key"]: entry for entry in manifest["entries"]}
        self.assertEqual(manifest_by_key["workspace_dom_snapshot"]["metadata"]["browser_provider"], "fake-native")
        self.assertEqual(manifest_by_key["workspace_script_inventory"]["category"], "source")
        self.assertEqual(manifest_by_key["workspace_navigation_events"]["category"], "trace")


if __name__ == "__main__":
    unittest.main()

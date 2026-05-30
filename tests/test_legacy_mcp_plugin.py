import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.runtime.legacy_mcp import (
    LEGACY_MCP_ALIASES,
    LEGACY_MCP_BACKEND_ID,
    LegacyMcpPluginUnavailableError,
    create_legacy_mcp_runtime,
    is_legacy_mcp_runtime_kind,
    legacy_mcp_install_guidance,
    legacy_mcp_alias_warning,
    legacy_mcp_backend_registration,
)


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-legacy-mcp" / "src"


class LegacyMcpPluginTests(unittest.TestCase):
    def test_core_shim_reports_missing_optional_plugin_when_unavailable(self) -> None:
        with patch("reverse_deepagent.runtime.legacy_mcp._plugin_module", return_value=None):
            with self.assertRaisesRegex(LegacyMcpPluginUnavailableError, "reverse-deepagent-legacy-mcp"):
                legacy_mcp_backend_registration()
            with self.assertRaisesRegex(LegacyMcpPluginUnavailableError, "reverse-deepagent-legacy-mcp"):
                create_legacy_mcp_runtime()

    def test_legacy_mcp_install_guidance_points_to_optional_package(self) -> None:
        guidance = legacy_mcp_install_guidance()
        self.assertEqual(guidance["backend_id"], "legacy-mcp")
        self.assertEqual(guidance["package"], "reverse-deepagent-legacy-mcp")
        self.assertEqual(guidance["preferred_web_runtime"], "native-web")
        self.assertIn("reverse_deepagent.runtime_backends", guidance["entry_point_group"])
        self.assertIn("uv pip install", guidance["install_hint"])

    def test_core_shim_prefers_optional_plugin_when_available(self) -> None:
        sys.path.insert(0, str(PACKAGE_SRC))
        try:
            sys.modules.pop("reverse_deepagent_legacy_mcp", None)
            registration = legacy_mcp_backend_registration()
        finally:
            sys.modules.pop("reverse_deepagent_legacy_mcp", None)
            sys.path.remove(str(PACKAGE_SRC))
        self.assertEqual(registration.backend_id, "legacy-mcp")
        self.assertEqual(registration.aliases, LEGACY_MCP_ALIASES)
        self.assertEqual(registration.capabilities.backend_id, LEGACY_MCP_BACKEND_ID)
        self.assertEqual(registration.capabilities.transport, "mcp-stdio")
        self.assertTrue(registration.capabilities.mcp_backed)
        self.assertEqual(registration.capabilities.config["package"], "reverse-deepagent-legacy-mcp")
        self.assertIn("mcp", registration.capabilities.config["aliases"])
        self.assertTrue(callable(registration.factory))
        self.assertNotIn("compat_fallback", registration.capabilities.config)

    def test_legacy_mcp_alias_helpers_are_self_contained(self) -> None:
        self.assertTrue(is_legacy_mcp_runtime_kind("legacy-mcp"))
        self.assertTrue(is_legacy_mcp_runtime_kind("mcp"))
        self.assertTrue(is_legacy_mcp_runtime_kind("jsreverser-mcp"))
        self.assertFalse(is_legacy_mcp_runtime_kind("native-web"))
        self.assertIsNone(legacy_mcp_alias_warning("legacy-mcp"))
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("mcp") or "")


if __name__ == "__main__":
    unittest.main()

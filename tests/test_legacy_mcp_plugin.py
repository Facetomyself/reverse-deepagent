import unittest

from reverse_deepagent.runtime.legacy_mcp import (
    LEGACY_MCP_ALIASES,
    LEGACY_MCP_BACKEND_ID,
    is_legacy_mcp_runtime_kind,
    legacy_mcp_alias_warning,
    legacy_mcp_backend_registration,
)


class LegacyMcpPluginTests(unittest.TestCase):
    def test_legacy_mcp_registration_is_entry_point_ready(self) -> None:
        registration = legacy_mcp_backend_registration()
        self.assertEqual(registration.backend_id, LEGACY_MCP_BACKEND_ID)
        self.assertEqual(registration.aliases, LEGACY_MCP_ALIASES)
        self.assertEqual(registration.capabilities.backend_id, LEGACY_MCP_BACKEND_ID)
        self.assertEqual(registration.capabilities.transport, "mcp-stdio")
        self.assertTrue(registration.capabilities.mcp_backed)
        self.assertIn("mcp", registration.capabilities.config["aliases"])
        self.assertTrue(callable(registration.factory))

    def test_legacy_mcp_alias_helpers_are_self_contained(self) -> None:
        self.assertTrue(is_legacy_mcp_runtime_kind("legacy-mcp"))
        self.assertTrue(is_legacy_mcp_runtime_kind("mcp"))
        self.assertTrue(is_legacy_mcp_runtime_kind("jsreverser-mcp"))
        self.assertFalse(is_legacy_mcp_runtime_kind("native-web"))
        self.assertIsNone(legacy_mcp_alias_warning("legacy-mcp"))
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("mcp") or "")


if __name__ == "__main__":
    unittest.main()

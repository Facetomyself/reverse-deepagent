import importlib
import sys
import tomllib
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-legacy-mcp"


class LegacyMcpPluginPackageTests(unittest.TestCase):
    def test_package_declares_runtime_backend_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-legacy-mcp")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.runtime_backends"]
        self.assertEqual(entry_points["legacy-mcp"], "reverse_deepagent_legacy_mcp:runtime_backend_registration")
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_entry_point_function_returns_legacy_mcp_registration_without_starting_runtime(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_legacy_mcp")
            registration = module.runtime_backend_registration()
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_legacy_mcp", None)
        self.assertEqual(registration.backend_id, "legacy-mcp")
        self.assertEqual(registration.capabilities.transport, "mcp-stdio")
        self.assertTrue(registration.capabilities.mcp_backed)
        self.assertTrue(callable(registration.factory))


if __name__ == "__main__":
    unittest.main()

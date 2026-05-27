#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reverse_deepagent.runtime.mcp_stdio import StdioMcpBridge


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe jsreverser-mcp over stdio.")
    parser.add_argument("--command", default="/opt/homebrew/bin/jsreverser-mcp")
    parser.add_argument("--browser-url", default="http://127.0.0.1:9222")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / "artifacts/exports/jsreverser-mcp-probe.json"))
    args = parser.parse_args()
    command = [
        args.command,
        "--browserUrl",
        args.browser_url,
    ]
    with StdioMcpBridge(command=command, request_timeout=20.0, startup_timeout=20.0) as bridge:
        init_result = bridge.initialize()
        tools_result = bridge.list_tools()
        summary = {
            "protocolVersion": init_result.get("protocolVersion"),
            "tool_count": len(tools_result.get("tools", [])),
            "tool_names_sample": [tool.get("name") for tool in tools_result.get("tools", [])[:20]],
            "stderr_tail": bridge.get_stderr().splitlines()[-10:],
        }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

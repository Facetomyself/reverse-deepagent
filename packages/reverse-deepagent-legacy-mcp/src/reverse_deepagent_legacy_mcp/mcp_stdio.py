from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MCP_PROTOCOL_VERSION = "2025-03-26"
JSONRPC_VERSION = "2.0"


class McpBridgeError(RuntimeError):
    """Base error for stdio MCP bridge failures."""


class McpTimeoutError(McpBridgeError):
    """Raised when waiting for an MCP response times out."""


class McpProtocolError(McpBridgeError):
    """Raised when the MCP peer sends malformed or error responses."""


@dataclass(slots=True)
class StdioMcpBridge:
    """Minimal synchronous MCP stdio client for local runtime integrations.

    The local `jsreverser-mcp` stdio transport emits newline-delimited JSON-RPC
    messages, so this bridge intentionally writes and reads one JSON object per
    line instead of using Content-Length frames.
    """

    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None
    protocol_version: str = DEFAULT_MCP_PROTOCOL_VERSION
    request_timeout: float = 30.0
    startup_timeout: float = 15.0
    _proc: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _id_counter: int = field(default=0, init=False, repr=False)
    _write_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _pending: dict[int, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _pending_events: dict[int, threading.Event] = field(default_factory=dict, init=False, repr=False)
    _reader_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stderr_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stderr_lines: list[str] = field(default_factory=list, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def start(self) -> None:
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, name="mcp-stdout-reader", daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, name="mcp-stderr-reader", daemon=True)
        self._stderr_thread.start()
        self.initialize()

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            for stream_name in ("stdout", "stderr"):
                try:
                    stream = getattr(proc, stream_name)
                    if stream and not stream.closed:
                        stream.close()
                except Exception:
                    pass
            self._proc = None
            self._initialized = False

    def __enter__(self) -> "StdioMcpBridge":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {"protocolVersion": self.protocol_version}
        self._ensure_process()
        result = self._send_request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "reverse-deepagent",
                    "version": "0.1.0",
                },
            },
            timeout=self.startup_timeout,
        )
        self._send_notification("notifications/initialized", {})
        self._initialized = True
        return result

    def list_tools(self) -> dict[str, Any]:
        self._ensure_ready()
        return self._send_request("tools/list", {})

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        self._ensure_ready()
        result = self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": params,
            },
        )
        if isinstance(result, dict) and "content" in result:
            return self._normalize_tool_result(result)
        return result

    def get_stderr(self) -> str:
        return "".join(self._stderr_lines)

    def _ensure_process(self) -> None:
        if self._proc is None:
            self.start()

    def _ensure_ready(self) -> None:
        if self._proc is None:
            self.start()
        if not self._initialized:
            self.initialize()

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    def _send_request(self, method: str, params: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        request_id = self._next_id()
        event = threading.Event()
        self._pending_events[request_id] = event
        self._write_message(
            {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        if not event.wait(timeout or self.request_timeout):
            raise McpTimeoutError(f"Timed out waiting for MCP response: {method}")
        payload = self._pending.pop(request_id, None)
        self._pending_events.pop(request_id, None)
        if payload is None:
            raise McpProtocolError(f"No MCP payload captured for request id {request_id}")
        if "error" in payload:
            raise McpProtocolError(f"MCP error for {method}: {payload['error']}")
        return payload.get("result", {})

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        self._write_message(
            {
                "jsonrpc": JSONRPC_VERSION,
                "method": method,
                "params": params,
            }
        )

    def _write_message(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise McpBridgeError("MCP process is not running")
        body = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            proc.stdin.write(body)
            proc.stdin.flush()

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        stream = proc.stdout
        try:
            while True:
                line = stream.readline()
                if not line:
                    return
                message = json.loads(line.decode("utf-8"))
                self._handle_message(message)
        except Exception as exc:
            self._stderr_lines.append(f"[bridge-reader-error] {exc}\n")

    def _stderr_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        while True:
            chunk = proc.stderr.readline()
            if not chunk:
                return
            try:
                self._stderr_lines.append(chunk.decode("utf-8", errors="ignore"))
            except Exception:
                self._stderr_lines.append(repr(chunk) + "\n")

    def _handle_message(self, message: dict[str, Any]) -> None:
        if "id" in message:
            request_id = message["id"]
            self._pending[request_id] = message
            event = self._pending_events.get(request_id)
            if event:
                event.set()
            return
        # Notifications are currently just ignored, but retained for debugging if needed.
        if message.get("method"):
            self._stderr_lines.append(f"[mcp-notification] {json.dumps(message, ensure_ascii=False)}\n")

    @staticmethod
    def _normalize_tool_result(result: dict[str, Any]) -> Any:
        content = result.get("content")
        if not isinstance(content, list):
            return result
        text_chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_chunks.append(item["text"])
        if not text_chunks:
            return result
        joined = "\n".join(text_chunks).strip()
        try:
            return json.loads(joined)
        except Exception:
            return {"content": content, "text": joined}

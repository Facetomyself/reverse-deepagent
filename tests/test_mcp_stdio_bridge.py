import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from reverse_deepagent.runtime.mcp_stdio import StdioMcpBridge


class McpStdioBridgeTests(unittest.TestCase):
    def test_bridge_can_initialize_and_call_fake_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            server_path = Path(tmpdir) / "fake_mcp_server.py"
            server_path.write_text(
                textwrap.dedent(
                    '''
                    import json
                    import sys

                    def write_message(message):
                        sys.stdout.write(json.dumps(message) + '\\n')
                        sys.stdout.flush()

                    for line in sys.stdin:
                        message = json.loads(line)
                        if message.get('method') == 'initialize':
                            write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'serverInfo': {'name': 'fake', 'version': '0.1'}}})
                        elif message.get('method') == 'tools/list':
                            write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'tools': [{'name': 'ping', 'description': 'ping tool'}]}})
                        elif message.get('method') == 'tools/call':
                            write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': [{'type': 'text', 'text': json.dumps({'ok': True, 'name': message['params']['name'], 'arguments': message['params']['arguments']})}]}})
                        elif message.get('method') == 'notifications/initialized':
                            continue
                    '''
                ),
                encoding='utf-8',
            )
            bridge = StdioMcpBridge(command=[os.environ.get('PYTHON_FOR_TEST', 'python3'), str(server_path)])
            with bridge:
                tools = bridge.list_tools()
                payload = bridge.invoke('ping', {'hello': 'world'})
            self.assertEqual(tools['tools'][0]['name'], 'ping')
            self.assertEqual(payload['name'], 'ping')
            self.assertEqual(payload['arguments']['hello'], 'world')


if __name__ == '__main__':
    unittest.main()

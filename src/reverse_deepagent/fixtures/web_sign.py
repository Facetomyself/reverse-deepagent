from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


class FixtureProfile(str, Enum):
    DEFAULT = "default"
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    BASE64 = "base64"
    CONTEXT_LOCALSTORAGE = "context-localstorage"
    CONTEXT_COOKIE = "context-cookie"
    CONTEXT_NAVIGATOR = "context-navigator"
    WEBPACK_MINIFIED = "webpack-minified"
    TOKEN_CHAIN = "token-chain"
    HYBRID_CONTEXT = "hybrid-context"


FIXTURE_PROFILE_VALUES = [item.value for item in FixtureProfile]

FIXTURE_BOOTSTRAP_TOKEN = "fixture-token"
FIXTURE_HYBRID_NONCE = "fixture-nonce"
FIXTURE_HYBRID_CSRF = "fixture-csrf"


def _profile_metadata(profile: FixtureProfile) -> dict[str, Any]:
    metadata: dict[FixtureProfile, dict[str, Any]] = {
        FixtureProfile.DEFAULT: {
            "family": "deterministic",
            "description": "Simple deterministic reducer for baseline smoke.",
            "expected_strategy": "fixture_seed_mod100000",
            "realism": ["plain-source"],
        },
        FixtureProfile.MD5: {
            "family": "hash",
            "description": "MD5 keyword/timestamp flow.",
            "expected_strategy": "md5_keyword_timestamp",
            "realism": ["plain-source", "legacy-hash"],
        },
        FixtureProfile.SHA1: {
            "family": "hash",
            "description": "WebCrypto SHA-1 keyword/timestamp flow.",
            "expected_strategy": "sha1_keyword_timestamp",
            "realism": ["webcrypto"],
        },
        FixtureProfile.SHA256: {
            "family": "hash",
            "description": "WebCrypto SHA-256 keyword/timestamp flow.",
            "expected_strategy": "sha256_keyword_timestamp",
            "realism": ["webcrypto"],
        },
        FixtureProfile.BASE64: {
            "family": "encoding",
            "description": "Base64 keyword/timestamp flow.",
            "expected_strategy": "base64_keyword_timestamp",
            "realism": ["browser-encoding"],
        },
        FixtureProfile.CONTEXT_LOCALSTORAGE: {
            "family": "runtime-context",
            "description": "Base64 flow that depends on localStorage.device_id.",
            "expected_strategy": "base64_keyword_timestamp",
            "runtime_context_required": ["localStorage"],
            "realism": ["storage-context"],
        },
        FixtureProfile.CONTEXT_COOKIE: {
            "family": "runtime-context",
            "description": "Base64 flow that depends on cookie device_id.",
            "expected_strategy": "base64_keyword_timestamp",
            "runtime_context_required": ["cookie"],
            "realism": ["cookie-context"],
        },
        FixtureProfile.CONTEXT_NAVIGATOR: {
            "family": "runtime-context",
            "description": "SHA-256 flow that depends on navigator.userAgent.",
            "expected_strategy": "sha256_keyword_timestamp",
            "runtime_context_required": ["navigator"],
            "realism": ["browser-fingerprint"],
        },
        FixtureProfile.WEBPACK_MINIFIED: {
            "family": "bundled",
            "description": "Webpack-like module wrapper with minified helpers around a SHA-256 sign function.",
            "expected_strategy": "sha256_keyword_timestamp",
            "realism": ["webpack-runtime", "minified-helper", "webcrypto"],
        },
        FixtureProfile.TOKEN_CHAIN: {
            "family": "token-chain",
            "description": "Bootstrap token request followed by sessionStorage-backed SHA-256 signing.",
            "expected_strategy": "sha256_keyword_timestamp",
            "runtime_context_required": ["sessionStorage"],
            "realism": ["bootstrap-request", "session-storage", "multi-request-chain"],
        },
        FixtureProfile.HYBRID_CONTEXT: {
            "family": "runtime-context",
            "description": "Base64 flow that combines localStorage nonce and CSRF cookie.",
            "expected_strategy": "base64_keyword_timestamp",
            "runtime_context_required": ["localStorage", "cookie"],
            "realism": ["multi-context", "cookie-context", "storage-context"],
            "expected_delivery": "partial_until_multi_binding_renderer",
        },
    }
    return metadata[profile]


def _normalize_profile(profile: str | FixtureProfile) -> FixtureProfile:
    if isinstance(profile, FixtureProfile):
        return profile
    try:
        return FixtureProfile(profile)
    except ValueError as exc:
        raise ValueError(f"Unsupported fixture profile: {profile}") from exc


def _build_html(title: str, profile: FixtureProfile) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <script src="/app.js"></script>
</head>
<body>
  <main>
    <h1>Reverse DeepAgent Fixture</h1>
    <p id="profile">profile: {profile.value}</p>
    <p id="status">loading...</p>
    <label>
      keyword
      <input id="keyword" value="sign" />
    </label>
    <button id="search" type="button">Search</button>
    <pre id="result"></pre>
  </main>
  <script>
    window.addEventListener('DOMContentLoaded', () => {{
      window.reverseFixture.search(document.getElementById('keyword').value);
      document.getElementById('search').addEventListener('click', () => {{
        window.reverseFixture.search(document.getElementById('keyword').value);
      }});
    }});
  </script>
</body>
</html>
"""


def _build_js(profile: FixtureProfile) -> str:
    if profile is FixtureProfile.DEFAULT:
        build_sign = r"""function buildSign(keyword, timestamp) {
  const FIXTURE_SEED = 'reverse-agent-fixture';
  const raw = `${keyword}:${timestamp}:${FIXTURE_SEED}`;
  const hash = Array.from(raw).reduce((acc, char) => (acc + char.charCodeAt(0)) % 100000, 0);
  return `sig_${hash.toString(16)}_${timestamp}`;
}"""
    elif profile is FixtureProfile.MD5:
        build_sign = r"""function rotateLeft(value, shift) {
  return (value << shift) | (value >>> (32 - shift));
}

function addUnsigned(left, right) {
  return (left + right) >>> 0;
}

function wordToHex(value) {
  let output = '';
  for (let index = 0; index < 4; index += 1) {
    output += ((value >>> (index * 8)) & 255).toString(16).padStart(2, '0');
  }
  return output;
}

function utf8Bytes(value) {
  return Array.from(new TextEncoder().encode(value));
}

function md5(message) {
  const bytes = utf8Bytes(message);
  const bitLength = bytes.length * 8;
  bytes.push(128);
  while ((bytes.length % 64) !== 56) {
    bytes.push(0);
  }
  for (let index = 0; index < 8; index += 1) {
    bytes.push(Math.floor(bitLength / (2 ** (8 * index))) & 255);
  }

  let a0 = 0x67452301;
  let b0 = 0xefcdab89;
  let c0 = 0x98badcfe;
  let d0 = 0x10325476;
  const shifts = [
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
  ];
  const constants = Array.from({ length: 64 }, (_, index) => Math.floor(Math.abs(Math.sin(index + 1)) * 2 ** 32) >>> 0);

  for (let offset = 0; offset < bytes.length; offset += 64) {
    const words = [];
    for (let index = 0; index < 16; index += 1) {
      const cursor = offset + index * 4;
      words[index] = (bytes[cursor] | (bytes[cursor + 1] << 8) | (bytes[cursor + 2] << 16) | (bytes[cursor + 3] << 24)) >>> 0;
    }

    let a = a0;
    let b = b0;
    let c = c0;
    let d = d0;

    for (let index = 0; index < 64; index += 1) {
      let f;
      let g;
      if (index < 16) {
        f = (b & c) | ((~b) & d);
        g = index;
      } else if (index < 32) {
        f = (d & b) | ((~d) & c);
        g = (5 * index + 1) % 16;
      } else if (index < 48) {
        f = b ^ c ^ d;
        g = (3 * index + 5) % 16;
      } else {
        f = c ^ (b | (~d));
        g = (7 * index) % 16;
      }
      const nextD = c;
      const nextC = b;
      const sum = addUnsigned(addUnsigned(a, f), addUnsigned(constants[index], words[g]));
      b = addUnsigned(b, rotateLeft(sum, shifts[index]));
      a = d;
      d = nextD;
      c = nextC;
    }

    a0 = addUnsigned(a0, a);
    b0 = addUnsigned(b0, b);
    c0 = addUnsigned(c0, c);
    d0 = addUnsigned(d0, d);
  }

  return `${wordToHex(a0)}${wordToHex(b0)}${wordToHex(c0)}${wordToHex(d0)}`;
}

function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  return md5(raw);
}"""
    elif profile is FixtureProfile.SHA1:
        build_sign = r"""async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
    elif profile is FixtureProfile.SHA256:
        build_sign = r"""async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
    elif profile is FixtureProfile.BASE64:
        build_sign = r"""function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  return btoa(raw);
}"""
    elif profile is FixtureProfile.CONTEXT_LOCALSTORAGE:
        build_sign = r"""function buildSign(keyword, timestamp) {
  const device = localStorage.getItem('device_id') || 'fixture-device';
  const raw = `${keyword}:${timestamp}:${device}`;
  return btoa(raw);
}"""
    elif profile is FixtureProfile.CONTEXT_COOKIE:
        build_sign = r"""function buildSign(keyword, timestamp) {
  const match = document.cookie.match(/(?:^|;\s*)device_id=([^;]+)/);
  const device = match ? decodeURIComponent(match[1]) : 'fixture-cookie-device';
  const raw = `${keyword}:${timestamp}:${device}`;
  return btoa(raw);
}"""
    elif profile is FixtureProfile.CONTEXT_NAVIGATOR:
        build_sign = r"""async function buildSign(keyword, timestamp) {
  const userAgent = navigator.userAgent;
  const raw = `${keyword}:${timestamp}:${userAgent}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
    elif profile is FixtureProfile.WEBPACK_MINIFIED:
        build_sign = r"""const __webpack_modules__ = {
  731: (module) => {
    const enc = new TextEncoder();
    const hex = (buffer) => Array.from(new Uint8Array(buffer)).map((item) => item.toString(16).padStart(2, '0')).join('');
    module.exports = {
      async sign(keyword, timestamp) {
        const raw = `${keyword}:${timestamp}`;
        return hex(await crypto.subtle.digest('SHA-256', enc.encode(raw)));
      },
    };
  },
};
const __webpack_module_cache__ = {};
function __webpack_require__(id) {
  const cached = __webpack_module_cache__[id];
  if (cached) return cached.exports;
  const module = (__webpack_module_cache__[id] = { exports: {} });
  __webpack_modules__[id](module, module.exports, __webpack_require__);
  return module.exports;
}
async function buildSign(keyword, timestamp) {
  return __webpack_require__(731).sign(keyword, timestamp);
}"""
    elif profile is FixtureProfile.TOKEN_CHAIN:
        build_sign = r"""async function loadFixtureToken(keyword) {
  const cached = sessionStorage.getItem('fixture_token');
  if (cached) return cached;
  const response = await fetch(`/api/bootstrap?keyword=${encodeURIComponent(keyword)}`);
  const data = await response.json();
  const token = data.token || 'fixture-token';
  sessionStorage.setItem('fixture_token', token);
  return token;
}

async function buildSign(keyword, timestamp) {
  const token = await loadFixtureToken(keyword);
  const raw = `${keyword}:${timestamp}:${token}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
    elif profile is FixtureProfile.HYBRID_CONTEXT:
        build_sign = r"""function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('fixture_nonce') || 'fixture-nonce';
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  const csrf = match ? decodeURIComponent(match[1]) : 'fixture-csrf';
  const raw = `${keyword}:${timestamp}:${nonce}:${csrf}`;
  return btoa(raw);
}"""
    else:
        raise ValueError(f"Unsupported fixture profile: {profile}")

    setup = ""
    if profile is FixtureProfile.CONTEXT_LOCALSTORAGE:
        setup = "  localStorage.setItem('device_id', 'fixture-device');\n"
    elif profile is FixtureProfile.CONTEXT_COOKIE:
        setup = "  document.cookie = 'device_id=fixture-cookie-device; path=/';\n"
    elif profile is FixtureProfile.HYBRID_CONTEXT:
        setup = (
            f"  localStorage.setItem('fixture_nonce', {json.dumps(FIXTURE_HYBRID_NONCE)});\n"
            f"  document.cookie = 'csrf_token={FIXTURE_HYBRID_CSRF}; path=/';\n"
        )

    return """window.reverseFixture = (() => {{
  const FIXTURE_PROFILE = {profile_json};
  const FIXTURE_SEED = 'reverse-agent-fixture';
{setup}

  {build_sign}

  async function search(keyword) {{
    const timestamp = Date.now();
    const sign = await buildSign(keyword, timestamp);
    const payload = {{
      keyword,
      timestamp,
      sign,
      fixture: FIXTURE_SEED,
      profile: FIXTURE_PROFILE,
    }};
    const response = await fetch(`/api/search?keyword=${{encodeURIComponent(keyword)}}&t=${{timestamp}}`, {{
      method: 'POST',
      headers: {{
        'content-type': 'application/json',
        'x-sign': sign,
        'x-fixture': FIXTURE_SEED,
        'x-fixture-profile': FIXTURE_PROFILE,
      }},
      body: JSON.stringify(payload),
    }});
    const data = await response.json();
    document.getElementById('status').textContent = `sign ready: ${{sign}}`;
    document.getElementById('result').textContent = JSON.stringify(data, null, 2);
    return data;
  }}

  return {{ buildSign, search, profile: FIXTURE_PROFILE }};
}})();
""".format(profile_json=json.dumps(profile.value), setup=setup, build_sign=build_sign)


def _build_api_response(path: str, query: dict[str, list[str]], body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if body:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {"raw": body.decode("utf-8", errors="replace")}
    keyword = query.get("keyword", ["sign"])[0]
    timestamp = query.get("t", ["0"])[0]
    return {
        "ok": True,
        "path": path,
        "keyword": keyword,
        "timestamp": timestamp,
        "profile": headers.get("x-fixture-profile", ""),
        "body": payload,
        "headers": {
            "x-sign": headers.get("x-sign", ""),
            "x-fixture": headers.get("x-fixture", ""),
            "x-fixture-profile": headers.get("x-fixture-profile", ""),
        },
    }


class _FixtureHandler(BaseHTTPRequestHandler):
    server_version = "ReverseDeepAgentFixture/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_request(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        body = self.rfile.read(int(self.headers.get("content-length", "0") or "0"))
        status_code = HTTPStatus.OK
        content_type = "application/json; charset=utf-8"
        if path == "/" or path == "/index.html":
            content_type = "text/html; charset=utf-8"
            payload = _build_html(
                getattr(self.server, "fixture_title", "Reverse DeepAgent Fixture"),  # type: ignore[attr-defined]
                getattr(self.server, "fixture_profile", FixtureProfile.DEFAULT),  # type: ignore[attr-defined]
            )
        elif path == "/app.js":
            content_type = "application/javascript; charset=utf-8"
            payload = _build_js(getattr(self.server, "fixture_profile", FixtureProfile.DEFAULT))  # type: ignore[attr-defined]
        elif path == "/healthz":
            profile = getattr(self.server, "fixture_profile", FixtureProfile.DEFAULT)  # type: ignore[attr-defined]
            payload = json.dumps(
                {
                    "ok": True,
                    "fixture": "reverse-agent-sign",
                    "profile": profile.value,
                    "profile_metadata": _profile_metadata(profile),
                    "profiles": FIXTURE_PROFILE_VALUES,
                },
                ensure_ascii=False,
                indent=2,
            )
        elif path == "/api/bootstrap":
            profile = getattr(self.server, "fixture_profile", FixtureProfile.DEFAULT)  # type: ignore[attr-defined]
            payload = json.dumps(
                {
                    "ok": True,
                    "profile": profile.value,
                    "token": FIXTURE_BOOTSTRAP_TOKEN,
                    "keyword": query.get("keyword", ["sign"])[0],
                    "ttl_ms": 300000,
                },
                ensure_ascii=False,
                indent=2,
            )
        elif path == "/api/search":
            payload = json.dumps(
                _build_api_response(path=path, query=query, body=body, headers={k.lower(): v for k, v in self.headers.items()}),
                ensure_ascii=False,
                indent=2,
            )
        else:
            status_code = HTTPStatus.NOT_FOUND
            payload = json.dumps({"ok": False, "error": "not found", "path": path}, ensure_ascii=False, indent=2)

        if isinstance(payload, str):
            raw = payload.encode("utf-8")
        else:
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@dataclass(slots=True)
class SignFixtureServer:
    """A local HTTP fixture server with a deterministic sign flow."""

    server: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str
    profile: FixtureProfile

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread.is_alive():
            self.thread.join(timeout=3)


def start_fixture_server(
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    title: str = "Reverse DeepAgent Sign Fixture",
    profile: str | FixtureProfile = FixtureProfile.DEFAULT,
) -> SignFixtureServer:
    """Start the sign fixture server on a background thread."""

    class FixtureHTTPServer(ThreadingHTTPServer):
        daemon_threads = True

    normalized_profile = _normalize_profile(profile)
    server = FixtureHTTPServer((host, port), _FixtureHandler)
    server.fixture_title = title  # type: ignore[attr-defined]
    server.fixture_profile = normalized_profile  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="reverse-deepagent-fixture", daemon=True)
    thread.start()
    actual_host, actual_port = server.server_address[:2]
    base_url = f"http://{actual_host}:{actual_port}"
    return SignFixtureServer(server=server, thread=thread, base_url=base_url, profile=normalized_profile)

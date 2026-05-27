from __future__ import annotations

import argparse
import json
from contextlib import suppress
from typing import Sequence
from urllib.request import urlopen

from reverse_deepagent.fixtures.web_sign import FIXTURE_PROFILE_VALUES, start_fixture_server


def build_fixture_parser() -> argparse.ArgumentParser:
    """Build the parser for the localhost sign fixture command."""

    parser = argparse.ArgumentParser(description="Run a local localhost sign fixture server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for the fixture server.")
    parser.add_argument("--port", type=int, default=0, help="Bind port for the fixture server. Default 0 picks a free port.")
    parser.add_argument("--title", default="Reverse DeepAgent Sign Fixture", help="HTML title for the fixture page.")
    parser.add_argument("--profile", choices=FIXTURE_PROFILE_VALUES, default="default", help="Fixture algorithm/profile to serve.")
    parser.add_argument("--check", action="store_true", help="Start the fixture, call /healthz once, print info, and exit.")
    return parser


def main_fixture(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for the localhost sign fixture server."""

    args = build_fixture_parser().parse_args(argv)
    fixture = start_fixture_server(host=args.host, port=args.port, title=args.title, profile=args.profile)
    try:
        if args.check:
            with urlopen(f"{fixture.base_url}/healthz", timeout=5) as response:  # nosec B310 - local fixture only
                payload = json.loads(response.read().decode("utf-8"))
            print(
                json.dumps(
                    {
                        "ok": True,
                        "base_url": fixture.base_url,
                        "profile": fixture.profile.value,
                        "health": payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        print(
            json.dumps(
                {
                    "ok": True,
                    "base_url": fixture.base_url,
                    "profile": fixture.profile.value,
                    "health_url": f"{fixture.base_url}/healthz",
                    "page_url": f"{fixture.base_url}/",
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )
        try:
            while True:
                fixture.thread.join(timeout=1)
        except KeyboardInterrupt:
            return 0
        return 0
    finally:
        with suppress(Exception):
            fixture.close()

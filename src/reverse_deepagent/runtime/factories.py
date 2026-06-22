from __future__ import annotations

from typing import Any

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.adapters.lightweight_web import LightweightWebRuntimeConfig, create_lightweight_web_runtime
from reverse_deepagent.adapters.native_web import create_native_web_runtime
from reverse_deepagent.adapters.platforms import AndroidAdbRuntime, IosSimulatorRuntime, MiniProgramDevtoolsRuntime
from reverse_deepagent.runtime.mock_bridge import MockJSReverserBridge


def _mock_runtime_factory(**_: Any) -> JSReverserRuntime:
    return JSReverserRuntime(
        bridge=MockJSReverserBridge(),
        backend_id="mock",
        display_name="Mock JSReverser Runtime",
        transport="in-process",
    )


def _android_adb_runtime_factory(
    *,
    android_adb_command: str | None = None,
    android_device_serial: str | None = None,
    android_package_name: str | None = None,
    **_: Any,
) -> AndroidAdbRuntime:
    return AndroidAdbRuntime(
        adb_command=android_adb_command or "adb",
        device_serial=android_device_serial,
        package_name=android_package_name,
    )


def _ios_simulator_runtime_factory(
    *,
    ios_xcrun_command: str | None = None,
    ios_device_id: str | None = None,
    ios_bundle_id: str | None = None,
    **_: Any,
) -> IosSimulatorRuntime:
    return IosSimulatorRuntime(
        xcrun_command=ios_xcrun_command or "xcrun",
        device_id=ios_device_id,
        bundle_id=ios_bundle_id,
    )


def _mini_program_devtools_runtime_factory(
    *,
    mini_program_devtools_command: str | None = None,
    mini_program_vendor: str | None = None,
    mini_program_project_path: str | None = None,
    **_: Any,
) -> MiniProgramDevtoolsRuntime:
    return MiniProgramDevtoolsRuntime(
        devtools_command=mini_program_devtools_command,
        vendor=mini_program_vendor or "wechat",
        project_path=mini_program_project_path,
    )


def _playwright_cli_runtime_factory(
    *,
    playwright_command: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="playwright-cli",
        display_name="Playwright CLI Runtime",
        transport="playwright-cli",
        command=playwright_command or "playwright",
        command_args=["--version"],
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _chrome_cdp_runtime_factory(
    *,
    browser_url: str | None = None,
    cdp_browser_url: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="chrome-cdp",
        display_name="Chrome CDP Runtime",
        transport="chrome-cdp",
        browser_url=cdp_browser_url or browser_url or "http://127.0.0.1:9222",
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _browser_cli_runtime_factory(
    *,
    browser_cli_command: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
) -> JSReverserRuntime:
    config = LightweightWebRuntimeConfig(
        backend_id="browser-cli",
        display_name="Generic Browser CLI Runtime",
        transport="browser-cli",
        command=browser_cli_command,
        command_args=["--version"] if browser_cli_command else [],
        request_timeout=request_timeout or 10.0,
    )
    return create_lightweight_web_runtime(config=config)


def _native_web_runtime_factory(
    *,
    browser: str | None = None,
    browser_provider: str | None = None,
    browser_headless: bool | None = None,
    browser_profile_dir: str | None = None,
    browser_executable_path: str | None = None,
    browser_args: list[str] | None = None,
    browser_url: str | None = None,
    cdp_browser_url: str | None = None,
    browser_humanize: bool | None = None,
    browser_proxy: str | None = None,
    browser_geoip: bool | None = None,
    browser_locale: str | None = None,
    browser_timezone: str | None = None,
    request_timeout: float | None = None,
    **_: Any,
):
    return create_native_web_runtime(
        browser=browser or browser_provider,
        browser_headless=True if browser_headless is None else browser_headless,
        browser_profile_dir=browser_profile_dir,
        browser_executable_path=browser_executable_path,
        browser_args=browser_args or [],
        browser_url=browser_url,
        cdp_browser_url=cdp_browser_url,
        browser_humanize=browser_humanize,
        browser_proxy=browser_proxy,
        browser_geoip=browser_geoip,
        browser_locale=browser_locale,
        browser_timezone=browser_timezone,
        request_timeout=request_timeout,
    )


def _remote_cdp_provider_runtime_factory(**kwargs: Any):
    kwargs.setdefault("browser", "remote-cdp")
    return _native_web_runtime_factory(**kwargs)

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Any, Callable

from reverse_deepagent.browser.capabilities import metadata_has_secret_like_keys

from .detectors import ALGORITHM_STRATEGY_REGISTRY, AlgorithmStrategyRule, StrategyDetector, detect_algorithm_strategy

STRATEGY_DETECTOR_ENTRY_POINT_GROUP = "reverse_deepagent.strategy_detectors"
StrategyProviderDetector = Callable[[str], dict[str, Any]]


class StrategyDetectorRegistryError(ValueError):
    """Raised when strategy detector provider registration is invalid."""


@dataclass(frozen=True, slots=True)
class StrategyDetectorProviderRegistration:
    """Metadata and callable registration for one strategy detector provider.

    Registration loading is metadata-only: it may import a plugin module, but it
    must not execute detectors, collect runtime context, start browsers, call
    MCP, run replay, or mutate files. The detector callable is invoked only by
    explicit detection helpers.
    """

    provider_id: str
    display_name: str
    rules: tuple[AlgorithmStrategyRule, ...]
    detector: StrategyProviderDetector
    aliases: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise StrategyDetectorRegistryError("Strategy detector provider id must not be empty")
        if not self.rules:
            raise StrategyDetectorRegistryError(f"Strategy detector provider {self.provider_id!r} must declare at least one rule")
        if not callable(self.detector):
            raise StrategyDetectorRegistryError(f"Strategy detector provider {self.provider_id!r} detector must be callable")
        if metadata_has_secret_like_keys(self.metadata):
            raise StrategyDetectorRegistryError(f"Strategy detector provider {self.provider_id!r} metadata contains secret-like keys")
        if metadata_has_secret_like_keys(self.side_effect_policy):
            raise StrategyDetectorRegistryError(f"Strategy detector provider {self.provider_id!r} side-effect policy contains secret-like keys")

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.provider_id, *self.aliases)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "description": self.description,
            "aliases": list(self.aliases),
            "keys": list(self.keys),
            "rule_count": len(self.rules),
            "rules": [_rule_metadata(rule) for rule in self.rules],
            "emits": sorted({strategy_id for rule in self.rules for strategy_id in rule.emits}),
            "metadata": self.metadata,
            "side_effect_policy": self.side_effect_policy or strategy_detector_metadata_side_effect_policy(),
        }


class StrategyDetectorProviderRegistry:
    """Side-effect-light registry for replaceable strategy detector providers."""

    def __init__(self) -> None:
        self._registrations: dict[str, StrategyDetectorProviderRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: StrategyDetectorProviderRegistration) -> None:
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise StrategyDetectorRegistryError(f"Strategy detector provider key already registered: {key}")
        self._registrations[registration.provider_id] = registration
        for alias in registration.aliases:
            self._aliases[alias] = registration.provider_id

    def load_entry_points(self, group: str = STRATEGY_DETECTOR_ENTRY_POINT_GROUP) -> list[str]:
        loaded_provider_ids: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                plugin_value = entry_point.load()
            except Exception as exc:  # pragma: no cover - defensive plugin error path
                raise RuntimeError(f"Failed to load strategy detector entry point {entry_point.name!r}: {exc}") from exc
            registrations = self._coerce_plugin_registrations(entry_point.name, plugin_value)
            for registration in registrations:
                self.register(registration)
                loaded_provider_ids.append(registration.provider_id)
        return loaded_provider_ids

    def resolve(self, provider_id: str) -> StrategyDetectorProviderRegistration:
        canonical = provider_id if provider_id in self._registrations else self._aliases.get(provider_id)
        if canonical is None:
            known = ", ".join(self.provider_ids())
            raise StrategyDetectorRegistryError(f"Unsupported strategy detector provider: {provider_id}. Known providers: {known}")
        return self._registrations[canonical]

    def is_registered(self, provider_id: str) -> bool:
        return provider_id in self._registrations or provider_id in self._aliases

    def provider_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_metadata(self) -> list[dict[str, Any]]:
        return [self._registrations[key].to_metadata() for key in sorted(self._registrations)]

    def detect(self, source_context: str, *, provider_id: str | None = None) -> dict[str, Any]:
        if provider_id:
            registration = self.resolve(provider_id)
            strategy = registration.detector(source_context)
            return _with_provider_metadata(strategy, registration)
        for registration in self._registrations.values():
            strategy = registration.detector(source_context)
            if strategy and strategy.get("id") != "unsupported_manual_port_required":
                return _with_provider_metadata(strategy, registration)
        if self._registrations:
            first = next(iter(self._registrations.values()))
            return _with_provider_metadata(first.detector(source_context), first)
        return detect_algorithm_strategy(source_context)

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[StrategyDetectorProviderRegistration]:
        if isinstance(value, StrategyDetectorProviderRegistration):
            return [value]
        if callable(value):
            return StrategyDetectorProviderRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, StrategyDetectorProviderRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "Strategy detector entry point "
            f"{entry_point_name!r} must return a StrategyDetectorProviderRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


def builtin_algorithm_strategy_detector_registration() -> StrategyDetectorProviderRegistration:
    rules = ALGORITHM_STRATEGY_REGISTRY

    def detector(source_context: str) -> dict[str, Any]:
        return detect_algorithm_strategy(source_context, registry=rules)

    return StrategyDetectorProviderRegistration(
        provider_id="builtin-algorithm-strategy",
        display_name="Built-in algorithm strategy detectors",
        aliases=("builtin", "algorithm-strategy", "default-strategy"),
        rules=rules,
        detector=detector,
        description="Conservative built-in JS signing strategy detector corpus for pure-Python rebuild triage.",
        metadata={
            "target_platforms": ["web"],
            "detector_scope": "source-snippet-patterns",
            "runtime_context_collection": False,
            "replay_execution": False,
            "plugin_kind": "builtin",
        },
        side_effect_policy=strategy_detector_metadata_side_effect_policy(),
    )


def build_default_strategy_detector_registry(*, load_entry_points: bool = True) -> StrategyDetectorProviderRegistry:
    registry = StrategyDetectorProviderRegistry()
    registry.register(builtin_algorithm_strategy_detector_registration())
    if load_entry_points:
        registry.load_entry_points()
    return registry


def detect_with_strategy_detector_registry(
    source_context: str,
    *,
    registry: StrategyDetectorProviderRegistry | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    return (registry or build_default_strategy_detector_registry()).detect(source_context, provider_id=provider_id)


def list_strategy_detector_provider_registry(*, load_entry_points: bool = True) -> list[dict[str, Any]]:
    return build_default_strategy_detector_registry(load_entry_points=load_entry_points).list_metadata()


def strategy_detector_metadata_side_effect_policy() -> dict[str, Any]:
    return {
        "metadata_only": True,
        "read_only": True,
        "files_mutated": False,
        "runtime_context_collected": False,
        "replay_executed": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "javascript_evaluated": False,
        "hooks_installed": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _rule_metadata(rule: AlgorithmStrategyRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "emits": list(rule.emits),
        "description": rule.description,
    }


def _with_provider_metadata(strategy: dict[str, Any], registration: StrategyDetectorProviderRegistration) -> dict[str, Any]:
    payload = dict(strategy)
    payload["detector_provider"] = {
        "provider_id": registration.provider_id,
        "display_name": registration.display_name,
        "rule_count": len(registration.rules),
        "side_effect_policy": registration.side_effect_policy or strategy_detector_metadata_side_effect_policy(),
    }
    return payload


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=group)
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        selected = entry_points.get(group, [])
    return list(selected)

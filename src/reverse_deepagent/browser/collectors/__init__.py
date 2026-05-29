from .cdp import CDPEnhancedCollector
from .console import ConsoleCollector
from .dom import DOMCollector
from .network import NetworkCollector
from .screenshots import ScreenshotCollector
from .scripts import ScriptCollector
from .storage import StorageCollector

__all__ = [
    "CDPEnhancedCollector",
    "ConsoleCollector",
    "DOMCollector",
    "NetworkCollector",
    "ScreenshotCollector",
    "ScriptCollector",
    "StorageCollector",
]

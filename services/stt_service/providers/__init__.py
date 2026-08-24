"""
STT providers package.
Imports all provider implementations to register them.
"""
from .base import BaseSTTProvider
from .registry import register_stt, get_stt_provider, list_providers

# Import mock provider (always available for testing)
from .mock_provider import MockSTTProvider

# Import providers to trigger registration (may fail if dependencies not installed)
try:
    from .indicconformer_provider import IndicConformerSTT
except ImportError:
    IndicConformerSTT = None

try:
    from .sravaani_provider import SravaaniSTT
except ImportError:
    SravaaniSTT = None

__all__ = [
    "BaseSTTProvider",
    "register_stt",
    "get_stt_provider",
    "list_providers",
    "MockSTTProvider",
    "IndicConformerSTT",
    "SravaaniSTT",
]

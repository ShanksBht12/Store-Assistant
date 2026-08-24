"""
Provider registry for STT services.
Handles registration and instantiation of STT providers.
"""
from typing import Dict, Type
from .base import BaseSTTProvider


# Global registry of STT providers
STT_PROVIDERS: Dict[str, Type[BaseSTTProvider]] = {}


def register_stt(name: str):
    """
    Decorator to register an STT provider.
    
    Usage:
        @register_stt("my_provider")
        class MySTTProvider(BaseSTTProvider):
            ...
    """
    def wrapper(cls: Type[BaseSTTProvider]):
        STT_PROVIDERS[name] = cls
        return cls
    return wrapper


def get_stt_provider(config: Dict) -> BaseSTTProvider:
    """
    Get an STT provider instance based on configuration.
    
    Args:
        config: Full configuration dictionary
    
    Returns:
        Initialized STT provider instance
    
    Raises:
        ValueError: If provider not found or configuration is invalid
    """
    stt_config = config.get("stt", {})
    provider_name = stt_config.get("provider")
    
    if not provider_name:
        raise ValueError("No STT provider specified in config")
    
    if provider_name not in STT_PROVIDERS:
        available = ", ".join(STT_PROVIDERS.keys())
        raise ValueError(
            f"STT provider '{provider_name}' not found. "
            f"Available providers: {available}"
        )
    
    provider_cls = STT_PROVIDERS[provider_name]
    instance = provider_cls()
    
    # Get provider-specific configuration
    provider_config = stt_config.get(provider_name, {})
    instance.load(**provider_config)
    
    return instance


def list_providers() -> list:
    """List all registered STT providers."""
    return list(STT_PROVIDERS.keys())

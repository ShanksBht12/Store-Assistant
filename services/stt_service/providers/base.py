"""
Base class for STT providers.
All STT implementations must inherit from this class.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseSTTProvider(ABC):
    """Abstract base class for Speech-to-Text providers."""
    
    def __init__(self):
        self.model = None
        self.loaded = False
    
    @abstractmethod
    def load(self, **params) -> None:
        """
        Load the STT model. This should be called once at service startup.
        
        Args:
            **params: Provider-specific configuration parameters
        """
        pass
    
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw audio data
            sample_rate: Sample rate in Hz (default: 16000)
        
        Returns:
            Dictionary with keys:
                - text (str): Transcribed text
                - confidence (float | None): Confidence score
                - duration_ms (int | None): Processing duration
        """
        pass
    
    def is_loaded(self) -> bool:
        """Check if the model is fully loaded and ready."""
        return self.loaded

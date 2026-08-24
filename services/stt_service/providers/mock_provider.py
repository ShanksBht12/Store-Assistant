"""
Mock STT provider for testing without heavy dependencies.
Returns dummy transcription to test the service architecture.
"""
import time
import logging
from typing import Dict, Any

from .base import BaseSTTProvider
from .registry import register_stt

logger = logging.getLogger(__name__)


@register_stt("mock")
class MockSTTProvider(BaseSTTProvider):
    """Mock provider for testing without model dependencies."""
    
    def load(self, **params) -> None:
        """Mock load - instant."""
        logger.info("Loading mock STT provider (instant)")
        time.sleep(0.5)  # Simulate small delay
        self.sample_rate = params.get("sample_rate", 16000)
        self.loaded = True
        logger.info("Mock STT provider loaded successfully")
    
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """Mock transcription - returns dummy text."""
        if not self.loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        import numpy as np
        
        start_time = time.time()
        
        # Convert bytes to array to get duration
        if isinstance(audio_bytes, bytes):
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            audio_array = audio_bytes
        
        duration_seconds = len(audio_array) / sample_rate
        
        # Mock transcription with some variety
        mock_texts = [
            "नमस्ते, म तपाईंलाई कसरी मद्दत गर्न सक्छु?",  # Hello, how can I help you?
            "यो एक परीक्षण अडियो हो",  # This is a test audio
            "Mock transcription successful",
        ]
        
        text = mock_texts[int(time.time()) % len(mock_texts)]
        
        # Simulate processing time
        time.sleep(0.1)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Mock transcription complete in {duration_ms}ms: '{text}' (audio: {duration_seconds:.2f}s)")
        
        return {
            "text": text,
            "confidence": 0.95,  # Mock confidence
            "duration_ms": duration_ms
        }

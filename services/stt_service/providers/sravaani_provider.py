"""
SraVaani STT provider using HuggingFace transformers.
Supports Nepali and other Indic languages.
"""
import os
import tempfile
import time
from typing import Dict, Any
import logging

from .base import BaseSTTProvider
from .registry import register_stt

logger = logging.getLogger(__name__)


@register_stt("sravaani")
class SravaaniSTT(BaseSTTProvider):
    """SraVaani provider for Nepali STT using transformers."""
    
    def load(self, **params) -> None:
        """
        Load the SraVaani model.
        
        Expected params:
            - hf_model_id: HuggingFace model ID
            - hf_token_env: Environment variable name for HF token
            - device: 'cuda' or 'cpu'
            - trust_remote_code: Must be True for this model
            - revision: Git revision/commit hash (recommended: pin specific hash)
        """
        try:
            import torch
            from transformers import AutoModel
        except ImportError as e:
            raise ImportError(
                "transformers not installed. Install with: pip install transformers torch"
            ) from e
        
        hf_model_id = params.get("hf_model_id", "ARTPARK-IISc/SraVaani-1.0")
        hf_token_env = params.get("hf_token_env", "HF_TOKEN")
        device = params.get("device", "cpu")
        trust_remote_code = params.get("trust_remote_code", True)
        revision = params.get("revision", "main")
        self.sample_rate = params.get("sample_rate", 16000)
        
        # Security check
        if not trust_remote_code:
            raise ValueError(
                "SraVaani requires trust_remote_code=True. "
                "This executes code from the model repository. "
                "Ensure you trust the source and have pinned a specific revision."
            )
        
        if revision == "main":
            logger.warning(
                "Using 'main' branch for SraVaani. "
                "For production, pin to a specific commit hash."
            )
        
        # Get HuggingFace token from environment
        hf_token = os.environ.get(hf_token_env)
        if not hf_token:
            logger.warning(f"HuggingFace token not found in {hf_token_env}. Model download may fail.")
        
        logger.info(f"Loading SraVaani model: {hf_model_id} (revision: {revision})")
        logger.info(f"⚠️  trust_remote_code=True - executing code from model repo")
        
        start_time = time.time()
        
        # Check device availability
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available. Falling back to CPU.")
            device = "cpu"
            logger.warning("CPU mode: expect ~10-30s per file (vs ~2-5s on GPU)")
        
        # Load model with trust_remote_code
        self.model = AutoModel.from_pretrained(
            hf_model_id,
            trust_remote_code=trust_remote_code,
            revision=revision,
            token=hf_token
        ).to(device).eval()
        
        self.device = device
        
        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully in {load_time:.2f}s on {device}")
        
        self.loaded = True
    
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw audio data (numpy array or bytes)
            sample_rate: Sample rate
        
        Returns:
            Dict with 'text', 'confidence', 'duration_ms'
        """
        if not self.loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        import soundfile as sf
        import numpy as np
        
        start_time = time.time()
        
        # Convert bytes to numpy array if needed
        if isinstance(audio_bytes, bytes):
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            audio_array = audio_bytes
        
        # SraVaani's transcribe() expects file paths
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            sf.write(tmp_path, audio_array, sample_rate)
        
        try:
            # Transcribe with hypotheses to get confidence if available
            result = self.model.transcribe(tmp_path, return_hypotheses=True)
            
            # Extract text from result
            if result and len(result) > 0:
                text = result[0].text if hasattr(result[0], 'text') else str(result[0])
            else:
                text = ""
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Transcription complete in {duration_ms}ms: '{text}'")
            
            return {
                "text": text,
                "confidence": None,  # Could extract from hypotheses if available
                "duration_ms": duration_ms
            }
        
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

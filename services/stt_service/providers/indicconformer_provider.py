"""
IndicConformer STT provider using NeMo toolkit.
Supports Nepali speech recognition with hybrid RNNT/CTC decoding.
"""
import os
import tempfile
import time
from typing import Dict, Any
import logging

from .base import BaseSTTProvider
from .registry import register_stt

logger = logging.getLogger(__name__)


@register_stt("indicconformer")
class IndicConformerSTT(BaseSTTProvider):
    """IndicConformer provider for Nepali STT using NeMo."""
    
    def load(self, **params) -> None:
        """
        Load the IndicConformer model.
        
        Expected params:
            - hf_model_id: HuggingFace model ID
            - hf_token_env: Environment variable name for HF token
            - device: 'cuda' or 'cpu'
            - decoding: 'rnnt' (streaming) or 'ctc' (batch-only)
            - sample_rate: Target sample rate (default: 16000)
        """
        try:
            import nemo.collections.asr as nemo_asr
            import torch
        except ImportError as e:
            raise ImportError(
                "NeMo not installed. Install with: pip install nemo_toolkit[all]"
            ) from e
        
        hf_model_id = params.get("hf_model_id", "ai4bharat/indicconformer_stt_ne_hybrid_rnnt_large")
        hf_token_env = params.get("hf_token_env", "HF_TOKEN")
        device = params.get("device", "cpu")
        decoding = params.get("decoding", "rnnt")
        self.sample_rate = params.get("sample_rate", 16000)
        
        # Get HuggingFace token from environment
        hf_token = os.environ.get(hf_token_env)
        if not hf_token:
            logger.warning(f"HuggingFace token not found in {hf_token_env}. Model download may fail.")
        
        logger.info(f"Loading IndicConformer model: {hf_model_id}")
        logger.info(f"This may take ~3 minutes on first run...")
        
        start_time = time.time()
        
        # Check device availability
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available. Falling back to CPU.")
            device = "cpu"
        
        # Load the hybrid RNNT/CTC model
        # This model supports both decoders; choose at runtime
        self.model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(
            model_name=hf_model_id
        )
        
        self.model = self.model.to(device)
        self.model.eval()
        
        # Set the decoding strategy
        if decoding not in ["rnnt", "ctc"]:
            raise ValueError(f"Invalid decoding strategy: {decoding}. Use 'rnnt' or 'ctc'.")
        
        self.model.change_decoding_strategy(decoder_type=decoding)
        self.decoding = decoding
        self.device = device
        
        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully in {load_time:.2f}s on {device}")
        logger.info(f"Using {decoding.upper()} decoder")
        
        self.loaded = True
    
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Transcribe audio bytes to text.
        
        Args:
            audio_bytes: Raw audio data (numpy array or bytes)
            sample_rate: Sample rate (must match model's expected rate)
        
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
        
        # NeMo's transcribe() expects file paths, so write to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            sf.write(tmp_path, audio_array, sample_rate)
        
        try:
            # Transcribe
            transcription = self.model.transcribe([tmp_path])
            text = transcription[0] if transcription else ""
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Transcription complete in {duration_ms}ms: '{text}'")
            
            return {
                "text": text,
                "confidence": None,  # NeMo basic transcribe doesn't return confidence
                "duration_ms": duration_ms
            }
        
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

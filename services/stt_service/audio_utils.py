"""
Audio processing utilities for STT service.
Handles audio format conversion, normalization, and VAD.
"""
import io
import subprocess
import logging
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


def normalize_audio(
    audio_data: bytes,
    target_sample_rate: int = 16000,
    target_channels: int = 1
) -> Tuple[np.ndarray, int]:
    """
    Normalize audio to target sample rate and channel count.
    
    Args:
        audio_data: Input audio bytes (any format supported by soundfile/ffmpeg)
        target_sample_rate: Target sample rate in Hz
        target_channels: Target channel count (1=mono, 2=stereo)
    
    Returns:
        Tuple of (audio_array, sample_rate)
    """
    try:
        import soundfile as sf
        
        # Try to read directly with soundfile first
        try:
            audio_array, sample_rate = sf.read(io.BytesIO(audio_data))
            
            # Convert to mono if needed
            if len(audio_array.shape) > 1 and target_channels == 1:
                audio_array = np.mean(audio_array, axis=1)
            
            # Resample if needed
            if sample_rate != target_sample_rate:
                audio_array = resample_audio(audio_array, sample_rate, target_sample_rate)
                sample_rate = target_sample_rate
            
            return audio_array, sample_rate
        
        except Exception as e:
            logger.warning(f"soundfile failed, trying ffmpeg: {e}")
            return normalize_with_ffmpeg(audio_data, target_sample_rate, target_channels)
    
    except ImportError:
        logger.warning("soundfile not installed, using ffmpeg only")
        return normalize_with_ffmpeg(audio_data, target_sample_rate, target_channels)


def normalize_with_ffmpeg(
    audio_data: bytes,
    target_sample_rate: int = 16000,
    target_channels: int = 1
) -> Tuple[np.ndarray, int]:
    """
    Normalize audio using ffmpeg.
    
    Args:
        audio_data: Input audio bytes
        target_sample_rate: Target sample rate
        target_channels: Target channels (1 or 2)
    
    Returns:
        Tuple of (audio_array, sample_rate)
    """
    try:
        # Use ffmpeg to convert to PCM WAV
        cmd = [
            'ffmpeg',
            '-i', 'pipe:0',  # Read from stdin
            '-ar', str(target_sample_rate),  # Sample rate
            '-ac', str(target_channels),  # Channels
            '-f', 's16le',  # Output format: signed 16-bit little-endian PCM
            '-'  # Write to stdout
        ]
        
        process = subprocess.run(
            cmd,
            input=audio_data,
            capture_output=True,
            check=True
        )
        
        # Convert PCM bytes to numpy array
        audio_array = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        
        return audio_array, target_sample_rate
    
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg conversion failed: {e.stderr.decode()}")
        raise RuntimeError("Audio conversion failed. Ensure ffmpeg is installed.")
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to process audio files.")


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """
    Resample audio to target sample rate.
    
    Args:
        audio: Audio array
        orig_sr: Original sample rate
        target_sr: Target sample rate
    
    Returns:
        Resampled audio array
    """
    if orig_sr == target_sr:
        return audio
    
    try:
        import librosa
        return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)
    except ImportError:
        # Fallback: simple linear interpolation
        logger.warning("librosa not available, using basic resampling")
        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)
        indices = np.linspace(0, len(audio) - 1, target_length)
        return np.interp(indices, np.arange(len(audio)), audio)


def apply_vad(
    audio: np.ndarray,
    sample_rate: int,
    aggressiveness: int = 2
) -> np.ndarray:
    """
    Apply Voice Activity Detection to remove silence.
    
    Args:
        audio: Audio array
        sample_rate: Sample rate
        aggressiveness: VAD aggressiveness (0-3, higher = more aggressive)
    
    Returns:
        Audio with silence trimmed
    """
    try:
        import webrtcvad
        
        vad = webrtcvad.Vad(aggressiveness)
        
        # VAD works on 10, 20, or 30ms frames
        frame_duration = 30  # ms
        frame_length = int(sample_rate * frame_duration / 1000)
        
        # Convert to 16-bit PCM
        audio_int16 = (audio * 32768).astype(np.int16)
        
        # Process frames
        voiced_frames = []
        for i in range(0, len(audio_int16) - frame_length, frame_length):
            frame = audio_int16[i:i + frame_length]
            if len(frame) < frame_length:
                break
            
            # VAD expects bytes
            frame_bytes = frame.tobytes()
            
            if vad.is_speech(frame_bytes, sample_rate):
                voiced_frames.append(frame)
        
        if not voiced_frames:
            logger.warning("No speech detected by VAD, returning original audio")
            return audio
        
        # Concatenate voiced frames and convert back to float32
        voiced_audio = np.concatenate(voiced_frames).astype(np.float32) / 32768.0
        
        return voiced_audio
    
    except ImportError:
        logger.warning("webrtcvad not installed, skipping VAD")
        return audio
    except Exception as e:
        logger.warning(f"VAD failed: {e}, returning original audio")
        return audio


def trim_silence(audio: np.ndarray, threshold: float = 0.01) -> np.ndarray:
    """
    Simple silence trimming based on amplitude threshold.
    
    Args:
        audio: Audio array
        threshold: Amplitude threshold for silence detection
    
    Returns:
        Trimmed audio
    """
    # Find non-silent regions
    non_silent = np.abs(audio) > threshold
    
    if not non_silent.any():
        return audio
    
    # Find first and last non-silent indices
    indices = np.where(non_silent)[0]
    start_idx = max(0, indices[0] - int(0.1 * len(audio)))  # Keep 10% padding
    end_idx = min(len(audio), indices[-1] + int(0.1 * len(audio)))
    
    return audio[start_idx:end_idx]

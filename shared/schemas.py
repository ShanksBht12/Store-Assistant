"""
Shared data schemas for all services (STT, LLM, TTS).
These define the Section 4 contracts from the project plan.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ===== STT Service Schemas =====
class STTRequest(BaseModel):
    """Request for speech-to-text transcription."""
    audio_base64: str = Field(..., description="Base64-encoded audio bytes")
    sample_rate: int = Field(16000, description="Audio sample rate in Hz")
    language: str = Field("ne", description="Language code (ne=Nepali, en=English)")


class STTResponse(BaseModel):
    """Response from speech-to-text transcription."""
    text: str = Field(..., description="Transcribed text")
    confidence: Optional[float] = Field(None, description="Confidence score (0-1)")
    duration_ms: Optional[int] = Field(None, description="Processing duration in milliseconds")


# ===== LLM Service Schemas =====
class ToolCall(BaseModel):
    """Details of a single tool call made by the LLM."""
    name: str
    args: Dict[str, Any]
    result: Any


class LLMRequest(BaseModel):
    """Request for LLM chat processing."""
    text: str = Field(..., description="User input text")
    session_id: str = Field(..., description="Session identifier for conversation history")
    language: str = Field("ne", description="Language code")


class LLMResponse(BaseModel):
    """Response from LLM chat processing."""
    reply_text: str = Field(..., description="LLM's reply text")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tool calls made during processing")
    session_id: str = Field(..., description="Session identifier")


# ===== TTS Service Schemas =====
class TTSRequest(BaseModel):
    """Request for text-to-speech synthesis."""
    text: str = Field(..., description="Text to synthesize")
    language: str = Field("ne", description="Language code")
    voice: Optional[str] = Field(None, description="Voice ID (provider-specific)")


class TTSResponse(BaseModel):
    """Response from text-to-speech synthesis."""
    audio_base64: str = Field(..., description="Base64-encoded audio data")
    format: str = Field("mp3", description="Audio format (mp3/wav)")
    duration_ms: Optional[int] = Field(None, description="Audio duration in milliseconds")


# ===== Health Check Schema =====
class HealthResponse(BaseModel):
    """Health/readiness check response."""
    status: str = Field(..., description="Service status: ready, loading, error")
    message: Optional[str] = Field(None, description="Additional status details")
    model_loaded: bool = Field(False, description="Whether the model is fully loaded")

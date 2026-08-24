"""
STT Service - FastAPI application for speech-to-text transcription.
Supports multiple STT providers (IndicConformer, SraVaani) via config.
"""
import os
import sys
import base64
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directories to path for imports
service_dir = Path(__file__).parent
project_root = service_dir.parent.parent
sys.path.insert(0, str(project_root))

from shared.schemas import STTRequest, STTResponse, HealthResponse
from services.stt_service.providers import get_stt_provider, list_providers
from services.stt_service.audio_utils import normalize_audio, trim_silence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
stt_provider = None
app_config = None
model_loading = True


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = project_root / "config" / "config.yaml"
    
    logger.info(f"Loading config from: {config_path}")
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {config_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in config file: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for model loading."""
    global stt_provider, app_config, model_loading
    
    logger.info("=" * 60)
    logger.info("STT Service starting up...")
    logger.info("=" * 60)
    
    try:
        # Load configuration
        app_config = load_config()
        
        # Get STT provider from config
        provider_name = app_config.get("stt", {}).get("provider", "unknown")
        logger.info(f"Configured STT provider: {provider_name}")
        logger.info(f"Available providers: {', '.join(list_providers())}")
        
        # Load the STT model
        logger.info("Loading STT model... (this may take ~3 minutes)")
        stt_provider = get_stt_provider(app_config)
        
        model_loading = False
        logger.info("=" * 60)
        logger.info("✓ STT Service ready!")
        logger.info(f"✓ Provider: {provider_name}")
        logger.info(f"✓ Model loaded successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        model_loading = False
        logger.error(f"Failed to initialize STT service: {e}", exc_info=True)
        raise
    
    yield
    
    # Cleanup
    logger.info("STT Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="STT Service",
    description="Speech-to-Text service with pluggable providers",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
async def root():
    """Root endpoint with service info."""
    return {
        "service": "STT Service",
        "version": "1.0.0",
        "status": "running",
        "provider": app_config.get("stt", {}).get("provider") if app_config else None
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Returns 'loading' during model initialization, 'ready' when complete.
    """
    if model_loading:
        return HealthResponse(
            status="loading",
            message="Model is still loading, please wait...",
            model_loaded=False
        )
    
    if stt_provider is None:
        return HealthResponse(
            status="error",
            message="STT provider failed to initialize",
            model_loaded=False
        )
    
    return HealthResponse(
        status="ready",
        message="Service is ready to accept requests",
        model_loaded=stt_provider.is_loaded()
    )


@app.get("/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check():
    """
    Readiness probe for container orchestration.
    Returns 503 if not ready.
    """
    health = await health_check()
    
    if health.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health.message
        )
    
    return health


@app.post("/stt/transcribe", response_model=STTResponse, tags=["STT"])
async def transcribe(request: STTRequest):
    """
    Transcribe audio to text.
    
    Accepts base64-encoded audio in any common format (wav, mp3, etc.).
    Returns transcribed text with confidence and timing metadata.
    """
    if model_loading:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is still loading. Please try again in a moment."
        )
    
    if stt_provider is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STT provider not initialized"
        )
    
    try:
        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(request.audio_base64)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 audio data: {e}"
            )
        
        logger.info(f"Received audio: {len(audio_bytes)} bytes, {request.sample_rate}Hz")
        
        # Normalize audio to target sample rate and mono
        target_sr = app_config.get("stt", {}).get(
            app_config.get("stt", {}).get("provider"),
            {}
        ).get("sample_rate", 16000)
        
        audio_array, sample_rate = normalize_audio(
            audio_bytes,
            target_sample_rate=target_sr,
            target_channels=1
        )
        
        # Apply simple silence trimming
        audio_array = trim_silence(audio_array)
        
        logger.info(f"Normalized audio: {len(audio_array)} samples at {sample_rate}Hz")
        
        # Transcribe
        result = stt_provider.transcribe(audio_array, sample_rate)
        
        logger.info(f"Transcription result: '{result['text']}'")
        
        return STTResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )


@app.get("/providers", tags=["Info"])
async def get_providers():
    """List all available STT providers."""
    return {
        "providers": list_providers(),
        "active": app_config.get("stt", {}).get("provider") if app_config else None
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or default to 8001
    port = int(os.environ.get("STT_PORT", 8001))
    
    logger.info(f"Starting STT service on port {port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )

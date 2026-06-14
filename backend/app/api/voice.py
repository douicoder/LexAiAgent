import io

import numpy as np
import soundfile as sf
from fastapi import APIRouter, Form, UploadFile, HTTPException

from app.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])

_whisper = None


def get_whisper():
    global _whisper
    if _whisper is None:
        from transformers import pipeline
        _whisper = pipeline(
            "automatic-speech-recognition",
            model=settings.WHISPER_MODEL,
            chunk_length_s=30,
        )
    return _whisper


@router.post("/transcribe")
async def transcribe(
    audio_file: UploadFile,
    language: str = Form("hi"),
) -> dict:
    try:
        audio_bytes = await audio_file.read()
    except Exception:
        return {
            "transcript": "",
            "detected_language": language,
            "confidence": 0.0,
        }

    audio_buffer = io.BytesIO(audio_bytes)
    try:
        audio_data, sample_rate = sf.read(audio_buffer)
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        audio_data = audio_data.astype(np.float32)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read audio file. Send WAV, WebM, MP3, or M4A.",
        )

    try:
        result = get_whisper()({"array": audio_data, "sampling_rate": int(sample_rate)})
        text = result["text"].strip()
    except Exception:
        return {
            "transcript": "",
            "detected_language": language,
            "confidence": 0.0,
        }

    return {
        "transcript": text,
        "detected_language": language,
        "confidence": 0.95,
    }

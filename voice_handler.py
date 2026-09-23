"""
voice_handler.py - Multimodal Voice & Audio Processing for ResearchAI Telegram Bot.
Transcribes voice messages (.oga / .ogg) across English, Hindi, Telugu, Arabic, Urdu,
and other languages using Gemini Multimodal Audio API.
"""

import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger("ResearchAI.Voice")


def transcribe_voice_message(
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    api_key: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribes audio bytes into text using Google Gemini Multimodal Audio capabilities.
    Returns (transcribed_text, detected_language_code).
    """
    if not audio_bytes or len(audio_bytes) < 100:
        return None, None

    prompt = (
        "Listen carefully to this audio recording. "
        "1. Transcribe the spoken audio EXACTLY as spoken without summarizing or omitting words. "
        "2. Identify the spoken language (e.g. English, Hindi, Telugu, Arabic, Urdu). "
        "Return strictly in this exact format:\n"
        "LANGUAGE: <en|hi|te|ar|ur|other>\n"
        "TRANSCRIPT: <transcribed text here>"
    )

    candidate_models = ["gemini-flash-latest", "gemma-4-26b-a4b-it", "gemini-2.5-flash"]

    for m in candidate_models:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            audio_part = types.Part.from_bytes(
                data=audio_bytes,
                mime_type=mime_type,
            )
            response = client.models.generate_content(
                model=m,
                contents=[audio_part, prompt],
            )
            if response and response.text:
                text = response.text.strip()
                lang = "en"
                transcript = text

                if "TRANSCRIPT:" in text:
                    parts = text.split("TRANSCRIPT:", 1)
                    header = parts[0]
                    transcript = parts[1].strip()
                    if "LANGUAGE:" in header:
                        raw_lang = header.split("LANGUAGE:", 1)[1].strip().lower()
                        for code in ["en", "hi", "te", "ar", "ur"]:
                            if code in raw_lang:
                                lang = code
                                break

                return transcript, lang
        except Exception as e_new:
            logger.debug(f"Audio transcription model {m} error: {e_new}")

        try:
            import google.generativeai as genai_classic
            genai_classic.configure(api_key=api_key)
            model = genai_classic.GenerativeModel(model_name=m)
            audio_blob = {
                "mime_type": mime_type,
                "data": audio_bytes,
            }
            response = model.generate_content([audio_blob, prompt])
            if response and response.text:
                text = response.text.strip()
                lang = "en"
                transcript = text
                if "TRANSCRIPT:" in text:
                    parts = text.split("TRANSCRIPT:", 1)
                    transcript = parts[1].strip()
                    header = parts[0]
                    if "LANGUAGE:" in header:
                        raw_lang = header.split("LANGUAGE:", 1)[1].strip().lower()
                        for code in ["en", "hi", "te", "ar", "ur"]:
                            if code in raw_lang:
                                lang = code
                                break
                return transcript, lang
        except Exception as e_classic:
            logger.debug(f"Classic model {m} audio transcription error: {e_classic}")

    return None, None

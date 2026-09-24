"""Server-side speech-to-text adapter for short Assistant recordings.

Audio is passed through memory to the configured OpenAI-compatible provider. It is never
written to Cocoon's database or filesystem, and is not included in application logs.
"""

import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import HTTPException, status

from app.core.config import get_settings

MAX_VOICE_BYTES = 8 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = frozenset({"audio/mp4", "audio/m4a", "audio/webm", "audio/wav"})


def transcription_is_configured() -> bool:
    settings = get_settings()
    return bool(settings.stt_api_url and settings.stt_model)


def _multipart_body(audio: bytes, content_type: str) -> tuple[bytes, str]:
    """Build the small OpenAI-compatible multipart request without storing the file."""
    boundary = f"----CocoonVoice{uuid.uuid4().hex}"
    extension = {"audio/mp4": "m4a", "audio/m4a": "m4a", "audio/webm": "webm", "audio/wav": "wav"}[
        content_type
    ]
    chunks = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="model"\r\n\r\n',
        get_settings().stt_model.encode(),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        (
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="cocoon-voice.{extension}"\r\n'
            ).encode()
            + f"Content-Type: {content_type}\r\n\r\n".encode()
        ),
        audio,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


def transcribe_audio(audio: bytes, content_type: str) -> str:
    """Return an OpenAI-compatible transcription or an explicit safe service error."""
    if not transcription_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La transcription vocale n’est pas configurée.",
        )
    if not audio:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Audio vide.")
    if len(audio) > MAX_VOICE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="L’enregistrement est trop long. Réessayez avec un message plus court.",
        )
    if content_type not in SUPPORTED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Ce format audio n’est pas pris en charge.",
        )

    settings = get_settings()
    body, boundary = _multipart_body(audio, content_type)
    request = UrlRequest(
        settings.stt_api_url.rstrip("/") + "/audio/transcriptions",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **({"Authorization": f"Bearer {settings.stt_api_key}"} if settings.stt_api_key else {}),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.stt_timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["text"]
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La transcription vocale est momentanément indisponible.",
        ) from error
    if not isinstance(text, str) or not (normalized := " ".join(text.split())):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="La transcription vocale est inexploitable. Réessayez.",
        )
    return normalized[:5000]

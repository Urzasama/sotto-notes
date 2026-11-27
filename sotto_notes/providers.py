"""Transcription providers.

The default engine is faster-whisper running locally on the CPU with int8
quantisation. A single optional OpenAI-compatible cloud adapter is included;
it stays disabled until an API key is configured.

Adding another backend means implementing :class:`Provider` and registering it
in :data:`PROVIDERS`.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import config


class TranscriptionError(RuntimeError):
    """Raised when a provider cannot produce a transcript."""


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = "S1"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Transcript:
    segments: list[Segment]
    language: str | None
    duration: float
    provider: str
    model: str


ProgressFn = Callable[[float], None]


class Provider:
    """Base class / interface for transcription backends."""

    id = "base"
    label = "Base"
    model = ""

    def status(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "available": False,
            "detail": "Not implemented",
            "model": self.model,
        }

    def transcribe(self, audio_path: Path, on_progress: ProgressFn) -> Transcript:
        raise NotImplementedError


def probe_duration(path: Path) -> float:
    """Best-effort duration in seconds using ffprobe, if it happens to exist."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return max(0.0, float(result.stdout.strip()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


class LocalWhisperProvider(Provider):
    """faster-whisper, CPU int8. The model is downloaded on first use."""

    id = "local"
    label = "Local (faster-whisper)"
    model = config.WHISPER_MODEL

    _model = None
    _lock = threading.Lock()

    @classmethod
    def load_model(cls):
        if cls._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on install
                raise TranscriptionError(
                    "faster-whisper is not installed. Run: "
                    "pip install -r requirements.txt"
                ) from exc
            with cls._lock:
                if cls._model is None:
                    try:
                        cls._model = WhisperModel(
                            config.WHISPER_MODEL,
                            device=config.WHISPER_DEVICE,
                            compute_type=config.WHISPER_COMPUTE_TYPE,
                        )
                    except Exception as exc:  # noqa: BLE001 - surface to the UI
                        raise TranscriptionError(
                            "Could not load the faster-whisper model "
                            f"'{config.WHISPER_MODEL}'. The first run downloads "
                            "it from Hugging Face, so an internet connection is "
                            f"required once. Original error: {exc}"
                        ) from exc
        return cls._model

    def status(self) -> dict:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return {
                "id": self.id,
                "label": self.label,
                "available": False,
                "detail": "faster-whisper is not installed",
                "model": config.WHISPER_MODEL,
            }
        return {
            "id": self.id,
            "label": self.label,
            "available": True,
            "detail": (
                f"CPU / {config.WHISPER_COMPUTE_TYPE}; first run downloads "
                f"the '{config.WHISPER_MODEL}' model"
            ),
            "model": config.WHISPER_MODEL,
        }

    def transcribe(self, audio_path: Path, on_progress: ProgressFn) -> Transcript:
        whisper = self.load_model()
        on_progress(0.02)
        try:
            raw_segments, info = whisper.transcribe(
                str(audio_path),
                language=config.WHISPER_LANGUAGE,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
        except Exception as exc:  # noqa: BLE001 - message goes to the UI
            raise TranscriptionError(f"Whisper failed: {exc}") from exc

        duration = float(getattr(info, "duration", 0.0) or 0.0)
        if duration <= 0:
            duration = probe_duration(audio_path)

        segments: list[Segment] = []
        for item in raw_segments:
            text = (item.text or "").strip()
            if not text:
                continue
            segments.append(
                Segment(start=float(item.start), end=float(item.end), text=text)
            )
            if duration > 0:
                on_progress(min(0.99, max(0.02, float(item.end) / duration)))

        language = getattr(info, "language", None) or config.WHISPER_LANGUAGE
        return Transcript(
            segments=segments,
            language=language,
            duration=duration,
            provider=self.id,
            model=config.WHISPER_MODEL,
        )


class OpenAICompatibleProvider(Provider):
    """Optional cloud adapter for an OpenAI-compatible transcription endpoint."""

    id = "cloud"
    label = "Cloud (OpenAI-compatible)"
    model = config.CLOUD_MODEL

    def status(self) -> dict:
        configured = bool(config.CLOUD_API_KEY)
        return {
            "id": self.id,
            "label": self.label,
            "available": configured,
            "detail": (
                f"{config.CLOUD_MODEL} at {config.CLOUD_BASE_URL}"
                if configured
                else "Set SOTTO_CLOUD_API_KEY to enable"
            ),
            "model": config.CLOUD_MODEL,
        }

    def _multipart(self, audio_path: Path) -> tuple[bytes, str]:
        boundary = "----sotto" + uuid.uuid4().hex
        mime = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        parts: list[bytes] = []

        def text_part(name: str, value: str) -> None:
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            )

        text_part("model", config.CLOUD_MODEL)
        text_part("response_format", "verbose_json")
        text_part("timestamp_granularities[]", "segment")
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{audio_path.name}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
        )
        parts.append(audio_path.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def transcribe(self, audio_path: Path, on_progress: ProgressFn) -> Transcript:
        if not config.CLOUD_API_KEY:
            raise TranscriptionError(
                "The cloud provider is disabled. Set SOTTO_CLOUD_API_KEY first."
            )
        body, content_type = self._multipart(audio_path)
        request = urllib.request.Request(
            f"{config.CLOUD_BASE_URL}/audio/transcriptions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {config.CLOUD_API_KEY}",
                "Content-Type": content_type,
            },
        )
        on_progress(0.15)
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise TranscriptionError(
                f"Cloud request failed ({exc.code}): {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise TranscriptionError(f"Cloud request failed: {exc}") from exc

        on_progress(0.95)
        raw_segments = payload.get("segments") or []
        segments = [
            Segment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=(item.get("text") or "").strip(),
            )
            for item in raw_segments
            if (item.get("text") or "").strip()
        ]
        duration = float(payload.get("duration") or 0.0)
        if not segments:
            text = (payload.get("text") or "").strip()
            if text:
                segments = [Segment(start=0.0, end=duration, text=text)]
        if not segments:
            raise TranscriptionError("The cloud provider returned no text.")
        return Transcript(
            segments=segments,
            language=payload.get("language"),
            duration=duration or probe_duration(audio_path),
            provider=self.id,
            model=config.CLOUD_MODEL,
        )


PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in (LocalWhisperProvider(), OpenAICompatibleProvider())
}

DEFAULT_PROVIDER = os.environ.get("SOTTO_PROVIDER", "local")


def get_provider(provider_id: str | None) -> Provider:
    provider = PROVIDERS.get(provider_id or DEFAULT_PROVIDER)
    if provider is None:
        raise TranscriptionError(f"Unknown provider: {provider_id}")
    return provider

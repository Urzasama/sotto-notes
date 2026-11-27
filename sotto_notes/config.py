"""Runtime configuration, all through environment variables."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
STATIC_DIR = PROJECT_DIR / "static"

HOST = os.environ.get("SOTTO_HOST", "127.0.0.1")
PORT = int(os.environ.get("SOTTO_PORT", "8765"))

#: Where notes, audio and the job scratch space live.
DATA_DIR = Path(
    os.environ.get("SOTTO_DATA_DIR")
    or (Path.home() / ".sotto-notes")
).expanduser()

NOTES_DIR = DATA_DIR / "notes"
AUDIO_DIR = DATA_DIR / "audio"
TMP_DIR = DATA_DIR / "tmp"

#: Upper bound for one uploaded file (512 MiB).
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

#: Local engine defaults.
WHISPER_MODEL = os.environ.get("SOTTO_WHISPER_MODEL", "tiny")
WHISPER_DEVICE = os.environ.get("SOTTO_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("SOTTO_WHISPER_COMPUTE", "int8")
WHISPER_LANGUAGE = os.environ.get("SOTTO_LANGUAGE") or None

#: Optional OpenAI-compatible cloud adapter. Disabled unless a key is set.
CLOUD_API_KEY = os.environ.get("SOTTO_CLOUD_API_KEY", "")
CLOUD_BASE_URL = os.environ.get(
    "SOTTO_CLOUD_BASE_URL", "https://api.openai.com/v1"
).rstrip("/")
CLOUD_MODEL = os.environ.get("SOTTO_CLOUD_MODEL", "whisper-1")

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".opus", ".flac", ".webm", ".aac",
}


def ensure_dirs() -> None:
    for directory in (DATA_DIR, NOTES_DIR, AUDIO_DIR, TMP_DIR):
        directory.mkdir(parents=True, exist_ok=True)

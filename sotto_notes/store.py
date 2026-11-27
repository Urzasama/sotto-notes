"""On-disk note library: one JSON document + one audio file per note."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .providers import Segment, Transcript

ID_RE = re.compile(r"^[0-9a-f]{12}$")
NOTE_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    )
    try:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    finally:
        if not handle.closed:
            handle.close()
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def note_path(note_id: str) -> Path:
    if not ID_RE.match(note_id or ""):
        raise ValueError("Invalid note id")
    return config.NOTES_DIR / f"{note_id}.json"


def audio_path_for(note: dict) -> Path:
    name = Path(note.get("audio", "")).name
    if not name:
        raise ValueError("Note has no audio file")
    return config.AUDIO_DIR / name


def title_from_filename(filename: str) -> str:
    stem = Path(filename or "Untitled").stem.strip()
    return (stem[:120] or "Untitled")


def new_note_id() -> str:
    return uuid.uuid4().hex[:12]


def build_note(
    *,
    note_id: str,
    original_filename: str,
    audio_filename: str,
    transcript: Transcript,
) -> dict:
    now = _now()
    return {
        "version": NOTE_VERSION,
        "id": note_id,
        "title": title_from_filename(original_filename),
        "source_filename": Path(original_filename).name,
        "audio": audio_filename,
        "duration": round(float(transcript.duration or 0.0), 3),
        "language": transcript.language,
        "provider": transcript.provider,
        "model": transcript.model,
        "created_at": now,
        "updated_at": now,
        "speakers": {},
        "segments": [segment.to_dict() for segment in transcript.segments],
    }


def save_note(note: dict) -> None:
    note["updated_at"] = _now()
    _atomic_write(
        note_path(note["id"]),
        json.dumps(note, ensure_ascii=False, indent=2),
    )


def load_note(note_id: str) -> dict | None:
    try:
        path = note_path(note_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_notes() -> list[dict]:
    summaries: list[dict] = []
    if not config.NOTES_DIR.exists():
        return summaries
    for path in config.NOTES_DIR.glob("*.json"):
        try:
            note = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        summaries.append(
            {
                "id": note.get("id", path.stem),
                "title": note.get("title", "Untitled"),
                "source_filename": note.get("source_filename", ""),
                "duration": note.get("duration", 0),
                "language": note.get("language"),
                "created_at": note.get("created_at", ""),
                "updated_at": note.get("updated_at", ""),
                "segment_count": len(note.get("segments") or []),
            }
        )
    summaries.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return summaries


def delete_note(note_id: str) -> bool:
    note = load_note(note_id)
    if note is None:
        return False
    try:
        audio_path_for(note).unlink(missing_ok=True)
    except ValueError:
        pass
    note_path(note_id).unlink(missing_ok=True)
    return True


def _clean_text(value, limit: int = 20000) -> str:
    return str(value or "").strip()[:limit]


def _clean_time(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, number), 3) if math.isfinite(number) else 0.0


def apply_update(note: dict, payload: dict) -> dict:
    """Validate and merge an edit from the client into ``note``."""
    title = _clean_text(payload.get("title"), 200)
    if title:
        note["title"] = title

    speakers = payload.get("speakers")
    if isinstance(speakers, dict):
        cleaned: dict[str, str] = {}
        for key, value in list(speakers.items())[:20]:
            key = _clean_text(key, 12)
            label = _clean_text(value, 60)
            if key.startswith("S") and key[1:].isdigit() and label:
                cleaned[key] = label
        note["speakers"] = cleaned

    segments = payload.get("segments")
    if isinstance(segments, list):
        cleaned_segments = []
        for index, item in enumerate(segments[:20000]):
            if not isinstance(item, dict):
                continue
            start = _clean_time(item.get("start"))
            end = max(start, _clean_time(item.get("end")))
            text = _clean_text(item.get("text"))
            speaker = _clean_text(item.get("speaker"), 12)
            if speaker not in note.get("speakers", {}):
                speaker = ""
            segment_id = _clean_text(item.get("id"), 32) or f"seg{index}"
            cleaned_segments.append(
                {
                    "id": segment_id,
                    "start": start,
                    "end": end,
                    "text": text,
                    "speaker": speaker,
                }
            )
        note["segments"] = cleaned_segments
    return note


def make_segment_from_payload(item: dict) -> Segment:
    return Segment(
        start=_clean_time(item.get("start")),
        end=_clean_time(item.get("end")),
        text=_clean_text(item.get("text")),
        speaker=_clean_text(item.get("speaker"), 12),
    )

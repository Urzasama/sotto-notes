"""Markdown / SRT / plain-text exporters."""

from __future__ import annotations

import re
from datetime import datetime, timezone


def clock(seconds: float) -> str:
    """HH:MM:SS, clamped at zero."""
    total = max(0, int(float(seconds or 0)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def srt_time(seconds: float) -> str:
    total = max(0.0, float(seconds or 0))
    millis = int(round(total * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _speaker(note: dict, segment: dict) -> str:
    key = segment.get("speaker") or ""
    return note.get("speakers", {}).get(key, "")


def _meta_lines(note: dict) -> list[str]:
    engine = " ".join(
        part for part in (note.get("provider"), note.get("model")) if part
    )
    exported = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return [
        f"- **Source:** {note.get('source_filename') or 'unknown'}",
        f"- **Duration:** {clock(note.get('duration', 0))}",
        f"- **Language:** {note.get('language') or 'auto'}",
        f"- **Engine:** {engine or 'unknown'}",
        f"- **Segments:** {len(note.get('segments') or [])}",
        f"- **Exported:** {exported}",
    ]


def to_markdown(note: dict) -> str:
    lines = [f"# {note.get('title') or 'Untitled'}", ""]
    lines.extend(_meta_lines(note))
    lines.extend(["", "## Transcript", ""])
    for segment in note.get("segments") or []:
        speaker = _speaker(note, segment)
        label = f"[{clock(segment.get('start', 0))}]"
        if speaker:
            label += f" {speaker}"
        text = (segment.get("text") or "").strip()
        lines.append(f"**{label}**  ")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_text(note: dict) -> str:
    lines = [note.get("title") or "Untitled"]
    lines.append(f"Source: {note.get('source_filename') or 'unknown'}")
    lines.append(f"Duration: {clock(note.get('duration', 0))}")
    lines.append("")
    for segment in note.get("segments") or []:
        speaker = _speaker(note, segment)
        prefix = f"[{clock(segment.get('start', 0))}]"
        if speaker:
            prefix += f" {speaker}:"
        lines.append(f"{prefix} {(segment.get('text') or '').strip()}")
    return "\n".join(lines).rstrip() + "\n"


def to_srt(note: dict) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(note.get("segments") or [], start=1):
        start = srt_time(segment.get("start", 0))
        end = srt_time(segment.get("end", segment.get("start", 0)))
        speaker = _speaker(note, segment)
        text = (segment.get("text") or "").strip()
        if speaker:
            text = f"{speaker}: {text}"
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


EXPORTERS = {
    "md": (to_markdown, "text/markdown; charset=utf-8", "md"),
    "srt": (to_srt, "application/x-subrip; charset=utf-8", "srt"),
    "txt": (to_text, "text/plain; charset=utf-8", "txt"),
}


def export(note: dict, fmt: str) -> tuple[str, str, str, str]:
    """Return ``(body, mime, extension, download_name)``."""
    if fmt not in EXPORTERS:
        raise ValueError(f"Unsupported format: {fmt}")
    builder, mime, extension = EXPORTERS[fmt]
    slug = re.sub(r"[^\w-]+", "-", (note.get("title") or "transcript").lower())
    slug = slug.strip("-")[:60] or "transcript"
    return builder(note), mime, extension, f"{slug}.{extension}"

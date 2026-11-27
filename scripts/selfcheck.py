#!/usr/bin/env python3
"""Self-check for sotto-notes.

Without arguments this verifies the repo layout, the exporters and the
provider registry. With ``--audio FILE`` it also runs a real transcription
through the local faster-whisper engine and prints the segments.

    python scripts/selfcheck.py
    python scripts/selfcheck.py --audio "C:\\path\\to\\clip.mp3"
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sotto_notes import __version__, config, export, store  # noqa: E402
from sotto_notes.providers import PROVIDERS, get_provider  # noqa: E402


def check_layout(failures: list[str]) -> None:
    before = len(failures)
    for name in ("index.html", "style.css", "app.js", "favicon.svg"):
        path = config.STATIC_DIR / name
        if not path.is_file():
            failures.append(f"missing static asset: {path}")
    for name in (
        "README.md", "LICENSE", "requirements.txt", "pyproject.toml",
        "run.bat", "run.ps1",
    ):
        if not (ROOT / name).is_file():
            failures.append(f"missing repo file: {name}")
    if len(failures) == before:
        print(f"[ok] layout ({len(list(config.STATIC_DIR.glob('*')))} static assets)")


def check_export(failures: list[str]) -> None:
    note = {
        "title": "self check",
        "source_filename": "check.mp3",
        "duration": 65.0,
        "language": "en",
        "provider": "local",
        "model": "tiny",
        "speakers": {"S1": "Tester"},
        "segments": [
            {
                "id": "one",
                "start": 0.0,
                "end": 2.5,
                "text": "hello from the self check",
                "speaker": "S1",
            }
        ],
    }
    for fmt in ("md", "srt", "txt"):
        body, _mime, _ext, _name = export.export(note, fmt)
        if "hello from the self check" not in body:
            failures.append(f"{fmt} export lost the segment text")
    if "[00:00:00] Tester: hello" not in export.to_text(note):
        failures.append("plain text export is missing timestamp/speaker")
    print("[ok] exporters (md, srt, txt)")


def check_providers(failures: list[str]) -> None:
    for provider in PROVIDERS.values():
        status = provider.status()
        flag = "ready" if status["available"] else "off"
        print(f"[{flag:5}] {status['label']}: {status['detail']}")
    if "local" not in PROVIDERS:
        failures.append("local provider is missing")


def run_audio(audio: Path, failures: list[str]) -> None:
    provider = get_provider("local")
    status = provider.status()
    if not status["available"]:
        failures.append(f"local provider unavailable: {status['detail']}")
        return
    seen: list[float] = []

    def progress(value: float) -> None:
        seen.append(value)
        print(f"  progress {int(value * 100):3d}%", flush=True)

    print(f"[..] transcribing {audio.name} with faster-whisper")
    transcript = provider.transcribe(audio, progress)
    print(f"[ok] language={transcript.language} duration={transcript.duration:.2f}s "
          f"segments={len(transcript.segments)}")
    for segment in transcript.segments:
        print(f"     [{segment.start:7.2f} -> {segment.end:7.2f}] {segment.text}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = (config.NOTES_DIR, config.AUDIO_DIR)
        config.NOTES_DIR = root / "notes"
        config.AUDIO_DIR = root / "audio"
        config.NOTES_DIR.mkdir()
        config.AUDIO_DIR.mkdir()
        try:
            note = store.build_note(
                note_id="ab12cd34ef56",
                original_filename=audio.name,
                audio_filename="ab12cd34ef56" + audio.suffix,
                transcript=transcript,
            )
            store.save_note(note)
            loaded = store.load_note("ab12cd34ef56")
            if loaded is None or not loaded["segments"]:
                failures.append("save/load roundtrip failed")
            markdown = export.to_markdown(loaded)
            print("[ok] note saved and exported to markdown:")
            for line in markdown.splitlines()[:6]:
                print(f"     {line}")
        finally:
            config.NOTES_DIR, config.AUDIO_DIR = original


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:  # pragma: no cover
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, help="run a real transcription")
    args = parser.parse_args()

    failures: list[str] = []
    print(f"sotto-notes {__version__} self-check")
    print(f"data dir: {config.DATA_DIR}")
    check_layout(failures)
    check_export(failures)
    check_providers(failures)
    if args.audio:
        if not args.audio.is_file():
            failures.append(f"audio file not found: {args.audio}")
        else:
            run_audio(args.audio, failures)

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

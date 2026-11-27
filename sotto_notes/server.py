"""Local web server: static UI, JSON API and the transcription job queue."""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import threading
import time
import urllib.parse
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, config, export, store
from .providers import PROVIDERS, TranscriptionError, get_provider

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class JobBoard:
    """A single background worker processes transcription jobs in order."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(
            target=self._work, name="sotto-transcriber", daemon=True
        )
        self._worker.start()

    def submit(
        self,
        *,
        job_id: str,
        note_id: str,
        provider_id: str,
        upload_path: Path,
        filename: str,
    ) -> str:
        job = {
            "id": job_id,
            "note_id": note_id,
            "provider": provider_id,
            "filename": filename,
            "upload_path": str(upload_path),
            "status": "queued",
            "stage": "Waiting for the transcriber",
            "progress": 0.0,
            "error": None,
            "created_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
        self._queue.put(job_id)
        return job_id

    def snapshot(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            public = {key: value for key, value in job.items() if key != "upload_path"}
            return public

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process(job_id)
            except Exception as exc:  # noqa: BLE001 - reported through the API
                self._update(
                    job_id,
                    status="error",
                    stage="Failed",
                    error=str(exc) or exc.__class__.__name__,
                )
            finally:
                self._queue.task_done()

    def _process(self, job_id: str) -> None:
        with self._lock:
            job = dict(self._jobs.get(job_id) or {})
        if not job:
            return
        upload_path = Path(job["upload_path"])
        target = None
        try:
            provider = get_provider(job["provider"])
            status = provider.status()
            if not status.get("available"):
                raise TranscriptionError(
                    status.get("detail") or "Provider unavailable"
                )

            self._update(
                job_id, status="running", stage="Loading the model", progress=0.01
            )

            def on_progress(value: float) -> None:
                value = max(0.01, min(0.99, float(value)))
                self._update(
                    job_id,
                    progress=round(value, 3),
                    stage=f"Transcribing - {int(value * 100)}%",
                )

            transcript = provider.transcribe(upload_path, on_progress)
            self._update(job_id, stage="Saving the note", progress=0.99)
            suffix = upload_path.suffix.lower()
            audio_name = f"{job['note_id']}{suffix}"
            target = config.AUDIO_DIR / audio_name
            os.replace(upload_path, target)
            note = store.build_note(
                note_id=job["note_id"],
                original_filename=job["filename"],
                audio_filename=audio_name,
                transcript=transcript,
            )
            store.save_note(note)
            self._update(
                job_id,
                status="done",
                stage="Done",
                progress=1.0,
                note_id=note["id"],
            )
        except Exception:
            upload_path.unlink(missing_ok=True)
            if target is not None:
                target.unlink(missing_ok=True)
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = f"sotto/{__version__}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- utilities
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[sotto] {self.address_string()} {fmt % args}")

    def _send_bytes(
        self,
        payload: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        extra_headers: dict | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status)

    def _read_json(self, limit: int = 4 * 1024 * 1024) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            raise ValueError("Empty request body")
        if length > limit:
            raise ValueError("Request body too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _path(self) -> tuple[str, dict]:
        parsed = urllib.parse.urlsplit(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    # ------------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        path, query = self._path()
        try:
            if path in ("/", "/index.html"):
                return self._serve_static("index.html")
            if path == "/favicon.ico":
                return self._serve_static("favicon.svg")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/api/health":
                return self._send_json(
                    {
                        "ok": True,
                        "version": __version__,
                        "data_dir": str(config.DATA_DIR),
                        "provider": os.environ.get("SOTTO_PROVIDER", "local"),
                    }
                )
            if path == "/api/providers":
                return self._send_json(
                    {"providers": [p.status() for p in PROVIDERS.values()]}
                )
            if path == "/api/notes":
                return self._send_json({"notes": store.list_notes()})
            if path.startswith("/api/notes/"):
                note_id = path.rsplit("/", 1)[-1]
                note = store.load_note(note_id)
                if note is None:
                    return self._error(HTTPStatus.NOT_FOUND, "Note not found")
                return self._send_json({"note": note})
            if path.startswith("/api/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                job = self.server.jobs.snapshot(job_id)
                if job is None:
                    return self._error(HTTPStatus.NOT_FOUND, "Job not found")
                return self._send_json({"job": job})
            if path.startswith("/api/export/"):
                return self._export(path.rsplit("/", 1)[-1], query)
            if path.startswith("/media/"):
                return self._serve_media(path[len("/media/"):])
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ------------------------------------------------------------------ POST
    def do_POST(self) -> None:  # noqa: N802
        path, _query = self._path()
        try:
            if path == "/api/transcribe":
                return self._upload()
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        except (BrokenPipeError, ConnectionResetError):
            return
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001 - turn into a JSON error
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    # ------------------------------------------------------------------- PUT
    def do_PUT(self) -> None:  # noqa: N802
        path, _query = self._path()
        try:
            if path.startswith("/api/notes/"):
                note_id = path.rsplit("/", 1)[-1]
                note = store.load_note(note_id)
                if note is None:
                    return self._error(HTTPStatus.NOT_FOUND, "Note not found")
                payload = self._read_json()
                store.apply_update(note, payload)
                store.save_note(note)
                return self._send_json({"note": note})
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---------------------------------------------------------------- DELETE
    def do_DELETE(self) -> None:  # noqa: N802
        path, _query = self._path()
        if path.startswith("/api/notes/"):
            note_id = path.rsplit("/", 1)[-1]
            if store.delete_note(note_id):
                return self._send_json({"ok": True})
            return self._error(HTTPStatus.NOT_FOUND, "Note not found")
        return self._error(HTTPStatus.NOT_FOUND, "Not found")

    # --------------------------------------------------------------- uploads
    def _upload(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return self._error(HTTPStatus.LENGTH_REQUIRED, "Content-Length required")
        if length > config.MAX_UPLOAD_BYTES:
            return self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "File is larger than 512 MiB"
            )

        raw_name = urllib.parse.unquote(self.headers.get("X-Filename") or "audio")
        filename = Path(raw_name).name[:200] or "audio"
        suffix = Path(filename).suffix.lower()
        if suffix not in config.SUPPORTED_EXTENSIONS:
            return self._error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                f"Unsupported audio type '{suffix or 'unknown'}'. "
                f"Supported: {', '.join(sorted(config.SUPPORTED_EXTENSIONS))}",
            )

        provider_id = self.headers.get("X-Provider") or "local"
        if provider_id not in PROVIDERS:
            return self._error(HTTPStatus.BAD_REQUEST, "Unknown provider")

        job_id = uuid.uuid4().hex[:12]
        upload_path = config.TMP_DIR / f"{job_id}{suffix}"
        remaining = length
        try:
            with upload_path.open("wb") as handle:
                while remaining > 0:
                    chunk = self.rfile.read(min(1024 * 256, remaining))
                    if not chunk:
                        raise ValueError("Upload interrupted")
                    handle.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            upload_path.unlink(missing_ok=True)
            raise

        self.server.jobs.submit(
            job_id=job_id,
            note_id=store.new_note_id(),
            provider_id=provider_id,
            upload_path=upload_path,
            filename=filename,
        )
        return self._send_json(
            {"job_id": job_id, "provider": provider_id},
            HTTPStatus.ACCEPTED,
        )

    # --------------------------------------------------------------- exports
    def _export(self, note_id: str, query: dict) -> None:
        note = store.load_note(note_id)
        if note is None:
            return self._error(HTTPStatus.NOT_FOUND, "Note not found")
        fmt = (query.get("format") or ["md"])[0]
        try:
            body, mime, _ext, name = export.export(note, fmt)
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", name) or "transcript.txt"
        disposition = (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{urllib.parse.quote(name)}"
        )
        self._send_bytes(
            body.encode("utf-8"),
            mime,
            extra_headers={"Content-Disposition": disposition},
        )

    # ---------------------------------------------------------------- static
    def _serve_static(self, relative: str) -> None:
        relative = relative.split("?", 1)[0]
        if not relative or relative.endswith("/"):
            relative += "index.html"
        candidate = (config.STATIC_DIR / relative).resolve()
        if config.STATIC_DIR.resolve() not in candidate.parents:
            return self._error(HTTPStatus.FORBIDDEN, "Forbidden")
        if not candidate.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "Not found")
        mime = STATIC_TYPES.get(
            candidate.suffix.lower(), "application/octet-stream"
        )
        self._send_bytes(
            candidate.read_bytes(),
            mime,
            extra_headers={"Cache-Control": "no-cache"},
        )

    # ----------------------------------------------------------------- media
    def _serve_media(self, note_id: str) -> None:
        note = store.load_note(note_id)
        if note is None:
            return self._error(HTTPStatus.NOT_FOUND, "Note not found")
        try:
            path = store.audio_path_for(note)
        except ValueError:
            return self._error(HTTPStatus.NOT_FOUND, "Audio missing")
        if not path.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "Audio missing")

        size = path.stat().st_size
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        status = HTTPStatus.OK
        extra_headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",
        }

        range_header = self.headers.get("Range")
        if range_header:
            match = RANGE_RE.match(range_header.strip())
            if match:
                begin, finish = match.groups()
                if begin:
                    start = int(begin)
                if finish:
                    end = min(int(finish), size - 1)
                if start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
                extra_headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        for key, value in extra_headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


class SottoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, Handler)
        self.jobs = JobBoard()


def serve(host: str = config.HOST, port: int = config.PORT) -> None:
    config.ensure_dirs()
    server = SottoServer((host, port))
    url = f"http://{host}:{port}"
    print(f"sotto-notes {__version__}")
    print(f"  open      {url}")
    print(f"  data dir  {config.DATA_DIR}")
    print(f"  engine    {config.WHISPER_MODEL} (faster-whisper, CPU)")
    print("  press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()

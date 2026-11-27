"""Note storage, validation and deletion."""

import tempfile
import unittest
from pathlib import Path

from sotto_notes import config, store
from sotto_notes.providers import Segment, Transcript


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self._original = (config.NOTES_DIR, config.AUDIO_DIR)
        config.NOTES_DIR = root / "notes"
        config.AUDIO_DIR = root / "audio"
        config.NOTES_DIR.mkdir(parents=True)
        config.AUDIO_DIR.mkdir(parents=True)

    def tearDown(self):
        config.NOTES_DIR, config.AUDIO_DIR = self._original

    def make_note(self):
        transcript = Transcript(
            segments=[
                Segment(start=0.5, end=3.0, text="Hello there."),
                Segment(start=3.0, end=6.5, text="Second line."),
            ],
            language="en",
            duration=6.5,
            provider="local",
            model="tiny",
        )
        note = store.build_note(
            note_id="abcdef123456",
            original_filename="My Recording.mp3",
            audio_filename="abcdef123456.mp3",
            transcript=transcript,
        )
        (config.AUDIO_DIR / "abcdef123456.mp3").write_bytes(b"fake-audio")
        return note

    def test_roundtrip(self):
        note = self.make_note()
        self.assertEqual(note["title"], "My Recording")
        store.save_note(note)
        loaded = store.load_note("abcdef123456")
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded["segments"]), 2)
        self.assertEqual(loaded["segments"][0]["text"], "Hello there.")
        self.assertTrue(store.audio_path_for(loaded).exists())

    def test_list_sorted_and_summarised(self):
        note = self.make_note()
        store.save_note(note)
        second = self.make_note()
        second["id"] = "abcdef123457"
        second["title"] = "Later note"
        store.save_note(second)
        listing = store.list_notes()
        self.assertEqual(len(listing), 2)
        self.assertTrue({"id", "title", "duration", "segment_count"}.issubset(listing[0]))

    def test_delete_removes_json_and_audio(self):
        note = self.make_note()
        store.save_note(note)
        self.assertTrue(store.delete_note(note["id"]))
        self.assertIsNone(store.load_note(note["id"]))
        self.assertFalse((config.AUDIO_DIR / "abcdef123456.mp3").exists())
        self.assertFalse(store.delete_note(note["id"]))

    def test_rejects_path_like_ids(self):
        self.assertIsNone(store.load_note("../../etc/passwd"))
        self.assertIsNone(store.load_note(""))
        with self.assertRaises(ValueError):
            store.note_path("../../etc/passwd")

    def test_apply_update_sanitises(self):
        note = self.make_note()
        note["speakers"] = {"S1": "Ada"}
        store.apply_update(
            note,
            {
                "title": "  New title  ",
                "speakers": {"S1": "Ada Lovelace", "S2": "", "bad": "x"},
                "segments": [
                    {
                        "id": "keep",
                        "start": -4,
                        "end": 1.5,
                        "text": "  Edited text  ",
                        "speaker": "S2",
                    },
                    {
                        "id": "ok",
                        "start": 2,
                        "end": 1,
                        "text": "clamped",
                        "speaker": "S1",
                    },
                ],
            },
        )
        self.assertEqual(note["title"], "New title")
        self.assertEqual(note["speakers"], {"S1": "Ada Lovelace"})
        self.assertEqual(len(note["segments"]), 2)
        first, second = note["segments"]
        self.assertEqual(first["start"], 0.0)
        self.assertEqual(first["end"], 1.5)
        self.assertEqual(first["text"], "Edited text")
        self.assertEqual(first["speaker"], "")  # S2 was dropped
        self.assertEqual(second["end"], 2.0)
        self.assertEqual(second["speaker"], "S1")

    def test_title_from_filename(self):
        self.assertEqual(store.title_from_filename("a/b/talk.wav"), "talk")
        self.assertEqual(store.title_from_filename(""), "Untitled")

    def test_new_ids_are_twelve_hex(self):
        note_id = store.new_note_id()
        self.assertEqual(len(note_id), 12)
        int(note_id, 16)


if __name__ == "__main__":
    unittest.main()

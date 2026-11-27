"""Provider registry and safe defaults."""

import unittest

from sotto_notes import config
from sotto_notes.providers import (
    PROVIDERS,
    LocalWhisperProvider,
    TranscriptionError,
    get_provider,
    probe_duration,
)


class ProviderTests(unittest.TestCase):
    def test_registry(self):
        self.assertIn("local", PROVIDERS)
        self.assertIn("cloud", PROVIDERS)
        self.assertIsInstance(PROVIDERS["local"], LocalWhisperProvider)

    def test_unknown_provider(self):
        with self.assertRaises(TranscriptionError):
            get_provider("nope")

    def test_cloud_disabled_without_key(self):
        original = config.CLOUD_API_KEY
        config.CLOUD_API_KEY = ""
        try:
            status = PROVIDERS["cloud"].status()
        finally:
            config.CLOUD_API_KEY = original
        self.assertFalse(status["available"])
        self.assertIn("SOTTO_CLOUD_API_KEY", status["detail"])

    def test_cloud_status_shape(self):
        status = PROVIDERS["cloud"].status()
        self.assertTrue({"id", "label", "available", "detail", "model"}.issubset(status))

    def test_cloud_without_key_raises(self):
        original = config.CLOUD_API_KEY
        config.CLOUD_API_KEY = ""
        try:
            with self.assertRaises(TranscriptionError):
                PROVIDERS["cloud"].transcribe(None, lambda _value: None)
        finally:
            config.CLOUD_API_KEY = original

    def test_probe_missing_file(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(probe_duration(Path(tmp) / "nope.mp3"), 0.0)


if __name__ == "__main__":
    unittest.main()

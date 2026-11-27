"""Export formats and timestamp arithmetic."""

import unittest

from sotto_notes import export


def sample_note():
    return {
        "id": "abc123def456",
        "title": "Morning stand-up",
        "source_filename": "standup.mp3",
        "duration": 3725.4,
        "language": "en",
        "provider": "local",
        "model": "tiny",
        "updated_at": "2026-11-27T11:00:00+00:00",
        "speakers": {"S1": "Ada", "S2": "Grace"},
        "segments": [
            {
                "id": "s1",
                "start": 5.0,
                "end": 12.5,
                "text": "Morning everyone.",
                "speaker": "S1",
            },
            {
                "id": "s2",
                "start": 65.25,
                "end": 70.0,
                "text": "The build is green.",
                "speaker": "S2",
            },
            {
                "id": "s3",
                "start": 3725.0,
                "end": 3725.4,
                "text": "That's all.",
                "speaker": "",
            },
        ],
    }


class ClockTests(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(export.clock(0), "00:00:00")
        self.assertEqual(export.clock(65.9), "00:01:05")
        self.assertEqual(export.clock(3725), "01:02:05")
        self.assertEqual(export.clock(-5), "00:00:00")

    def test_srt_time(self):
        self.assertEqual(export.srt_time(1.5), "00:00:01,500")
        self.assertEqual(export.srt_time(3725.123), "01:02:05,123")


class MarkdownTests(unittest.TestCase):
    def test_markdown_structure(self):
        body = export.to_markdown(sample_note())
        self.assertTrue(body.startswith("# Morning stand-up\n"))
        self.assertIn("- **Source:** standup.mp3", body)
        self.assertIn("- **Duration:** 01:02:05", body)
        self.assertIn("** [00:00:05] Ada**".replace(" ", ""), body.replace(" ", ""))
        self.assertIn("The build is green.", body)
        self.assertIn("## Transcript", body)
        self.assertTrue(body.endswith("\n"))


class TextTests(unittest.TestCase):
    def test_text_has_timestamps_and_speakers(self):
        body = export.to_text(sample_note())
        self.assertIn("[00:00:05] Ada: Morning everyone.", body)
        self.assertIn("[00:01:05] Grace: The build is green.", body)
        self.assertIn("[01:02:05] That's all.", body)


class SrtTests(unittest.TestCase):
    def test_srt_blocks(self):
        body = export.to_srt(sample_note())
        self.assertIn("1\n00:00:05,000 --> 00:00:12,500\nAda: Morning everyone.\n", body)
        self.assertIn("3\n01:02:05,000 --> 01:02:05,400\nThat's all.\n", body)

    def test_export_dispatch(self):
        for fmt, extension in (("md", "md"), ("srt", "srt"), ("txt", "txt")):
            body, mime, ext, name = export.export(sample_note(), fmt)
            self.assertTrue(body)
            self.assertTrue(mime)
            self.assertEqual(ext, extension)
            self.assertTrue(name.endswith("." + extension))
            self.assertIn("morning-stand-up", name)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            export.export(sample_note(), "pdf")


if __name__ == "__main__":
    unittest.main()

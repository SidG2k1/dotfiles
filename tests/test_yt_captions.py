import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "yt_captions", Path(__file__).resolve().parents[1] / "lib/yt-captions.py"
)
captions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(captions)


class CaptionsTests(unittest.TestCase):
    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["yt-captions", *args]), redirect_stdout(stdout), redirect_stderr(stderr):
            status = captions.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_browser_cookies_are_forwarded(self):
        with patch.object(captions, "YoutubeDL", side_effect=captions.DownloadError("Stop before network access")) as downloader:
            status, _, _ = self.run_cli(
                "--refresh", "--cookies-from-browser", "brave", "https://youtu.be/rmu0Ns8KGdw"
            )
        self.assertEqual(status, 1)
        self.assertEqual(downloader.call_args.args[0]["cookiesfrombrowser"], ("brave",))

    def test_cache_reuses_video_id_and_refreshes(self):
        url = "https://www.youtube.com/watch?v=rmu0Ns8KGdw"
        short_url = "https://youtu.be/rmu0Ns8KGdw?t=20"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(captions.tempfile, "gettempdir", return_value=directory), \
                patch.object(captions, "YoutubeDL") as downloader:
            ydl = downloader.return_value.__enter__.return_value
            ydl.extract_info.return_value = {
                "subtitles": {"en": [{"ext": "json3", "url": "https://example.invalid/captions"}]}
            }
            ydl.urlopen.side_effect = [
                io.BytesIO(json.dumps({"events": [{"segs": [{"utf8": text}]}]}).encode())
                for text in ("First transcript.", "Updated transcript.")
            ]
            first = self.run_cli(url)
            second = self.run_cli(short_url)
            self.assertEqual(first[:2], (0, "First transcript.\n"))
            self.assertEqual(second[:2], first[:2])
            self.assertEqual(downloader.call_count, 1)

            refreshed = self.run_cli("--refresh", url)
            self.assertEqual(refreshed[:2], (0, "Updated transcript.\n"))
            self.assertEqual(downloader.call_count, 2)
            self.assertEqual(self.run_cli(short_url)[:2], refreshed[:2])
            self.assertEqual(downloader.call_count, 2)

    def test_failed_refresh_preserves_cached_transcript(self):
        url = "https://www.youtube.com/watch?v=rmu0Ns8KGdw"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(captions.tempfile, "gettempdir", return_value=directory), \
                patch.object(captions, "YoutubeDL", side_effect=captions.DownloadError("Download failed")):
            cache = Path(directory) / "yt-captions" / "rmu0Ns8KGdw.transcript"
            cache.parent.mkdir()
            cache.write_text("Existing transcript.\n", encoding="utf-8")
            failed = self.run_cli("--refresh", url)
            self.assertEqual(failed[:2], (1, ""))
            self.assertIn("Download failed", failed[2])
            self.assertEqual(self.run_cli(url)[:2], (0, "Existing transcript.\n"))

    def test_manual_regional_english_beats_automatic_english(self):
        manual = {"ext": "json3", "url": "https://example.invalid/manual"}
        automatic = {"ext": "json3", "url": "https://example.invalid/automatic"}
        selected = captions.select_caption({
            "subtitles": {"en-GB": [manual]},
            "automatic_captions": {"en": [automatic], "en-orig": [automatic]},
        })
        self.assertEqual(selected, ("subtitles", "en-GB", manual))

    def test_automatic_original_then_english_translation(self):
        original = {"ext": "json3", "url": "https://example.invalid/original"}
        translated = {"ext": "json3", "url": "https://example.invalid/translation"}
        info = {
            "subtitles": {"fr": [original]},
            "automatic_captions": {"en": [translated], "en-orig": [original]},
        }
        self.assertEqual(captions.select_caption(info), ("automatic_captions", "en-orig", original))
        del info["automatic_captions"]["en-orig"]
        self.assertEqual(captions.select_caption(info), ("automatic_captions", "en", translated))

    def test_no_english_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "No English"):
            captions.select_caption({"subtitles": {"fr": [{"ext": "json3"}]}})

    def test_plain_text_preserves_spoken_repetition(self):
        data = {"events": [
            {"tStartMs": 0},
            {"segs": [{"utf8": "Hello"}, {"utf8": " &amp; welcome."}]},
            {"segs": [{"utf8": "\n"}]},
            {"segs": [{"utf8": "Again."}]},
            {"segs": [{"utf8": "Again."}]},
        ]}
        self.assertEqual(captions.caption_text(data), "Hello & welcome.\nAgain.\nAgain.")
        with self.assertRaisesRegex(ValueError, "empty"):
            captions.caption_text({"events": []})


if __name__ == "__main__":
    unittest.main()

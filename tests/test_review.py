import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "helpers" / "review.py"
SPEC = importlib.util.spec_from_file_location("video_use_review", MODULE_PATH)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


NOTES = {
    "video": "final.mp4",
    "fps": "24",
    "duration": 120.0,
    "notes": [
        {"id": 2, "t_in": 65.5, "t_out": None, "frame_in": 1572, "frame_out": None,
         "kind": "wrong", "text": "", "voice": None, "voice_text": None,
         "created": "2026-09-19T13:46:11"},
        {"id": 1, "t_in": 10.0, "t_out": 14.0, "frame_in": 240, "frame_out": 336,
         "kind": "cut", "text": "goes nowhere", "voice": None, "voice_text": None,
         "created": "2026-09-19T13:44:02"},
    ],
}


class FpsToFloatTests(unittest.TestCase):
    def test_converts_integer_decimal_and_rational_rates(self):
        self.assertAlmostEqual(review.fps_to_float("24"), 24.0)
        self.assertAlmostEqual(review.fps_to_float("29.97"), 29.97)
        self.assertAlmostEqual(review.fps_to_float("30000/1001"), 29.970029, places=5)

    def test_rejects_zero_and_garbage(self):
        for value in ("0", "", "nope", "1/0"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    review.fps_to_float(value)


class TimeToFrameTests(unittest.TestCase):
    def test_rounds_to_nearest_frame(self):
        fps = review.fps_to_float("30000/1001")
        self.assertEqual(review.time_to_frame(0.0, fps), 0)
        self.assertEqual(review.time_to_frame(1.0, fps), 30)
        self.assertEqual(review.time_to_frame(412.48, fps), 12362)

    def test_never_returns_negative(self):
        self.assertEqual(review.time_to_frame(-0.5, 24.0), 0)


class TimecodeTests(unittest.TestCase):
    def test_minutes_seconds_and_frames(self):
        self.assertEqual(review.format_timecode(0.0, 24.0), "0:00.00")
        self.assertEqual(review.format_timecode(65.5, 24.0), "1:05.12")

    def test_passes_an_hour(self):
        self.assertEqual(review.format_timecode(3661.0, 24.0), "61:01.00")


class RelativeVideoPathTests(unittest.TestCase):
    def test_default_layout_points_one_level_up(self):
        self.assertEqual(
            review.relative_video_path(Path("/e/final.mp4"), Path("/e/review")),
            "../final.mp4",
        )

    def test_same_directory(self):
        self.assertEqual(
            review.relative_video_path(Path("/e/final.mp4"), Path("/e")),
            "final.mp4",
        )

    def test_spaces_and_accents_are_percent_encoded(self):
        got = review.relative_video_path(
            Path("/Volumes/Lexar/Youtube Fede/citt\u00e0.mp4"),
            Path("/Volumes/Lexar/Youtube Fede/review"),
        )
        self.assertEqual(got, "../citt%C3%A0.mp4")

    def test_a_climbing_path_is_allowed_when_it_still_resolves(self):
        # Two volumes are reachable from each other on POSIX, and the climbing
        # path works in a file:// URL. There is nothing to refuse here.
        got = review.relative_video_path(
            Path("/Volumes/A/f.mp4"), Path("/Volumes/B/review")
        )
        self.assertEqual(got, "../../A/f.mp4")

    def test_refuses_a_path_it_cannot_express(self):
        # Windows drive letters: relpath raises rather than returning nonsense.
        with patch("os.path.relpath", side_effect=ValueError("different drive")):
            with self.assertRaises(ValueError):
                review.relative_video_path(
                    Path("/Volumes/A/f.mp4"), Path("/Volumes/B/review")
                )


class BuildPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _page(self, video_name="final.mp4"):
        video = self.root / video_name
        video.write_bytes(b"not really a video")
        out = self.root / "review"
        with patch.object(review, "probe_source_fps", return_value="24"), \
             patch.object(review, "probe_duration", return_value=12.5):
            return review.build_page(video, out), out

    def test_writes_the_page_and_injects_the_parameters(self):
        page, out = self._page()
        self.assertEqual(page, out / "final.html")
        params = review.read_params(page)
        self.assertEqual(params["video"], "../final.mp4")
        self.assertEqual(params["stem"], "final")
        self.assertEqual(params["fps"], "24")
        self.assertAlmostEqual(params["duration"], 12.5)

    def test_escapes_angle_brackets_so_a_path_cannot_close_the_script_tag(self):
        # A file name cannot hold a slash, so "</script>" cannot appear in one.
        # Escaping "<" is what stops any of its relatives from trying.
        page, _ = self._page("x<script>y.mp4")
        html = page.read_text(encoding="utf-8")
        injected = html.split(review.PARAMS_MARKER)[1][:400]
        self.assertNotIn("<script>", injected)
        self.assertIn("\\u003c", injected)
        self.assertEqual(review.read_params(page)["stem"], "x<script>y")

    def test_refuses_to_overwrite_a_notes_file(self):
        out = self.root / "review"
        out.mkdir()
        (out / "final.review.json").write_text('{"notes": []}')
        page, _ = self._page()
        self.assertTrue((out / "final.review.json").exists())
        self.assertEqual(
            json.loads((out / "final.review.json").read_text())["notes"], []
        )


class DumpNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "final.review.json"
        self.path.write_text(json.dumps(NOTES), encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_orders_by_time_not_by_id(self):
        out = review.dump_notes(self.path, transcribe=False)
        self.assertLess(out.index("0:10.00"), out.index("1:05.12"))

    def test_range_shows_both_ends_and_a_point_shows_one(self):
        out = review.dump_notes(self.path, transcribe=False)
        self.assertIn("0:10.00 - 0:14.00", out)
        self.assertIn("1:05.12", out)
        self.assertNotIn("1:05.12 -", out)

    def test_names_the_video_and_every_kind(self):
        out = review.dump_notes(self.path, transcribe=False)
        self.assertIn("final.mp4", out)
        self.assertIn("cut", out)
        self.assertIn("wrong", out)

    def test_carries_the_frame_numbers_through(self):
        out = review.dump_notes(self.path, transcribe=False)
        self.assertIn("240", out)
        self.assertIn("336", out)


class LoadNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "broken.review.json"
        self.addCleanup(self.tmp.cleanup)

    def test_truncated_file_fails_with_the_path_in_the_message(self):
        self.path.write_text('{"notes": [{"id": 1,', encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            review.load_notes(self.path)
        self.assertIn("broken.review.json", str(caught.exception))

    def test_a_file_that_is_not_a_review_is_rejected(self):
        self.path.write_text('{"hello": 1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            review.load_notes(self.path)

    def test_missing_file_fails_clearly(self):
        with self.assertRaises(FileNotFoundError):
            review.load_notes(self.path.parent / "nope.json")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "helpers" / "review.py"
SPEC = importlib.util.spec_from_file_location("video_use_review", MODULE_PATH)
assert SPEC and SPEC.loader
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


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


if __name__ == "__main__":
    unittest.main()

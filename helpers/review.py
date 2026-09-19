"""Review a rendered cut in the browser and read the notes back.

Two jobs, no server:

    python helpers/review.py <video>            generate the page and open it
    python helpers/review.py --dump <notes>     print the notes for the agent

The page is a plain file opened from disk. Measured on Chrome 153, a file://
page is a secure context, gets MediaRecorder and showDirectoryPicker, and seeks
150 s into a 380 MB local file in 201 ms. That last number is why there is no
server here: HTTP Range support was the only thing a server would have added.
"""

from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import parse_fps, probe_source_fps  # noqa: E402  same directory

KINDS = ("cut", "shorten", "lengthen", "wrong", "note")


def fps_to_float(canonical: str) -> float:
    """A frame rate as a number. Accepts what parse_fps accepts.

    parse_fps signals a bad rate with argparse.ArgumentTypeError, which is not a
    ValueError. Callers here are not a command line, so the error is translated
    rather than leaked.
    """
    try:
        rate = Fraction(parse_fps(canonical))
    except (argparse.ArgumentTypeError, ZeroDivisionError, TypeError) as exc:
        raise ValueError(f"not a usable frame rate: {canonical!r}") from exc
    return float(rate)


def time_to_frame(seconds: float, fps: float) -> int:
    """Which frame an instant falls on. A note that says 'cut' has to become a
    cut later, and that needs a frame, not a float."""
    return max(0, round(seconds * fps))


def format_timecode(seconds: float, fps: float) -> str:
    """m:ss.ff - the only thing the reviewer reads to orient themselves.

    Minutes are not wrapped into hours: a cut is discussed as '21:04', and a
    reviewer who sees '1:01:04' has to do arithmetic to find it in the EDL.
    """
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    whole = int(rest)
    frames = int(round((rest - whole) * fps))
    if frames >= round(fps):
        frames = 0
        whole += 1
        if whole >= 60:
            whole = 0
            minutes += 1
    return f"{minutes}:{whole:02d}.{frames:02d}"

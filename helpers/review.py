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
import json
import os
import subprocess
import sys
import webbrowser
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import parse_fps, probe_source_fps  # noqa: E402  same directory

KINDS = ("cut", "shorten", "lengthen", "wrong", "note")

TEMPLATE = Path(__file__).resolve().parent / "review.html"
PARAMS_MARKER = '<script id="review-params" type="application/json">'


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


def relative_video_path(video: Path, page_dir: Path) -> str:
    """How the page refers to the video, URL-encoded.

    Refuses instead of guessing when the two cannot be expressed relative to
    each other, which in practice means separate Windows drives. A <video> that
    silently fails to load is worse than a command that refuses to run, so the
    result is also walked back to the file it came from before it is returned.
    """
    video = video.resolve()
    page_dir = page_dir.resolve()
    try:
        rel = os.path.relpath(video, page_dir)
    except ValueError as exc:
        raise ValueError(
            f"cannot reach {video} from {page_dir}: put the page on the same volume"
        ) from exc
    if os.path.isabs(rel) or os.path.normpath(os.path.join(page_dir, rel)) != str(video):
        raise ValueError(f"cannot reach {video} from {page_dir}")
    return quote(Path(rel).as_posix())


def probe_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def read_params(page: Path) -> dict:
    """The parameter block back out of a generated page. Used by the tests and
    by anyone debugging a page that will not load."""
    html = page.read_text(encoding="utf-8")
    start = html.index(PARAMS_MARKER) + len(PARAMS_MARKER)
    return json.loads(html[start:html.index("</script>", start)])


def build_page(video: Path, out_dir: Path) -> Path:
    """Write the review page for a video. Returns its path."""
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"template missing: {TEMPLATE}")
    out_dir.mkdir(parents=True, exist_ok=True)

    params = {
        "video": relative_video_path(video, out_dir),
        "stem": video.stem,
        "fps": probe_source_fps(video) or "25",
        "duration": probe_duration(video),
    }
    # "<" becomes an escape so no path can close the script tag and turn the
    # parameter block into markup.
    blob = json.dumps(params, ensure_ascii=False).replace("<", "\\u003c")

    html = TEMPLATE.read_text(encoding="utf-8")
    start = html.index(PARAMS_MARKER) + len(PARAMS_MARKER)
    end = html.index("</script>", start)
    page = out_dir / f"{video.stem}.html"
    page.write_text(html[:start] + blob + html[end:], encoding="utf-8")
    return page

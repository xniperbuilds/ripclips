"""
RipClips - Step 3: download the full source video (best quality up to config
max_height, falling back to 720p). Subtitles are NOT downloaded here.

Usage:
    python 3_download/download_video.py "https://youtu.be/VIDEO_ID"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


def build_format(max_h):
    # try <=max_h, then <=720 as fallback, all merged to a single stream
    return (
        "bv*[height<=%d]+ba/b[height<=%d]/"
        "bv*[height<=720]+ba/b[height<=720]/b"
        % (max_h, max_h)
    )


def main():
    if len(sys.argv) < 2:
        rc.die('usage: python 3_download/download_video.py "YOUTUBE_URL"')
    url = sys.argv[1]
    cfg = rc.load_config()
    max_h = int(cfg.get("download", {}).get("max_height", 1080))

    rc.require_tool("yt-dlp")
    rc.require_tool("ffmpeg", hint="(needed to merge video+audio)")
    rc.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    out_tmpl = str(rc.DOWNLOAD_DIR / "%(title).120B [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", build_format(max_h),
        "--merge-output-format", "mp4",
        "-o", out_tmpl,
        url,
    ]
    rc.log("Downloading source video (<=%dp) ..." % max_h)
    result = rc.run(cmd)
    if result.returncode != 0:
        rc.die("yt-dlp download failed (exit %s)." % result.returncode)

    video = rc.find_source_video()
    size_mb = video.stat().st_size / (1024 * 1024)
    rc.log("[ok] downloaded: %s (%.1f MB)" % (video.name, size_mb))


if __name__ == "__main__":
    main()

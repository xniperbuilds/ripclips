"""
RipClips - Step 4: cut the full source video into clips using the time ranges
from 2_analysis/clip_durations.txt.

Usage:
    python 4_clip/cut_clips.py                 # all clips, accurate re-encode
    python 4_clip/cut_clips.py --mode copy     # fastest, keyframe-snapped
    python 4_clip/cut_clips.py --clip 2        # only clip 2
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


def cut(source, start, end, out_path, mode):
    dur = end - start
    if mode == "copy":
        # stream copy: fast, but cuts land on the nearest keyframe
        cmd = [
            "ffmpeg", "-y",
            "-ss", rc.format_timecode(start),
            "-i", str(source),
            "-t", "%.3f" % dur,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(out_path),
        ]
    else:
        # re-encode: accurate boundaries (input seeking after -i is frame-exact)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-ss", rc.format_timecode(start),
            "-t", "%.3f" % dur,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            str(out_path),
        ]
    result = rc.run(cmd)
    return result.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["reencode", "copy"], default=None)
    ap.add_argument("--clip", type=int, default=None, help="only this clip number")
    args = ap.parse_args()

    cfg = rc.load_config()
    mode = args.mode or cfg.get("clip", {}).get("encode_mode", "reencode")

    rc.require_tool("ffmpeg")
    source = rc.find_source_video()
    clips = rc.parse_clip_durations()
    rc.CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    if args.clip is not None:
        clips = [c for c in clips if c["index"] == args.clip]
        if not clips:
            rc.die("clip %d not found in clip_durations.txt" % args.clip)

    rc.log("Cutting %d clip(s) from %s (mode=%s)" % (len(clips), source.name, mode))
    ok = 0
    for c in clips:
        out_path = rc.CLIPS_DIR / rc.clip_name(c["index"])
        rc.log("-> clip %02d  %s - %s"
               % (c["index"], rc.format_timecode(c["start"], False),
                  rc.format_timecode(c["end"], False)))
        if cut(source, c["start"], c["end"], out_path, mode) and out_path.exists():
            ok += 1
        else:
            rc.log("   WARNING: clip %02d failed" % c["index"])

    rc.log("[ok] %d/%d clips written to %s" % (ok, len(clips), rc.CLIPS_DIR))
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

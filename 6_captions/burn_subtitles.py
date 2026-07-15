"""
RipClips - Step 6: burn styled subtitles into each vertical clip, producing the
final upload-ready clips.

Reads the .srt from step 1, trims + offsets cues to each clip's time window
(from step 2), builds a styled .ass, and burns it in with FFmpeg.

Usage:
    python 6_captions/burn_subtitles.py --style 1
    python 6_captions/burn_subtitles.py --style 4 --clip 2
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

_SRT_TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def parse_srt(path):
    cues = []
    block = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    for chunk in re.split(r"\n\s*\n", content):
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        time_line = None
        text_lines = []
        for ln in lines:
            if _SRT_TIME.search(ln):
                time_line = ln
            elif ln.strip().isdigit() and time_line is None:
                continue
            else:
                text_lines.append(ln)
        if not time_line:
            continue
        m = _SRT_TIME.search(time_line)
        start = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                 + int(m.group(3)) + int(m.group(4)) / 1000.0)
        end = (int(m.group(5)) * 3600 + int(m.group(6)) * 60
               + int(m.group(7)) + int(m.group(8)) / 1000.0)
        text = " ".join(text_lines)
        text = re.sub(r"<[^>]+>", "", text)          # html tags
        text = re.sub(r"\{\\[^}]*\}", "", text)       # ass overrides
        text = text.strip()
        if text and end > start:
            cues.append([start, end, text])
    return cues


def window_cues(cues, clip_start, clip_end):
    """Keep cues overlapping [clip_start, clip_end], offset to clip-local time."""
    out = []
    dur = clip_end - clip_start
    for s, e, t in cues:
        if e <= clip_start or s >= clip_end:
            continue
        ns = max(0.0, s - clip_start)
        ne = min(dur, e - clip_start)
        if ne > ns:
            out.append([ns, ne, t])
    return out


def split_words(cues):
    """Style 4: one word at a time, dividing each cue's duration equally."""
    out = []
    for s, e, t in cues:
        words = t.split()
        if not words:
            continue
        step = (e - s) / len(words)
        for i, w in enumerate(words):
            out.append([s + i * step, s + (i + 1) * step, w])
    return out


# ---------------------------------------------------------------------------
# ASS building
# ---------------------------------------------------------------------------

def ass_time(sec):
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def ass_escape(text):
    return (text.replace("{", "(").replace("}", ")")
            .replace("\\", "/").replace("\n", "\\N"))


# style -> V4+ Style line fields (colours are ASS &HAABBGGRR)
def style_def(style, font):
    fn = font or "Arial"
    # Name,Fontname,Fontsize,Primary,Secondary,Outline,Back,Bold,Italic,Under,
    # Strike,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Align,
    # MarginL,MarginR,MarginV,Encoding
    if style == 1:      # TikTok Classic - bold white, thick black outline
        return ("Default,%s,72,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
                "-1,0,0,0,100,100,0,0,1,5,0,2,60,60,300,1" % fn)
    if style == 2:      # Word Pop - yellow on dark box
        return ("Default,%s,66,&H0000FFFF,&H000000FF,&H9E000000,&H00000000,"
                "-1,0,0,0,100,100,0,0,3,10,0,2,80,80,320,1" % fn)
    if style == 3:      # Podcast Modern - clean white, soft shadow
        return ("Default,%s,62,&H00FFFFFF,&H000000FF,&H00202020,&H96000000,"
                "0,0,0,0,100,100,0,0,1,1,3,2,80,80,300,1" % fn)
    # style 4          # Word-by-Word - big bold karaoke pop
    return ("Default,%s,108,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
            "-1,0,0,0,100,100,0,0,1,6,0,2,60,60,650,1" % fn)


def build_ass(cues, style, font, width, height):
    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: %s\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n" % (width, height, style_def(style, font))
    )
    body = []
    for s, e, t in cues:
        body.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                     % (ass_time(s), ass_time(e), ass_escape(t)))
    return head + "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# burn
# ---------------------------------------------------------------------------

def burn(clip, ass_path, out_path, font_dir=None):
    esc = str(ass_path).replace("\\", "/").replace(":", "\\:")
    sub = "subtitles='%s'" % esc
    if font_dir:
        fd = str(font_dir).replace("\\", "/").replace(":", "\\:")
        sub += ":fontsdir='%s'" % fd
    cmd = [
        "ffmpeg", "-y", "-i", str(clip),
        "-vf", sub,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return rc.run(cmd).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", type=int, choices=[1, 2, 3, 4], default=None)
    ap.add_argument("--clip", type=int, default=None)
    args = ap.parse_args()

    cfg = rc.load_config()
    style = args.style or int(cfg.get("captions", {}).get("default_style", 1))
    font_cfg = cfg.get("captions", {}).get("font", "") or ""
    font_name, font_dir = "", None
    if font_cfg:
        fp = Path(font_cfg)
        if fp.exists():
            font_name = fp.stem
            font_dir = fp.parent

    rc.require_tool("ffmpeg")
    tw = int(cfg["reframe"]["width"])
    th = int(cfg["reframe"]["height"])

    srt = rc.find_srt()
    cues_all = parse_srt(srt)
    if not cues_all:
        rc.die("no subtitle cues parsed from %s" % srt.name)
    ranges = {c["index"]: c for c in rc.parse_clip_durations()}

    verticals = sorted(rc.VERTICAL_DIR.glob("clip_*.mp4"))
    if not verticals:
        rc.die("no vertical clips in %s (run step 5 first)." % rc.VERTICAL_DIR)
    if args.clip is not None:
        verticals = [v for v in verticals if v.stem == "clip_%02d" % args.clip]
        if not verticals:
            rc.die("clip %d not found." % args.clip)

    rc.CAPTIONED_DIR.mkdir(parents=True, exist_ok=True)
    rc.log("Burning captions  style=%d  clips=%d  (srt=%s)"
           % (style, len(verticals), srt.name))

    ok = 0
    for clip in verticals:
        idx = int(clip.stem.split("_")[1])
        rng = ranges.get(idx)
        if not rng:
            rc.log("   WARNING: no time range for clip %02d, skipping." % idx)
            continue
        cues = window_cues(cues_all, rng["start"], rng["end"])
        if style == 4:
            cues = split_words(cues)
        out_path = rc.CAPTIONED_DIR / clip.name
        if not cues:
            rc.log("-> clip %02d  no cues in window, copying as-is." % idx)
            import shutil
            shutil.copy2(clip, out_path)
            ok += 1
            continue

        ass_text = build_ass(cues, style, font_name, tw, th)
        with tempfile.NamedTemporaryFile("w", suffix=".ass", delete=False,
                                         encoding="utf-8") as tf:
            tf.write(ass_text)
            ass_path = tf.name

        rc.log("-> clip %02d  (%d cues)" % (idx, len(cues)))
        if burn(clip, ass_path, out_path, font_dir) and out_path.exists():
            ok += 1
        else:
            rc.log("   WARNING: burn failed for clip %02d" % idx)
        try:
            Path(ass_path).unlink()
        except OSError:
            pass

    rc.log("[ok] %d/%d final clips -> %s" % (ok, len(verticals), rc.CAPTIONED_DIR))
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

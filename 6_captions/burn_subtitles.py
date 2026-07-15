"""
RipClips - Step 6: burn styled subtitles into each vertical clip, producing the
final upload-ready clips.

Reads the .srt from step 1, trims + offsets cues to each clip's time window
(from step 2), builds a styled .ass, and burns it in with FFmpeg.

Captions are fully customizable via config.yaml -> captions: (font, size,
colors, position, bold, uppercase, margins) on top of 8 built-in style presets.

Usage:
    python 6_captions/burn_subtitles.py --style 1
    python 6_captions/burn_subtitles.py --style 5 --clip 2
    python 6_captions/burn_subtitles.py --style 1 --font "Montserrat" --size 84 \
        --color "#FFE94A" --uppercase
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


# ---------------------------------------------------------------------------
# Style presets  (mode: line = whole cue | word = one word | karaoke = line
# stays, active word highlighted).  Colors are plain hex; converted to ASS.
# ---------------------------------------------------------------------------

PRESETS = {
    1: {  # TikTok Classic - bold white, thick black outline
        "name": "TikTok Classic", "font": "Arial", "size": 72,
        "primary": "#FFFFFF", "outline": "#000000", "outline_w": 5,
        "shadow": 0, "bold": True, "box": False, "position": "bottom",
        "mode": "line",
    },
    2: {  # Word Pop - yellow text on a dark box
        "name": "Word Pop", "font": "Arial", "size": 64,
        "primary": "#FFE31A", "outline": "#000000", "outline_w": 6,
        "shadow": 0, "bold": True, "box": True, "box_color": "#000000CC",
        "position": "bottom", "mode": "line",
    },
    3: {  # Podcast Modern - clean white, soft drop shadow
        "name": "Podcast Modern", "font": "Arial", "size": 60,
        "primary": "#FFFFFF", "outline": "#202020", "outline_w": 1,
        "shadow": 3, "bold": False, "box": False, "position": "bottom",
        "mode": "line",
    },
    4: {  # Word-by-Word - big bold karaoke, one word at a time
        "name": "Word-by-Word", "font": "Arial", "size": 104,
        "primary": "#FFFFFF", "outline": "#000000", "outline_w": 6,
        "shadow": 0, "bold": True, "box": False, "position": "center",
        "mode": "word",
    },
    5: {  # Highlight Karaoke - line stays, active word lights up
        "name": "Highlight Karaoke", "font": "Arial", "size": 74,
        "primary": "#FFFFFF", "outline": "#000000", "outline_w": 5,
        "shadow": 0, "bold": True, "box": False, "highlight": "#FFE31A",
        "position": "bottom", "mode": "karaoke",
    },
    6: {  # Bold Yellow - big punchy yellow, thick outline
        "name": "Bold Yellow", "font": "Arial", "size": 86,
        "primary": "#FFE31A", "outline": "#000000", "outline_w": 7,
        "shadow": 0, "bold": True, "box": False, "position": "bottom",
        "mode": "line",
    },
    7: {  # Neon - bright cyan with dark outline
        "name": "Neon", "font": "Arial", "size": 74,
        "primary": "#22FFE7", "outline": "#062A2A", "outline_w": 5,
        "shadow": 2, "bold": True, "box": False, "position": "bottom",
        "mode": "line",
    },
    8: {  # Boxed Bar - white text on a solid brand-purple bar
        "name": "Boxed Bar", "font": "Arial", "size": 62,
        "primary": "#FFFFFF", "outline": "#6D28D9", "outline_w": 10,
        "shadow": 0, "bold": True, "box": True, "box_color": "#6D28D9E6",
        "position": "bottom", "mode": "line",
    },
}


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

_SRT_TIME = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def parse_srt(path):
    cues = []
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
        text = re.sub(r"\{\\[^}]*\}", "", text)       # stray ass overrides
        text = re.sub(r"\s+", " ", text).strip()
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
    """word mode: one word at a time, dividing each cue's duration equally."""
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
# Color + ASS helpers
# ---------------------------------------------------------------------------

def _hex_parts(h):
    """'#RGB' / '#RRGGBB' / '#RRGGBBAA' -> (r, g, b, opacity 0..255)."""
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "FF"                      # opaque
    if len(h) != 8:
        raise ValueError("bad color: %r" % h)
    r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    return r, g, b, a


def ass_color(h):
    """Hex -> ASS &HAABBGGRR (alpha inverted: opaque hex FF -> ass 00)."""
    r, g, b, a = _hex_parts(h)
    return "&H%02X%02X%02X%02X" % (255 - a, b, g, r)


def inline_c(h):
    """Hex -> inline \\c override &HBBGGRR& (no alpha)."""
    r, g, b, _ = _hex_parts(h)
    return "&H%02X%02X%02X&" % (b, g, r)


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


_ALIGN = {"bottom": 2, "center": 5, "middle": 5, "top": 8}


# ---------------------------------------------------------------------------
# Resolve preset + config/CLI overrides into one property dict
# ---------------------------------------------------------------------------

def resolve_style(style, cfg, cli):
    props = dict(PRESETS.get(style, PRESETS[1]))
    cap = cfg.get("captions", {}) or {}

    def pick(cli_val, cfg_key, prop_key, cast=lambda x: x):
        if cli_val not in (None, ""):
            props[prop_key] = cast(cli_val)
        elif cap.get(cfg_key) not in (None, "", 0):
            props[prop_key] = cast(cap.get(cfg_key))

    pick(cli.get("font"), "font", "font")
    pick(cli.get("size"), "size", "size", int)
    pick(cli.get("color"), "primary_color", "primary")
    pick(None, "outline_color", "outline")
    pick(None, "box_color", "box_color")
    pick(None, "highlight_color", "highlight")
    pick(None, "position", "position")
    if cli.get("outline_w") is not None:
        props["outline_w"] = int(cli["outline_w"])
    elif cap.get("outline_width", -1) not in (None, -1):
        props["outline_w"] = int(cap["outline_width"])
    if cap.get("bold") is not None:
        props["bold"] = bool(cap["bold"])
    props["uppercase"] = bool(cli.get("uppercase") or cap.get("uppercase", False))
    props["margin_pct"] = float(cap.get("margin_pct", 8) or 8)
    return props


def maybe_upper(text, props):
    return text.upper() if props.get("uppercase") else text


# ---------------------------------------------------------------------------
# ASS building
# ---------------------------------------------------------------------------

def style_line(props, width):
    fn = props.get("font") or "Arial"
    size = int(props.get("size", 72))
    primary = ass_color(props.get("primary", "#FFFFFF"))
    box = bool(props.get("box"))
    border_style = 3 if box else 1
    outline_col = ass_color(props.get("box_color", "#000000CC") if box
                            else props.get("outline", "#000000"))
    back_col = ass_color("#000000A0")          # shadow
    bold = -1 if props.get("bold", True) else 0
    outline_w = props.get("outline_w", 5)
    shadow = props.get("shadow", 0)
    align = _ALIGN.get(props.get("position", "bottom"), 2)
    margin = int(width * props.get("margin_pct", 8) / 100.0)
    # Name,Fontname,Fontsize,Primary,Secondary,Outline,Back,Bold,Italic,Under,
    # Strike,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Align,
    # MarginL,MarginR,MarginV,Encoding
    return ("Default,%s,%d,%s,&H000000FF,%s,%s,%d,0,0,0,100,100,0,0,%d,%d,%d,"
            "%d,%d,%d,%d,1"
            % (fn, size, primary, outline_col, back_col, bold, border_style,
               outline_w, shadow, align, margin, margin, margin))


def build_ass(cues, props, width, height):
    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: %s\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n" % (width, height, style_line(props, width))
    )
    body = []
    for s, e, t in cues:
        body.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
                     % (ass_time(s), ass_time(e), ass_escape(maybe_upper(t, props))))
    return head + "\n".join(body) + "\n"


def build_ass_karaoke(cues, props, width, height):
    """Line stays visible; the active word is recolored per time slice."""
    hi = inline_c(props.get("highlight", "#FFE31A"))
    base = inline_c(props.get("primary", "#FFFFFF"))
    events = []
    for s, e, text in cues:
        words = text.split()
        if not words:
            continue
        step = (e - s) / len(words)
        for i in range(len(words)):
            parts = []
            for j, w in enumerate(words):
                w = maybe_upper(w, props)
                if j == i:
                    parts.append("{\\c%s}%s{\\c%s}" % (hi, ass_escape(w), base))
                else:
                    parts.append(ass_escape(w))
            events.append([s + i * step, s + (i + 1) * step, " ".join(parts)])

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: %s\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n" % (width, height, style_line(props, width))
    )
    body = ["Dialogue: 0,%s,%s,Default,,0,0,0,,%s"
            % (ass_time(s), ass_time(e), t) for s, e, t in events]
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
    ap = argparse.ArgumentParser(description="Burn styled captions into clips.")
    ap.add_argument("--style", type=int, choices=list(PRESETS.keys()), default=None)
    ap.add_argument("--clip", type=int, default=None)
    ap.add_argument("--font", default=None, help="font family name or .ttf path")
    ap.add_argument("--size", type=int, default=None, help="base font size")
    ap.add_argument("--color", default=None, help="text color hex, e.g. #FFE94A")
    ap.add_argument("--outline-w", dest="outline_w", type=int, default=None)
    ap.add_argument("--uppercase", action="store_true")
    args = ap.parse_args()

    cfg = rc.load_config()
    style = args.style or int(cfg.get("captions", {}).get("default_style", 1))
    if style not in PRESETS:
        style = 1
    cli = {"font": args.font, "size": args.size, "color": args.color,
           "outline_w": args.outline_w, "uppercase": args.uppercase}
    props = resolve_style(style, cfg, cli)

    # font: name vs .ttf/.otf path
    font_dir = None
    fval = props.get("font") or ""
    fp = Path(fval)
    if fval and fp.suffix.lower() in (".ttf", ".otf") and fp.exists():
        font_dir = fp.parent
        props["font"] = fp.stem

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
    rc.log("Burning captions  style=%d (%s)  clips=%d  (srt=%s)"
           % (style, props["name"], len(verticals), srt.name))

    ok = 0
    for clip in verticals:
        idx = int(clip.stem.split("_")[1])
        rng = ranges.get(idx)
        if not rng:
            rc.log("   WARNING: no time range for clip %02d, skipping." % idx)
            continue
        cues = window_cues(cues_all, rng["start"], rng["end"])
        out_path = rc.CAPTIONED_DIR / clip.name
        if not cues:
            rc.log("-> clip %02d  no cues in window, copying as-is." % idx)
            import shutil
            shutil.copy2(clip, out_path)
            ok += 1
            continue

        mode = props.get("mode", "line")
        if mode == "karaoke":
            ass_text = build_ass_karaoke(cues, props, tw, th)
        else:
            if mode == "word":
                cues = split_words(cues)
            ass_text = build_ass(cues, props, tw, th)

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

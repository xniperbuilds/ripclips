"""
RipClips - Step 5: reframe each horizontal clip into vertical 1080x1920.

Two modes (set `mode:` in config.yaml):

  podcast  - camera rotates between two configured speakers (host/guest),
             using the crop x-positions in speakers.json.
  general  - auto face-tracking with OpenCV; the crop follows the dominant
             face. Falls back to a centered crop when no face is found.

Both modes build a crop-x timeline, then render once with FFmpeg (audio kept).

Usage:
    python 5_reframe/reframe.py                  # all clips, mode from config
    python 5_reframe/reframe.py --clip 1
    python 5_reframe/reframe.py --dry-run
    python 5_reframe/reframe.py --primary-duration 3-4 --secondary-duration 2-3
    python 5_reframe/reframe.py --focus-mode timeline   # podcast manual CSV
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


# ---------------------------------------------------------------------------
# probing
# ---------------------------------------------------------------------------

def probe(clip):
    """Return (width, height, duration_seconds) via ffprobe."""
    rc.require_tool("ffprobe")
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "json", str(clip),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    w = int(st.get("width", 0))
    h = int(st.get("height", 0))
    dur = float((data.get("format") or {}).get("duration", 0.0))
    if not (w and h and dur):
        rc.die("ffprobe could not read %s" % clip.name)
    return w, h, dur


def crop_box(sw, sh, tw, th):
    """Compute even crop w/h and vertical y-offset for a tw:th target."""
    ar = tw / float(th)
    crop_h = sh
    crop_w = int(round(sh * ar))
    if crop_w > sw:                      # source not wide enough -> crop height
        crop_w = sw
        crop_h = int(round(sw / ar))
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2
    y_off = max(0, (sh - crop_h) // 2)
    return crop_w, crop_h, y_off


def frac_to_x(frac, sw, crop_w):
    x = int(round(frac * sw - crop_w / 2.0))
    return max(0, min(sw - crop_w, x))


# ---------------------------------------------------------------------------
# timelines  ->  list of (t_start, x_pixel)
# ---------------------------------------------------------------------------

def parse_range(text):
    text = str(text)
    if "-" in text:
        a, b = text.split("-", 1)
        return (float(a) + float(b)) / 2.0
    return float(text)


def load_speakers():
    if not rc.SPEAKERS_FILE.exists():
        return {"default_speaker": "guest",
                "speakers": {"guest": {"x": 0.33}, "host": {"x": 0.67}}}
    with open(rc.SPEAKERS_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def podcast_timeline(dur, cfg, sw, crop_w, pd, sd):
    spk = load_speakers()["speakers"]
    prim = cfg["reframe"]["primary_speaker"]
    sec = cfg["reframe"]["secondary_speaker"]

    def xfor(name):
        frac = spk.get(name, {}).get("x", 0.5)
        return frac_to_x(frac, sw, crop_w)

    segs, t, on_primary = [], 0.0, True
    while t < dur:
        name = prim if on_primary else sec
        segs.append((round(t, 3), xfor(name)))
        t += pd if on_primary else sd
        on_primary = not on_primary
    return segs or [(0.0, frac_to_x(0.5, sw, crop_w))]


def timeline_from_csv(clip_start, clip_end, sw, crop_w):
    """Manual mode: map absolute-timestamp CSV rows into clip-local segments."""
    spk = load_speakers()
    default = spk.get("default_speaker", "guest")
    xmap = {n: frac_to_x(v.get("x", 0.5), sw, crop_w)
            for n, v in spk["speakers"].items()}
    rows = []
    if rc.TIMELINE_FILE.exists():
        with open(rc.TIMELINE_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or line.lower().startswith("start"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                rows.append((rc.parse_timecode(parts[0]),
                             rc.parse_timecode(parts[1]), parts[2]))
    segs = []
    for s, e, name in sorted(rows):
        if e <= clip_start or s >= clip_end:
            continue
        local = max(0.0, s - clip_start)
        segs.append((round(local, 3), xmap.get(name, xmap.get(default, 0))))
    if not segs or segs[0][0] > 0:
        segs.insert(0, (0.0, xmap.get(default, frac_to_x(0.5, sw, crop_w))))
    return segs


def general_timeline(clip, cfg, sw, sh, crop_w):
    """Auto face-tracking with OpenCV -> smoothed crop-x timeline."""
    rf = cfg["reframe"]
    if rf.get("detector", "opencv") == "center":
        return [(0.0, frac_to_x(0.5, sw, crop_w))]
    try:
        import cv2
    except ImportError:
        rc.log("WARNING: opencv-python not installed - using center crop. "
               "Run setup to enable face tracking.")
        return [(0.0, frac_to_x(0.5, sw, crop_w))]

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / max(1, int(rf.get("sample_fps", 3))))))

    samples, idx, last = [], 0, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
            if len(faces):
                fx, _, fw, _ = max(faces, key=lambda f: f[2] * f[3])
                last = (fx + fw / 2.0) / float(frame.shape[1])
            samples.append((idx / fps, last))
        idx += 1
    cap.release()

    known = [s for s in samples if s[1] is not None]
    if not known:
        return [(0.0, frac_to_x(0.5, sw, crop_w))]

    # forward/backward fill gaps
    first = known[0][1]
    filled, prev = [], first
    for t, f in samples:
        prev = f if f is not None else prev
        filled.append((t, prev))

    # EMA smoothing
    alpha = max(0.05, 1.0 - float(rf.get("smoothing", 0.85)))
    ema, sm = filled[0][1], []
    for t, f in filled:
        ema = alpha * f + (1 - alpha) * ema
        sm.append((t, frac_to_x(ema, sw, crop_w)))

    # merge near-equal consecutive x's to keep the expression small
    merge_px = max(6, int(crop_w * 0.012))
    segs = [sm[0]]
    for t, x in sm[1:]:
        if abs(x - segs[-1][1]) >= merge_px:
            segs.append((round(t, 3), x))
    return segs


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def build_x_expr(segs):
    """segs: [(t_start, x), ...] sorted -> ffmpeg piecewise expression."""
    if len(segs) == 1:
        return str(int(segs[0][1]))
    expr = str(int(segs[-1][1]))
    for i in range(len(segs) - 2, -1, -1):
        expr = "if(lt(t,%.3f),%d,%s)" % (segs[i + 1][0], int(segs[i][1]), expr)
    return expr


def render(clip, out_path, crop_w, crop_h, y_off, x_expr, tw, th):
    x_esc = x_expr.replace(",", "\\,")          # protect commas inside expr
    vf = "crop=%d:%d:%s:%d,scale=%d:%d:flags=lanczos" % (
        crop_w, crop_h, x_esc, y_off, tw, th)
    cmd = [
        "ffmpeg", "-y", "-i", str(clip),
        "-vf", vf,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return rc.run(cmd).returncode == 0


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--focus-mode", choices=["auto", "timeline"], default="auto")
    ap.add_argument("--primary-duration", default=None)
    ap.add_argument("--secondary-duration", default=None)
    args = ap.parse_args()

    cfg = rc.load_config()
    mode = cfg.get("mode", "podcast")
    tw = int(cfg["reframe"]["width"])
    th = int(cfg["reframe"]["height"])
    pd = parse_range(args.primary_duration or cfg["reframe"]["primary_duration"])
    sd = parse_range(args.secondary_duration or cfg["reframe"]["secondary_duration"])

    clips = sorted(rc.CLIPS_DIR.glob("clip_*.mp4"))
    if not clips:
        rc.die("no clips in %s (run step 4 first)." % rc.CLIPS_DIR)
    if args.clip is not None:
        clips = [c for c in clips if c.stem == "clip_%02d" % args.clip]
        if not clips:
            rc.die("clip %d not found." % args.clip)

    ranges = {c["index"]: c for c in rc.parse_clip_durations()} \
        if rc.CLIP_DURATIONS.exists() else {}
    rc.VERTICAL_DIR.mkdir(parents=True, exist_ok=True)
    rc.log("Reframe mode=%s  target=%dx%d  clips=%d" % (mode, tw, th, len(clips)))

    ok = 0
    for clip in clips:
        idx = int(clip.stem.split("_")[1])
        sw, sh, dur = probe(clip)
        crop_w, crop_h, y_off = crop_box(sw, sh, tw, th)

        if mode == "podcast" and args.focus_mode == "timeline":
            r = ranges.get(idx)
            if r:
                segs = timeline_from_csv(r["start"], r["end"], sw, crop_w)
            else:
                segs = podcast_timeline(dur, cfg, sw, crop_w, pd, sd)
        elif mode == "podcast":
            segs = podcast_timeline(dur, cfg, sw, crop_w, pd, sd)
        else:
            segs = general_timeline(clip, cfg, sw, sh, crop_w)

        x_expr = build_x_expr(segs)
        out_path = rc.VERTICAL_DIR / clip.name

        if args.dry_run:
            rc.log("clip %02d  %dx%d %.1fs  crop=%dx%d  segments=%d"
                   % (idx, sw, sh, dur, crop_w, crop_h, len(segs)))
            preview = ", ".join("%.1fs:x%d" % (t, x) for t, x in segs[:6])
            rc.log("          plan: %s%s"
                   % (preview, " ..." if len(segs) > 6 else ""))
            continue

        rc.log("-> clip %02d  (%d segments)" % (idx, len(segs)))
        if render(clip, out_path, crop_w, crop_h, y_off, x_expr, tw, th) \
                and out_path.exists():
            ok += 1
        else:
            rc.log("   WARNING: reframe failed for clip %02d" % idx)

    if not args.dry_run:
        rc.log("[ok] %d/%d vertical clips -> %s" % (ok, len(clips), rc.VERTICAL_DIR))
        if ok == 0:
            sys.exit(1)


if __name__ == "__main__":
    main()

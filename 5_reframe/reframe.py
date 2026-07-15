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
        rc.which("ffprobe") or "ffprobe", "-v", "error",
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


def alternating_timeline(dur, primary_x, secondary_x, pd, sd):
    """Rotate the crop between two x positions using the configured durations."""
    segs, t, on_primary = [], 0.0, True
    while t < dur:
        segs.append((round(t, 3), primary_x if on_primary else secondary_x))
        t += pd if on_primary else sd
        on_primary = not on_primary
    return segs or [(0.0, primary_x)]


def face_cascade():
    """Haar face cascade from whichever cv2 layout is present, else None.

    cv2.CascadeClassifier is top-level in OpenCV 4.x; OpenCV 5.0 moved it under
    cv2.objdetect. Returns None if unavailable so callers fall back to center crop.
    """
    try:
        import cv2
    except ImportError:
        return None
    cls = getattr(cv2, "CascadeClassifier", None)
    if cls is None:
        cls = getattr(getattr(cv2, "objdetect", None), "CascadeClassifier", None)
    if cls is None or not hasattr(cv2, "data"):
        return None
    cascade = cls(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return cascade if not cascade.empty() else None


def collect_face_xfracs(clip, cfg):
    """Sample the clip and return every detected face's x-center as a 0..1 frac."""
    try:
        import cv2
    except ImportError:
        return []
    cascade = face_cascade()
    if cascade is None:
        return []
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / max(1, int(cfg["reframe"].get("sample_fps", 3))))))
    fracs, idx = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
            w = float(frame.shape[1])
            for fx, _, fw, _ in faces:
                fracs.append((fx + fw / 2.0) / w)
        idx += 1
    cap.release()
    return fracs


def two_clusters(fracs, min_sep=0.08):
    """1-D 2-means on face x-fractions -> two sorted centers, or None."""
    if len(fracs) < 6:
        return None
    xs = sorted(fracs)
    c0, c1 = xs[0], xs[-1]
    if c1 - c0 < min_sep:
        return None
    for _ in range(12):
        g0 = [x for x in xs if abs(x - c0) <= abs(x - c1)]
        g1 = [x for x in xs if abs(x - c0) > abs(x - c1)]
        if not g0 or not g1:
            break
        n0, n1 = sum(g0) / len(g0), sum(g1) / len(g1)
        if abs(n0 - c0) < 1e-4 and abs(n1 - c1) < 1e-4:
            c0, c1 = n0, n1
            break
        c0, c1 = n0, n1
    if abs(c1 - c0) < min_sep:
        return None
    return sorted([c0, c1])


def calibrate_podcast(clip, cfg, sw, crop_w):
    """Return (primary_x, secondary_x) in pixels.

    Auto-detects the two speakers from the clip (default). Falls back to
    speakers.json fractions when detection fails or is disabled.
    """
    spk = load_speakers()["speakers"]
    pf = spk.get(cfg["reframe"]["primary_speaker"], {}).get("x", 0.33)
    sf = spk.get(cfg["reframe"]["secondary_speaker"], {}).get("x", 0.67)

    if cfg["reframe"].get("podcast_calibrate", True):
        clusters = two_clusters(collect_face_xfracs(clip, cfg))
        if clusters:
            pf, sf = clusters            # left = primary, right = secondary
    return frac_to_x(pf, sw, crop_w), frac_to_x(sf, sw, crop_w)


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

    cascade = face_cascade()
    if cascade is None:
        rc.log("WARNING: OpenCV face detector unavailable - using center crop.")
        return [(0.0, frac_to_x(0.5, sw, crop_w))]
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
                px, sx = calibrate_podcast(clip, cfg, sw, crop_w)
                segs = alternating_timeline(dur, px, sx, pd, sd)
        elif mode == "podcast":
            px, sx = calibrate_podcast(clip, cfg, sw, crop_w)
            segs = alternating_timeline(dur, px, sx, pd, sd)
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

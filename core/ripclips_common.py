"""
RipClips - shared helpers used by every pipeline step.

Cross-platform (Windows / macOS / Linux). No third-party imports here except
PyYAML, so this module stays importable even when opencv or yt-dlp are missing.
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root + paths
# ---------------------------------------------------------------------------

# This file lives at <root>/core/ripclips_common.py, so the root is one up.
ROOT = Path(__file__).resolve().parent.parent

TRANSCRIPT_DIR   = ROOT / "1_transcript"
ANALYSIS_DIR     = ROOT / "2_analysis"
DOWNLOAD_DIR     = ROOT / "3_download" / "downloads"
CLIPS_DIR        = ROOT / "4_clip" / "clips"
VERTICAL_DIR     = ROOT / "5_reframe" / "vertical_clips"
CAPTIONED_DIR    = ROOT / "6_captions" / "captioned_clips"

CLIP_DURATIONS   = ANALYSIS_DIR / "clip_durations.txt"
CONFIG_FILE      = ROOT / "config.yaml"
SPEAKERS_FILE    = ROOT / "5_reframe" / "speakers.json"
TIMELINE_FILE    = ROOT / "5_reframe" / "speaker_timeline.csv"


# ---------------------------------------------------------------------------
# Console (ASCII-safe on Windows cp1252 terminals)
# ---------------------------------------------------------------------------

def log(msg):
    """Print a line that never crashes on a non-UTF terminal."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(str(msg).encode("ascii", "replace").decode("ascii"), flush=True)


def die(msg, code=1):
    log("ERROR: " + str(msg))
    sys.exit(code)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "mode": "podcast",          # podcast | general
    "language": "en",
    "download": {"max_height": 1080, "format": "mp4"},
    "clip": {"encode_mode": "reencode", "min_seconds": 8, "max_seconds": 90},
    "reframe": {
        "width": 1080,
        "height": 1920,
        "primary_speaker": "guest",
        "secondary_speaker": "host",
        "primary_duration": "3-4",
        "secondary_duration": "2-3",
        "detector": "opencv",   # opencv | center  (general mode)
        "smoothing": 0.85,
        "sample_fps": 3,
    },
    "captions": {"default_style": 1, "font": ""},
}


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    """Load config.yaml merged over defaults. Missing file -> defaults."""
    user_cfg = {}
    if CONFIG_FILE.exists():
        try:
            import yaml  # lazy: only needed when a config file is present
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                user_cfg = yaml.safe_load(fh) or {}
        except ImportError:
            log("WARNING: PyYAML not installed - using default config. "
                "Run setup to install requirements.")
        except Exception as exc:  # noqa: BLE001
            log("WARNING: could not parse config.yaml (%s) - using defaults." % exc)
    return _deep_merge(_DEFAULT_CONFIG, user_cfg)


# ---------------------------------------------------------------------------
# External tool discovery
# ---------------------------------------------------------------------------

def which(name):
    """Return the path to an executable, or None.

    Checks PATH first, then this repo's local .venv (so the pipeline works even
    when the venv isn't 'activated', as long as its Scripts/bin holds the tool).
    """
    found = shutil.which(name)
    if found:
        return found
    for sub in ("Scripts", "bin"):
        cand = ROOT / ".venv" / sub / name
        for ext in ("", ".exe", ".cmd", ".bat"):
            p = cand.with_name(cand.name + ext) if ext else cand
            if p.exists():
                return str(p)
    return None


def require_tool(name, hint=""):
    path = which(name)
    if not path:
        extra = (" " + hint) if hint else ""
        die("'%s' not found on PATH. Run setup.ps1 (Windows) or setup.sh "
            "(macOS/Linux) to install it.%s" % (name, extra))
    return path


def run(cmd, **kwargs):
    """Run a subprocess, streaming output. Returns the CompletedProcess.

    Resolves a bare executable name (e.g. 'ffmpeg', 'yt-dlp') via which() so the
    call still works when the .venv isn't activated.
    """
    if cmd and not os.path.dirname(str(cmd[0])):
        resolved = which(str(cmd[0]))
        if resolved:
            cmd = [resolved] + list(cmd[1:])
    log("$ " + " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, **kwargs)


# ---------------------------------------------------------------------------
# Timecode helpers
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?")


def parse_timecode(text):
    """Parse 'HH:MM:SS(.mmm)' or 'MM:SS' into float seconds."""
    text = text.strip()
    m = _TS_RE.fullmatch(text)
    if not m:
        raise ValueError("bad timecode: %r" % text)
    hh = int(m.group(1) or 0)
    mm = int(m.group(2))
    ss = int(m.group(3))
    ms = int((m.group(4) or "0").ljust(3, "0"))
    return hh * 3600 + mm * 60 + ss + ms / 1000.0


def format_timecode(seconds, millis=True):
    """Float seconds -> 'HH:MM:SS.mmm' (or 'HH:MM:SS')."""
    if seconds < 0:
        seconds = 0
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = int(seconds % 60)
    if millis:
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms == 1000:
            ms = 0
            ss += 1
        return "%02d:%02d:%02d.%03d" % (hh, mm, ss, ms)
    return "%02d:%02d:%02d" % (hh, mm, ss)


def parse_clip_durations(path=None):
    """
    Read 2_analysis/clip_durations.txt and return a list of dicts:
        [{"index": 1, "start": 84.0, "end": 130.0}, ...]

    Accepted block format (blank line between clips is optional):
        Clip 1
        Time: 00:01:24 - 00:02:10
    """
    path = Path(path) if path else CLIP_DURATIONS
    if not path.exists():
        die("clip list not found: %s (run step 2 first)." % path)

    clips = []
    current = None
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            mclip = re.match(r"(?i)^clip\s+(\d+)", line)
            if mclip:
                current = int(mclip.group(1))
                continue
            mtime = re.match(r"(?i)^time:\s*(.+?)\s*[-–]+\s*(.+)$", line)
            if mtime:
                start = parse_timecode(mtime.group(1))
                end = parse_timecode(mtime.group(2))
                if end <= start:
                    log("WARNING: clip %s has end <= start, skipping." % current)
                    continue
                clips.append({
                    "index": current if current is not None else len(clips) + 1,
                    "start": start,
                    "end": end,
                })
                current = None
    if not clips:
        die("no valid clips parsed from %s" % path)
    return clips


def clip_name(index, ext="mp4"):
    return "clip_%02d.%s" % (int(index), ext)


def find_source_video():
    """Return the single downloaded source .mp4 in 3_download/downloads."""
    vids = sorted(
        [p for p in DOWNLOAD_DIR.glob("*.mp4") if p.is_file()],
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not vids:
        die("no source video in %s (run step 3 first)." % DOWNLOAD_DIR)
    return vids[0]


def find_srt():
    """Return the transcript .srt in 1_transcript (prefer manual over auto)."""
    srts = list(TRANSCRIPT_DIR.glob("*.srt"))
    if not srts:
        die("no .srt transcript in %s (run step 1 first)." % TRANSCRIPT_DIR)
    # Prefer files that do NOT look auto-generated.
    manual = [p for p in srts if "auto" not in p.name.lower()]
    pool = manual or srts
    return sorted(pool, key=lambda p: p.stat().st_size, reverse=True)[0]

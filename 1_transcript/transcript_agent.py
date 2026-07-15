"""
RipClips - Step 1: YouTube transcript.

Downloads SUBTITLES ONLY (never the video) with yt-dlp, keeps the timestamped
.srt for later steps, and writes a clean paragraph transcript.txt for the
analysis step.

Usage:
    python 1_transcript/transcript_agent.py "https://youtu.be/VIDEO_ID"
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import ripclips_common as rc  # noqa: E402


# YouTube increasingly gates the default web client behind "Sign in to confirm
# you're not a bot". These alternate player clients usually bypass that for
# subtitle + video fetches. We try the default first, then fall back.
CLIENT_FALLBACKS = ["default", "tv_embedded,android", "android", "web_safari,android"]


def _yt_dlp_subs(url, lang, client, out_tmpl):
    cmd = [
        "yt-dlp", "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "%s.*" % lang,
        "--convert-subs", "srt",
        "-o", out_tmpl,
    ]
    if client != "default":
        cmd += ["--extractor-args", "youtube:player_client=%s" % client]
    cmd += [url]
    return rc.run(cmd)


def download_subs(url, lang):
    rc.require_tool("yt-dlp")
    out_tmpl = str(rc.TRANSCRIPT_DIR / "%(title).120B [%(id)s].%(ext)s")
    for client in CLIENT_FALLBACKS:
        if client != "default":
            rc.log("   retrying subtitle fetch with player_client=%s ..." % client)
        result = _yt_dlp_subs(url, lang, client, out_tmpl)
        if result.returncode == 0 and newest_srt() is not None:
            return
    if newest_srt() is not None:      # something landed despite a nonzero exit
        return
    rc.die("yt-dlp could not fetch subtitles - YouTube may be blocking this "
           "network/IP. Try again later, or export browser cookies to a "
           "cookies.txt and add:  --cookies cookies.txt")


def newest_srt():
    srts = sorted(rc.TRANSCRIPT_DIR.glob("*.srt"), key=lambda p: p.stat().st_mtime)
    return srts[-1] if srts else None


def srt_to_paragraph(srt_path):
    """Strip cue numbers, timestamps and duplicate lines -> readable text."""
    lines = []
    with open(srt_path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.isdigit():
                continue
            if "-->" in line:
                continue
            line = re.sub(r"<[^>]+>", "", line)          # inline tags
            line = re.sub(r"\{\\[^}]*\}", "", line)       # ass overrides
            lines.append(line)
    # collapse consecutive duplicate fragments (common in auto-captions)
    cleaned = []
    for ln in lines:
        if not cleaned or cleaned[-1].lower() != ln.lower():
            cleaned.append(ln)
    return re.sub(r"\s+", " ", " ".join(cleaned)).strip()


def main():
    if len(sys.argv) < 2:
        rc.die('usage: python 1_transcript/transcript_agent.py "YOUTUBE_URL"')
    url = sys.argv[1]
    cfg = rc.load_config()
    lang = cfg.get("language", "en")

    rc.TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    rc.log("Fetching subtitles for: %s" % url)
    download_subs(url, lang)

    srt = newest_srt()
    if not srt:
        rc.die("no .srt produced. The video may have no %s subtitles." % lang)

    rc.log("[ok] transcript saved: %s" % srt.name)

    paragraph = srt_to_paragraph(srt)
    txt_path = rc.TRANSCRIPT_DIR / "transcript.txt"
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(paragraph + "\n")
    rc.log("[ok] clean transcript: %s (%d chars)" % (txt_path.name, len(paragraph)))
    rc.log("Next: step 2 reads the .srt timestamps to pick clip moments.")


if __name__ == "__main__":
    main()

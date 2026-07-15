# RipClips - Agent Orchestrator Instructions

RipClips turns a long YouTube video into short, vertical, captioned clips for TikTok, YouTube Shorts, and Reels. It is an **agentic workflow**: you (the AI agent - Claude Code, Codex, Cursor, etc.) are the orchestrator that runs it end to end. No paid AI API key is required - the "smart" step (picking the best moments) is done by your own reasoning.

Whenever the user gives a YouTube URL, or asks to repurpose / clip / make shorts from a YouTube video, run the full pipeline in folders `1_transcript` -> `6_captions`, in order.

---

## Core Rule - read the directive first

> **Before doing anything for a step, open and read that step's directive file in full.** Then follow it exactly - its tools, inputs, output filename, output path, and rules.

Do not skip a step, reorder steps, invent filenames/paths, or assume how a step works from memory. Do not advance to the next step until the current step's required output exists and is verified.

---

## Setup (first run only)

If `yt-dlp` or `ffmpeg` is missing, tell the user to run setup once:
- Windows: `powershell -ExecutionPolicy Bypass -File setup.ps1`
- macOS/Linux: `bash setup.sh`

This creates a `.venv`, installs Python deps, and installs ffmpeg. Behaviour defaults live in `config.yaml` (mode, quality, caption style, framing).

**Run steps inside the venv.** Either activate it first (`.\.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` elsewhere) or invoke `.venv`'s Python directly (`.venv\Scripts\python.exe 1_transcript\transcript_agent.py ...`). The scripts also auto-find `yt-dlp`/`ffmpeg` inside `.venv` if it isn't activated.

---

## Pipeline

```
YouTube URL
   |
   v
1 Transcript -> 2 Clip Analysis -> 3 Download -> 4 Clip Export -> 5 Vertical Reframe -> 6 Subtitle Burn
```

| Step | Folder | Directive | Action | Output |
|------|--------|-----------|--------|--------|
| 1 | `1_transcript/` | `youtube_transcript.directive.md` | Fetch subtitles (only) | `1_transcript/*.srt` |
| 2 | `2_analysis/` | `clip_analysis.directive.md` | Pick best moments (your intelligence) | `2_analysis/clip_durations.txt` |
| 3 | `3_download/` | `video_download.directive.md` | Download full video | `3_download/downloads/*.mp4` |
| 4 | `4_clip/` | `clip_export.directive.md` | Cut clips | `4_clip/clips/clip_XX.mp4` |
| 5 | `5_reframe/` | `reframe.directive.md` | Reframe to vertical 1080x1920 | `5_reframe/vertical_clips/clip_XX.mp4` |
| 6 | `6_captions/` | `subtitle_burn.directive.md` | Burn styled captions | `6_captions/captioned_clips/clip_XX.mp4` |

**Modes** (set `mode:` in `config.yaml`; default `general`):
- `general` - any video; auto face-tracking follows the dominant face, or centers when none is found.
- `podcast` - two-speaker interviews; the crop rotates between the two speakers, whose positions are auto-detected from the clip (or fixed in `speakers.json` when `podcast_calibrate: false`).

**Caption styles** (step 6, `--style N`): 1 TikTok Classic, 2 Word Pop, 3 Podcast Modern, 4 Word-by-Word, 5 Highlight Karaoke, 6 Bold Yellow, 7 Neon, 8 Boxed Bar. All are customizable under `config.yaml -> captions:` (font, size, colours, position, bold, uppercase, margins).

**YouTube bot gate:** if a plain `yt-dlp` call is blocked with "Sign in to confirm you're not a bot", steps 1 and 3 automatically retry with alternate `--extractor-args youtube:player_client=...` clients. No action needed; if all retries fail the step reports it.

---

## Deterministic execution rules

- Start at step 1 when a YouTube URL is given.
- Run steps `1 -> 2 -> 3 -> 4 -> 5 -> 6`, once each, in order.
- Re-read the current step's directive immediately before running it, every time.
- Use only earlier steps' outputs and the tools/paths the current directive authorizes.
- Verify each output before advancing. If a step fails, diagnose or report it - never silently skip.
- **Step 6 requires a user choice of caption style. Stop and ask; do not guess.**
- Keep every intermediate and final file in the exact folder its directive specifies.

---

## Reset between runs

To clear generated outputs before a fresh run, follow `cleanup.md` (deletes only the generated files listed in `.gitignore`, never source or config).

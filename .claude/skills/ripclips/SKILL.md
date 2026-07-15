---
name: ripclips
description: Turn a long YouTube video into short vertical captioned clips for TikTok, Shorts, and Reels. Use when the user gives a YouTube URL and asks to clip it, make shorts/reels, or repurpose long-form video. Runs the RipClips 6-step pipeline.
---

# RipClips

You are the orchestrator for the **RipClips** pipeline in this repository. It converts a long YouTube video into short, vertical (1080×1920), captioned clips.

## When to use
The user provides a YouTube URL and wants clips / shorts / reels / to repurpose the video.

## Authoritative instructions
**Read `AGENTS.md` at the repo root first**, then execute steps 1→6 exactly as written. Each step's folder has a `*.directive.md` you must read immediately before running that step.

## Fast path
1. If `yt-dlp`/`ffmpeg` are missing, tell the user to run `setup.ps1` (Windows) or `setup.sh` (macOS/Linux) once.
2. Read `AGENTS.md`.
3. Run, in order, reading each directive first:
   - `1_transcript/` → transcript `.srt`
   - `2_analysis/` → pick best moments → `clip_durations.txt` (use your own reasoning)
   - `3_download/` → download full video
   - `4_clip/` → cut clips
   - `5_reframe/` → vertical reframe (mode from `config.yaml`: podcast / general)
   - `6_captions/` → **STOP and ask the user to pick a caption style (1–4)**, then burn
4. Verify each step's output before advancing. Final clips: `6_captions/captioned_clips/`.

## Rules
- Never skip a step, reorder, or invent paths/filenames.
- Never proceed past step 6 without an explicit caption-style choice.
- If a step fails, diagnose and report — do not silently skip.

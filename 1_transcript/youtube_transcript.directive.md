# Step 1 Directive - YouTube Transcript

**Goal:** fetch the timestamped subtitles for the user's YouTube video. Subtitles ONLY - never download the video in this step.

## Inputs
- The YouTube URL from the user's message.
- `language` from `config.yaml` (default `en`).

## How to run
```bash
python 1_transcript/transcript_agent.py "YOUTUBE_URL"
```

The helper:
1. Runs `yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "<lang>.*" --convert-subs srt` into `1_transcript/`.
2. Prefers creator/manual subtitles, falls back to auto-generated captions.
3. Saves the timestamped `.srt` (used later by steps 2 and 6).
4. Writes a clean `transcript.txt` paragraph (used by step 2 analysis).

## Manual fallback (if the helper cannot run)
```bash
yt-dlp --skip-download --write-subs --write-auto-subs --sub-langs "en.*" --convert-subs srt -o "1_transcript/%(title).120B [%(id)s].%(ext)s" "YOUTUBE_URL"
```

## Required output
- At least one `.srt` file inside `1_transcript/`.
- `1_transcript/transcript.txt`.

## Rules
- Do NOT download the video here.
- Do NOT proceed to step 2 until a `.srt` exists in `1_transcript/`.
- If the video has no subtitles in the target language, report it to the user instead of guessing.

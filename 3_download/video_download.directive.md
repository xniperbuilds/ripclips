# Step 3 Directive - Video Download

**Goal:** download the full source YouTube video at good quality. No subtitles, no clipping here.

## Inputs
- The same YouTube URL from step 1.
- `config.yaml` -> `download.max_height` (default 1080, auto-falls back to 720).

## How to run
```bash
python 3_download/download_video.py "YOUTUBE_URL"
```

The helper downloads with `yt-dlp`, merges best video+audio to a single `.mp4` in `3_download/downloads/`. It **auto-retries YouTube's bot gate** with alternate `--extractor-args youtube:player_client=...` clients if the default is blocked.

## Manual fallback
```bash
yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]/bv*[height<=720]+ba/b[height<=720]" --merge-output-format mp4 -o "3_download/downloads/%(title).120B [%(id)s].%(ext)s" "YOUTUBE_URL"
```
If blocked by the bot gate, add: `--extractor-args "youtube:player_client=android"` (or `tv_embedded,android`).

## Required output
- Exactly one `.mp4` in `3_download/downloads/`.

## Rules
- Do NOT download subtitles here (step 1 already did).
- Do NOT clip here (step 4 does).
- Do NOT proceed until the `.mp4` exists.

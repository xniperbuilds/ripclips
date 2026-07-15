# Step 5 Directive - Vertical Reframe

**Goal:** turn each horizontal clip into a vertical `1080x1920` clip suitable for TikTok / Shorts / Reels.

## Mode (from `config.yaml` -> `mode`)
- **podcast** - two-speaker interviews. The crop rotates between the configured speakers (default: guest 3-4s, then host 2-3s, repeat). Crop positions come from `5_reframe/speakers.json`.
- **general** - any long-form video. Auto face-tracking (OpenCV) makes the crop follow the dominant on-screen face; falls back to a centered crop when no face is detected.

## Inputs
- `4_clip/clips/clip_XX.mp4`.
- `config.yaml` -> `reframe.*`.
- podcast: `5_reframe/speakers.json` (and optional `5_reframe/speaker_timeline.csv`).

## How to run
```bash
python 5_reframe/reframe.py                 # all clips, mode from config
python 5_reframe/reframe.py --clip 1        # one clip
python 5_reframe/reframe.py --dry-run       # print the crop plan, render nothing
python 5_reframe/reframe.py --primary-duration 3-4 --secondary-duration 2-3
python 5_reframe/reframe.py --focus-mode timeline   # podcast manual CSV timing
```

## Tuning
- **Podcast framing:** edit `speakers.json` - `x` is each speaker's crop CENTER as a fraction of width (0=left, 1=right). Run `--dry-run` to preview.
- **General smoothness:** `reframe.smoothing` (higher = smoother camera), `reframe.sample_fps`, or `reframe.detector: center` to disable tracking.

## Required output
- One vertical `.mp4` per clip in `5_reframe/vertical_clips/`.

## Rules
- Do NOT burn subtitles here (step 6 does).
- Do NOT proceed until at least one vertical clip exists.

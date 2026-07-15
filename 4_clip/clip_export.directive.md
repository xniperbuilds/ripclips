# Step 4 Directive - Clip Export

**Goal:** cut the full source video into individual clips using the time ranges from step 2.

## Inputs
- `3_download/downloads/*.mp4` (source video).
- `2_analysis/clip_durations.txt` (time ranges).
- `config.yaml` -> `clip.encode_mode` (`reencode` = accurate, `copy` = fastest).

## How to run
```bash
python 4_clip/cut_clips.py                # all clips
python 4_clip/cut_clips.py --mode copy    # fastest (keyframe-snapped)
python 4_clip/cut_clips.py --clip 2       # only clip 2
```

Uses FFmpeg. `reencode` gives frame-accurate boundaries; `copy` is fastest but snaps to nearby keyframes.

## Required output
- One `.mp4` per clip in `4_clip/clips/`, named `clip_01.mp4`, `clip_02.mp4`, ...

## Rules
- Do NOT re-analyse the transcript or re-download the video here.
- Each clip must match its start/end from step 2.
- Do NOT proceed until at least one `clip_XX.mp4` exists.

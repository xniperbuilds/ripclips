# Step 2 Directive - Transcript Clip Analysis

**Goal:** read the timestamped transcript from step 1 and pick the best moments to clip. This step is done by YOUR OWN intelligence as the agent - no external API, no sentiment service.

## Inputs
- `1_transcript/*.srt` (has timestamps) and/or `1_transcript/transcript.txt`.
- `config.yaml` -> `clip.min_seconds`, `clip.max_seconds` (length guidance).

## What to do
1. Read the transcript in full.
2. Find the most important, emotional, surprising, funny, or standalone-worthy moments - the kind that work as short vertical clips.
3. Prefer moments that make sense on their own (a complete thought/story/point).
4. Choose clean start/end times from the `.srt` timestamps. Aim for `min_seconds`..`max_seconds`.
5. Order clips by their appearance in the video.

## Required output
Create `2_analysis/clip_durations.txt` containing ONLY clip numbers and time ranges - no titles, scores, reasons, or commentary:

```text
Clip 1
Time: 00:01:24 - 00:02:10

Clip 2
Time: 00:05:33 - 00:06:18
```

## Rules
- Output only the format above. No extra text.
- Use `HH:MM:SS` (or `HH:MM:SS.mmm`) taken from real transcript timestamps.
- If only one strong moment exists, output just one clip.
- Do NOT re-download or re-transcribe. Do NOT proceed until `clip_durations.txt` exists.

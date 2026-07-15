# Step 6 Directive - Subtitle Burn (final step)

**Goal:** burn styled captions permanently into each vertical clip from step 5, producing the final upload-ready clips.

## Inputs
| Source | Path |
|--------|------|
| Vertical clips | `5_reframe/vertical_clips/clip_XX.mp4` |
| Subtitle track | `1_transcript/*.srt` |
| Clip time ranges | `2_analysis/clip_durations.txt` |

## MANDATORY PAUSE - ask the user to pick a style

Before running anything, STOP and present this menu word-for-word. Do not guess.

---
> **Choose a subtitle style for your clips:**
>
> **1 - TikTok Classic** - Bold white text, thick black outline. Standard high-readability look.
> **2 - Word Pop** - Yellow text on a dark semi-transparent box. Punchy for interviews/reactions.
> **3 - Podcast Modern** - Clean white text with a soft drop shadow. Minimal and premium.
> **4 - Word-by-Word** - One word at a time, karaoke style. The viral trend.
>
> *Type 1, 2, 3, or 4 to continue.*
---

Wait for a valid reply (1-4). (A default style can be preset in `config.yaml -> captions.default_style`, but still confirm with the user.)

## How to run
```bash
python 6_captions/burn_subtitles.py --style N            # all clips
python 6_captions/burn_subtitles.py --style N --clip 2   # one clip
```

The script trims/offsets the `.srt` cues to each clip window, builds a styled `.ass`, and burns it with FFmpeg. Style 4 splits each cue into individual word-timed entries.

## Required output
- One final `.mp4` per clip in `6_captions/captioned_clips/` - subtitles baked in, ready to upload.

## Rules
- Do NOT skip the style question.
- Do NOT re-download, re-transcribe, or re-export clips here.
- If a clip has no overlapping cues it is copied as-is with a warning.

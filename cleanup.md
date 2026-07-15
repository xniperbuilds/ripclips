# Cleanup Directive

## Purpose
Reset RipClips to a clean, ready-to-run state by deleting generated pipeline outputs and Python cache - the disposable files listed in `.gitignore`.

## Procedure
1. Work from the repo root (the folder with this file, `.gitignore`, `config.yaml`, and folders `1_transcript` ... `6_captions`).
2. Read `.gitignore` first - it is the authoritative list of generated artifacts.
3. Delete only these:
   - Every `.srt`, `.vtt`, and `transcript.txt` in `1_transcript/`.
   - `2_analysis/clip_durations.txt`.
   - Everything inside `3_download/downloads/` except `.gitkeep`.
   - Everything inside `4_clip/clips/` except `.gitkeep`.
   - Everything inside `5_reframe/vertical_clips/` except `.gitkeep`.
   - Everything inside `6_captions/captioned_clips/` except `.gitkeep`.
   - Every `__pycache__/` directory and every `*.pyc` / `*.pyo`.
4. Missing/empty paths are fine - not an error.
5. Verify the outputs are gone and each output folder still has its `.gitkeep`.
6. Report what was removed.

## Safety rules
- NEVER delete `.git/`, `.gitignore`, `config.yaml`, `AGENTS.md`, `cleanup.md`, `README.md`, `LICENSE`, directive files, `speakers.json`, `speaker_timeline.csv`, `core/`, `.claude/`, or any `.py` source.
- Preserve every `.gitkeep`. Do not delete the output folders themselves - only their generated contents.
- No broad/recursive delete commands that could remove source. Delete only the explicit paths above.
- Do not run any pipeline step during cleanup.

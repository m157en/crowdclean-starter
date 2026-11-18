# CrowdClean — vocal-stem experiment (2026-11-18)

## Decision
Human A/B ratings for broadband ducking: 8 worse / 0 better / 0 unclear.
Reject broadband ducking as the production method. Do not delete the previous
previews or ratings.

## Implemented (feature/audio-mvp)
- `app/audio_stems.py`: optional Demucs two-stem separation on **two** REMOVE
  regions by default. Generates independent original/stem-attenuated stereo
  previews and `report.json` in `storage/analysis/ab-stems-v1`.
- Human precise boundaries, not VAD raw regions, determine where the vocal
  stem is attenuated. Smooth 250 ms fades. Source MP3 never modified.
- `/ab/stems`: separate listening page and independent `ratings.json`.
- `tests/test_audio_stems.py`: tests for stem alignment, boundary validation,
  preserving the instrumental stem, and unity gain.

## Execution constraints
GitHub contains no original MP3 or local audio; remote commits cannot execute
Demucs on the user's Mac. New code has **not** been tested on that Mac.
The user must run a local test command and install the optional Demucs model
dependencies. A model download may occur on first invocation.

From `~/Documents/crowdclean-starter/backend`, first run existing tests:

```bash
.venv-audio/bin/python -m pytest -q
```

For optional model setup, use the **existing audio venv** only after checking
dependency compatibility; Demucs 4.x and torchaudio may conflict with pinned
Intel Mac PyTorch. Do not silently upgrade torch or overwrite the venv.
Check first:

```bash
.venv-audio/bin/python -m pip show torch torchaudio demucs numpy soundfile
```

After Demucs is available in that interpreter, generate two previews:

```bash
.venv-audio/bin/python -m app.audio_stems --limit 2
```

Restart the local FastAPI server, then open `http://127.0.0.1:8000/ab/stems`.
Do not run full-mix separation. The model may suppress sung vocals and leak
instrumental content. Evaluate manually against the unprocessed original.

## Safety
- No automatic model install, model download, full-mix processing or merging.
- No changes to `main`.
- Never overwrite existing preview folders.
- Do not upload local audio or private ratings to GitHub.
- Keep backup `~/Documents/CrowdClean-backup-2026-11-17` intact.

## Blocker
Need local Mac runtime information and successful optional Demucs setup.
Until then, separation quality cannot be established or certified.

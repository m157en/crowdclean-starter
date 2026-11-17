# CrowdClean — checkpoint / resume 2026-11-17

## Source of truth and scope
- Repository: `m157en/crowdclean-starter`, branch **`feature/audio-mvp`**. Do not merge to `main` without approval.
- Local workspace: `~/Documents/crowdclean-starter`; backend: `backend/`; Python: `.venv-audio/bin/python`.
- Local audio and review clips are NOT stored in GitHub. Never assume they can be recovered from the repo.
- **Last verified local test run:** 48 passed (before subsequent precise-boundary, filter, UI fixes, and preview code). All newer tests **not yet verified on the Mac**. Do not claim otherwise.
- Current remote code as of this checkpoint includes preview test commit `5131129`. The data-label commit is `75603ca`.

## Completed and verified
1. Silero VAD chunked processing on 58:50.011 (`3530.011` s) `storage/samples/lost-frequencies.mp3`, threshold `0.3`: **61** speech candidates.
2. Candidates merged with 5 s gap and 2 s context: **25** review WAVs in `storage/analysis/review/threshold-03/`.
3. User manually labeled **17 KEEP / 8 REMOVE**. This is episode-level precision among reviewed candidates, not recall or model precision across all possible events.
4. User marked approximate whole-second shout boundaries for all eight REMOVE episodes. Labels are versioned at `backend/datasets/lost-frequencies-review-threshold-03.json`:
   - 006 1398.3–1402.3
   - 013 2347.0–2354.0
   - 014 2363.4–2365.4
   - 015 2370.7–2371.7
   - 016 2500.7–2504.7
   - 018 2644.9–2652.9
   - 019 2658.6–2659.6
   - 024 3320.2–3327.2
   Total **34 seconds** of human-annotated candidate regions, not isolated voice.
5. Local review UI at `http://127.0.0.1:8000/review` lists only REMOVE episodes, supports relative clip time boundary selection, persists absolute boundaries in local `manifest.json`.

## New code awaiting local execution
- `backend/app/audio_preview.py`: CLI creates eight pairs of mono 16k WAV previews, original and smoothly broadband-ducked at 25% gain, with 2 s context; output `storage/analysis/ab-preview-v1/` and `report.json`. It never changes source MP3. **This is NOT source separation and attenuates the music as well.** Preview output must not be presented as a clean mix.
- `backend/tests/test_audio_preview.py`: 3 tests for envelope, PCM length/source immutability, output and overwrite prevention.
- Note: script intentionally refuses to overwrite an existing `ab-preview-v1` directory. If output already exists, inspect it before choosing a new output path; never delete it blindly.

## Exact first step next session
Run locally from Terminal:
```bash
cd ~/Documents/crowdclean-starter && \
git status --short && \
git pull --ff-only && \
cd backend && \
.venv-audio/bin/python -m pytest -q && \
.venv-audio/bin/python -m app.audio_preview
```
If `git status --short` shows local modifications, inspect them before pulling; never reset/discard. If tests fail, fix in feature branch and rerun. Expected test count is approximately 52 (48 last verified plus 1 boundary test, 1 filtering test, 1 relative UI test, 1 save test, and 3 preview tests; actual count must be checked rather than assumed).

## Next work after preview generation
1. A/B listen to each of the eight pairs (original vs ducked); measure music damage subjectively. **No full-mix export yet.**
2. Build a browser A/B player for preview files with rating `better / worse / unclear`, store results in a separate report.
3. Evaluate vocal/music separation alternatives on short samples only; do not claim quality without listening.
4. Keep a baseline against KEEP regions and guard against false positives. Human boundary uncertainty ~1 s.
5. Design a non-destructive final export only after the algorithm is selected and evaluated.

## Local data preservation checklist
Before closing for the day, preserve these local-only assets:
- `backend/storage/samples/lost-frequencies.mp3` (original mix)
- `backend/storage/analysis/lost-frequencies-threshold-03.json`
- `backend/storage/analysis/review/threshold-03/manifest.json`
- `backend/storage/analysis/review/threshold-03/review-*.wav`
- `backend/storage/analysis/reference-16k/` (two reference WAVs)
- any `backend/storage/analysis/ab-preview-v1/` generated later.

Do NOT commit MP3/WAV to GitHub; preserve them locally in a separate backup location. Repo data-label JSON already versioned in GitHub.

## Cautions
- Silero at 0.3 generates candidates, not definitive shout classifications.
- 8/25 positive episode rate is not recall and does not validate production quality.
- The current preview attenuation is broadband: cannot remove only DJ voice.
- No scheduled/background run was set up. Resume explicitly next session.

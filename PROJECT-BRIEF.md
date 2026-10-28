# CrowdClean — product brief

## Problem

DJ-set listeners often want continuous music without spoken hype phrases such as “make some noise” or “put your hands up.” Existing tools may have short duration caps, metered credits, clunky flows or no URL import. CrowdClean aims to provide a batch-first, reviewable workflow for long mixes.

## Primary user flow

1. User uploads an audio file or adds a supported source URL.
2. Service creates a job and shows status/progress.
3. Service detects likely spoken intervals and marks confidence.
4. User previews each interval and chooses keep/remove.
5. Service renders a cleaned mix and offers an export.

## Non-goals for MVP

- Perfect speaker diarization in every concert recording.
- Removing every vocal sound from the music.
- Bypassing DRM or downloading from providers that do not permit it.
- Public hosting of user files without retention and access controls.

## Quality metrics

- Speech-candidate precision/recall on a rights-cleared labelled fixture set.
- Percentage of musical-vocal intervals incorrectly marked for removal.
- End-to-end completion rate for long files.
- Processing time and peak memory per audio hour.
- Percentage of output files that decode correctly and preserve duration/channel count.
- User correction rate for suggested intervals.

# CrowdClean

CrowdClean is an API-first portfolio project for identifying DJ crowd shouts in long electronic music sets and producing a cleaned audio version without unnecessarily damaging the music.

**Current state:** the first backend slice is implemented: REST job creation (URL/upload), persistence, job listing/detail, segment decisions, and GraphQL reads/updates. Audio analysis and the actual cleanup worker are deliberately not faked; they are the next milestone.

## Why this project

The product solves a real workflow problem: long mixes should be processable without arbitrary short-duration caps, with no per-minute credit meter in the prototype, and with a review step to catch false positives. The QA portfolio should demonstrate meaningful quality engineering, not just endpoint smoke tests.

## Architecture (target)

- **FastAPI REST:** upload/import, job status, segment review, export/download.
- **Strawberry GraphQL:** flexible reads for jobs and detected segments; mutation for reviewer decisions.
- **PostgreSQL:** jobs, time segments, decisions, processing events.
- **Worker + Redis:** long-running audio jobs, retries, idempotency, cancellation.
- **Audio pipeline:** speech activity detection -> candidate classification -> optional source separation -> time-aware attenuation/replacement -> export.
- **Frontend:** React UI, waveform/timeline, before/after preview.
- **Quality:** pytest API/integration tests, SQL validation, Playwright E2E, CI, quality gates.

## Quick start: local Python

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for REST docs and `http://127.0.0.1:8000/graphql` for GraphQL.

Run tests:

```bash
pytest -q
pytest --cov=app --cov-branch
```

By default the local app uses SQLite. The tests use a separate in-memory SQLite database and temporary upload directory.

## Quick start: Docker Compose

```bash
docker compose up --build
```

The API is on `http://localhost:8000`, PostgreSQL is exposed locally on port `5433`.

## First API examples

Create a job from a URL (this records the URL; downloading/processing is not connected yet):

```bash
curl -X POST http://localhost:8000/api/v1/jobs/url \
  -H 'Content-Type: application/json' \
  -d '{"source_url":"https://example.com/my-set.mp3"}'
```

Upload a file:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/upload \
  -F 'file=@./sample-set.mp3'
```

List jobs:

```bash
curl 'http://localhost:8000/api/v1/jobs?limit=20&offset=0'
```

GraphQL query:

```graphql
query {
  jobs {
    id
    status
    sourceType
    sourceUrl
    originalFilename
  }
}
```

## Important product/engineering decisions

1. **A URL is not necessarily a downloadable audio source.** The actual importer must explicitly support permitted providers/direct links, enforce timeouts and size limits, and block loopback/private IPs to prevent SSRF. Do not bypass access controls or DRM.
2. **“Remove all vocals” is not the goal.** DJ speech and music vocals may overlap. We need measured false-positive/false-negative rates and a review interface before destructive cleanup.
3. **One-hour files are asynchronous work.** Upload/import requests should return promptly with a job ID. Worker status should move through a validated state machine such as `queued -> downloading -> analyzing -> cleaning -> completed` (or `failed`/`cancelled`).
4. **No production-ready claims yet.** Authentication, quotas, retention/deletion, malware/format verification, migrations, task queue and real audio processing are not implemented in this starter.

## Proposed milestones

### M1 — API + database (current)
- [x] REST endpoints for job creation, listing and detail
- [x] Upload persistence and extension/size checks
- [x] Segment model and reviewer decisions
- [x] GraphQL query + mutation
- [x] Automated tests for REST and GraphQL
- [ ] Alembic migrations and CI workflow

### M2 — Background processing
- [ ] Job state machine and audit events
- [ ] Redis-backed worker with retry/idempotency tests
- [ ] Safe, supported URL import
- [ ] Duration, codec, file integrity and size checks

### M3 — Audio proof of concept
- [ ] Curated, rights-cleared fixture set with annotated speech intervals
- [ ] VAD-based candidate intervals
- [ ] Separate DJ shouts from musical vocals as far as feasible
- [ ] Export cleaned result and compare original/output
- [ ] Measure precision/recall and audible artifacts

### M4 — Review UI + E2E
- [ ] Timeline and audio preview
- [ ] Keep/remove decisions per interval
- [ ] Full-set export
- [ ] Playwright critical-path tests

## QA portfolio pack to build next

- Test strategy and risk analysis
- Requirements-to-tests traceability matrix
- REST positive/negative/boundary tests
- GraphQL query/mutation and validation tests
- SQL integrity and transaction tests
- Upload validation, interrupted upload and duplicate-submission scenarios
- Async job state transitions, retries, cancellation and idempotency tests
- Audio regression tests against known timestamps and human-reviewed output
- CI report with coverage and reproducible test setup

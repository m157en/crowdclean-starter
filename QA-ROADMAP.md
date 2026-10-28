# QA roadmap

## Critical risks

| Risk | Example | Test approach |
|---|---|---|
| Wrong speech removal | Song vocal is marked as a DJ shout | Curated audio fixtures, golden intervals, manual listening review |
| Missed shout | Short, shouted or reverberant speech is not found | Recall-oriented threshold tests; noisy/reverb fixtures |
| Long-file failure | One-hour set runs out of memory or times out | Representative long fixture, chunk processing, load/resource measurement |
| Broken job lifecycle | Job stays `analyzing` forever | State-machine tests, worker crash/retry test, stale-job recovery |
| Duplicate processing | Retry creates duplicate segments/files | Idempotency key and unique constraints; retry integration test |
| URL import SSRF | URL points to localhost or cloud metadata | Block private/loopback/link-local IPs after DNS resolution; redirect revalidation |
| Unsafe upload | Fake extension, empty file, malformed media, oversized body | Extension + magic/decoder validation, empty/size limit tests |
| Data inconsistency | Segment refers to deleted/nonexistent job | Foreign key, cascade, transaction and migration tests |
| API contract regression | Response field or status changes accidentally | Schema/contract assertions and OpenAPI snapshot review |
| Access-control issue | Another user can access job or exported file | Add auth/ownership tests before multi-user deployment |

## Initial acceptance criteria

1. URL job creation returns `202 Accepted` and a stable job ID without pretending that processing has already started.
2. Unsupported file extensions are rejected; empty and over-limit uploads are rejected; partial files are cleaned up after an error.
3. Unknown job/segment IDs return a documented `404` response.
4. List pagination validates `limit` and `offset` and returns a truthful total.
5. GraphQL reads the same persisted jobs as REST; reviewer decisions are visible through both interfaces.
6. Segment intervals must satisfy `start_seconds >= 0` and `end_seconds > start_seconds`; confidence must be in `[0, 1]`. (Database/API validation to add in the next iteration.)
7. Audio-output acceptance is measured using annotated fixtures and human listening, not just “the export file exists.”

## Suggested test layers

- Unit: URL/filename policy, state transitions, segment interval logic, audio chunk stitching.
- API integration: FastAPI + isolated database, file upload, REST + GraphQL consistency.
- DB: migrations, foreign keys, transaction rollback, indexes and constraints.
- Worker integration: queue retries, timeout, cancellation, duplicate delivery.
- E2E: create job -> monitor status -> inspect intervals -> keep/remove -> export.
- Audio quality: labelled clips including song vocals, DJ shouts, crowd chants, applause and speech over music.

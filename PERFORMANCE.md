# SCENA startup performance — 2026-09-14

## Confirmed production defect

Baseline commit `2a9ffad70d40eff03e760a74cd891c0b2d6673c4`, deployment `dpl_7dDak36rmEfYBEqkneyUaaG7gfvT`.

At 17:43:58 UTC a public request returned 500: the Tornado gateway connected to port 8501 before Streamlit listened. Runtime logs contain `ConnectionRefusedError`; Uvicorn became ready at 17:44:04.986. The request/startup interval was approximately seven seconds. It does not measure the user's complete page load.

## Changes

- The gateway starts accepting requests only after Streamlit's actual HTTP health endpoint returns 200. The readiness wait has a 30-second deadline and cleans up a failed backend.
- A later backend connection failure produces a retryable 503 rather than an uncaught 500.
- The launcher passes completed database initialization to its own Streamlit child, scoped to the exact database path. The launcher itself always clears that marker and performs initialization.
- Reading publications in an initialized cloud process no longer repeats schema creation. Legacy post conversion still runs; offline behavior remains unchanged.
- `/healthz` now includes cumulative startup stage timings. No secrets, customer data or provider URLs are included.

## Measurements

A local libSQL-backed AppTest executed the real public page with an empty seeded database. Only SQL `execute` calls are counted below; these counts are not website latency or Core Web Vitals.

| Experiment | First page SQL calls | Warm rerun SQL calls | Result |
| --- | ---: | ---: | --- |
| Baseline | 81 | 17 | Reference |
| Inherit completed launcher migrations | 18 | 17 | 63 redundant first-page SQL calls removed |
| Also avoid repeated publication schema writes | 11 | 10 | Seven further calls removed on each page |

The baseline also issued one `executemany` on the first page; the revised page issued none. The launcher still performs its initial migration pass and live storage checks. No absolute cold-start speed guarantee is claimed.

Local CPU timings are dominated by imports and vary around 0.26–0.30 seconds; they cannot predict remote SQL round trips. Retention is based on eliminating measured redundant remote operations and the startup race, with production stage timings added for follow-up.

## Correctness

247 tests completed: OK, three existing skips. New regression coverage verifies a unavailable backend returns 503, publication reads preserve legacy conversion without schema writes, and the first accepted HTTP request already reaches a ready real Streamlit application. Cabinet login and subsequent authenticated navigation remain covered by the actual gateway integration test.

The owner's browser performance and mobile network timing require separate confirmation after deployment.

## Second investigation — 18:15 UTC

Baseline production `2d96d86c1704db37dc2f0676786deb765532f958`, deployment `dpl_2mxPRQnVGk6uuXpP6anwGw7nDZ4f`. The owner still reports very slow opening. The startup race fix was insufficient.

Confirmed evidence:

- Separate requests for `/_stcore/health` and `/_stcore/host-config` at 17:56:09 launched separate processes with application-ready timings 4.329 and 4.791 seconds. Other cold starts remain around 4–5 seconds, excluding platform overhead and browser rendering.
- At 18:00:22 a `PUT /_stcore/upload_file/...` launched a fresh process and returned 400. At 18:02:49 multiple `/media/...jpg` requests returned 404.
- Streamlit 1.63's installed upload handler rejects session IDs absent from that process with 400, explicitly identifying replicated deployments without session affinity. The response body of the live failed upload was not captured; its exact rejection message remains unverified.
- The initial document contains 68 module preloads. Two independent HTTP reads of `/static/js/rolldown-runtime.C0FnF6B9.js` at 18:13:44 and 18:13:54 both returned `x-vercel-cache: MISS`, age 0, despite the browser header `public, immutable, max-age=31536000`.
- The currently displayed public hero is a loaded 1200×1200 image with 112,111 characters in its data URI (approximately 84 KB of image bytes). It is not evidence of a huge hero download.

The evidence strongly indicates a session-distribution problem in addition to cold-start latency. Shared SQL and Blob persistence do not make Streamlit's in-memory session, upload and media registries shared. Official sources:

- https://docs.streamlit.io/develop/concepts/architecture/architecture#websockets-and-session-management
- https://vercel.com/kb/guide/docker-on-vercel-vs-render
- https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections

This bounded patch explicitly allows Vercel's CDN to cache only successful content-hashed framework JS, CSS and font responses without Set-Cookie. Login, cabinet responses, errors and unversioned files are excluded. Retain the cache change only after production reads demonstrate a cache HIT; no full-page speedup percentage is claimed.

The container build also sets the initial HTML title to SCENA and the app retains the default crown favicon accepted by the owner. This is branding, not a performance remedy.

**Remaining blocker:** uploads and generated media require session affinity/shared runtime storage, or a different web implementation. The current patch does not solve that architectural issue. Full public-page load time on the owner's device remains unmeasured. Do not call the entire launch complete based on `/healthz`, an HTTP 200, or local single-process tests.

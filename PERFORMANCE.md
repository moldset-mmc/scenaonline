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

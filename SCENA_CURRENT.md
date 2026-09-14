# SCENA — durable production release, 2026-09-14

The owner authorized completing and deploying the existing project. This release replaces the temporary launcher with durable storage and an authenticated cabinet. Production is deployed and the stable domain opens the public site and cabinet login. The receipt below distinguishes live checks from local tests.

## Locations

- Source: https://github.com/moldset-mmc/scenaonline ; production branch `main`.
- Stable site: https://scenaonline.vercel.app ; cabinet: `/auth/login`.
- Vercel project `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6`, team `team_fJicG9DXWXAwA5PRe3Ah4XyI`.
- Historical checkpoint: branch `checkpoint/scena-hosting-2026-09-14`, commit `67e670b422d3b1ac5f10b75ec3998bb8bcd4a004`. It preserves the earlier temporary state and does not auto-deploy.
- Resource IDs and provisioning record: [deploy/HOSTING-PROPOSAL.md](deploy/HOSTING-PROPOSAL.md).

## Implemented

`Dockerfile.vercel` runs `deploy/start_cloud.py`. It requires the existing Production Turso and two Blob connections, plus `SCENA_ADMIN_PASSWORD`. The credential already saved by the owner now applies to Production and Preview; its value was not read or put into Git.

- `scena_database.py`: native authenticated libSQL, SQLite-compatible rows, transactions, constraints, and consistent portable snapshots. Offline installations retain SQLite.
- `scena_media.py`: originals in private Blob, published normalized renditions in public Blob, a durable manifest in Turso, and recovery of container caches. Uploads precede database references.
- `deploy/serve_cloud.py`: same-origin HTTP/WebSocket gateway; cabinet password login, CSRF checks, signed HttpOnly cookies, expiration, and logout.
- Password rotation requires a new deployment. The database stores the active password version; old sessions are rejected on subsequent validation. No raw password is stored in the database or backup.
- Cloud backup/restore validates archives before replacing data and preserves current authentication metadata.
- `/healthz` reports safe deployment/boot identifiers and cloud service acceptance. Startup probes verify transactional SQL, both Blob stores, private access denial, and recovery of a previous persistent probe. No customer records are created by these checks.

## Verification before publication

245 tests completed in the native libSQL test configuration: OK, three existing skips. This includes eight cloud tests covering transactions, media cache loss, backup/restore, cookie expiry/rotation, HTTP/WS authentication, and the actual production launcher with Streamlit navigation. Cloud service probes also passed on Vercel; see the live receipt below.

## Operations and limits

Use the stable domain for future updates. GitHub `main` triggers the existing Vercel production pipeline. Storage credentials are Production-only; a preview deployment requires separately configured durable resources and must not use temporary storage for real data. `deploy/start_preview.py` remains available only for deliberately isolated trials.

[Пароль и восстановление](CABINET-ACCESS.md). The current product has one owner cabinet. Individual user accounts and email password recovery are not implemented. Telegram, AI and payment integrations require their own configuration; creating the three storage resources does not enable them.

Git stores code and starter assets, not live records or uploaded originals. Export private backups through the cabinet. No paid upgrade, new provider, real email, or real customer submission is included in this release.

## Live acceptance receipt — 2026-09-14, 17:19 UTC

- GitHub `main`: `11549a353fd193e8fddea8cd51ed5cfc8c80ec95` before this documentation update.
- Vercel deployment `dpl_JKwShkMfGhq7GCaKeWXfGXd2ZLEc`, target Production, state READY, all three project aliases attached without error.
- `https://scenaonline.vercel.app/` returned HTTP 200. A fresh browser tab rendered the complete public profile in English; switching to Russian rendered the Russian profile and navigation.
- The visible cabinet link opened `/auth/login` with the password field and «Войти» button. The owner's password was not submitted by the agent in the live browser. Authenticated navigation through the actual gateway and Streamlit server passed in the local integration test.
- `/healthz` returned HTTP 200, status `ok`, database/public_storage/private_storage `verified`, private_access `blocked_without_token`, and previous_probe_recovered `true`. Observed boot ID `57dbc08c41a28019`. Runtime logs confirmed both Blob reads returned 200 and unauthenticated private access returned 403.
- A 4×4 public probe image was independently opened in the browser and loaded at its correct dimensions. Checks use only tiny synthetic probe images and a rolled-back database record; no customer forms were submitted.
- Two cloud compatibility faults were fixed using actual runtime evidence: Turso Cloud rejects `PRAGMA busy_timeout`; Vercel consistent cache-bypass Blob reads apply to private stores, not public stores. Both are now handled explicitly.
- No application error appeared in the final browser console check. The browser extension still emitted its own metadata transmission error; this originates from a `chrome-extension://` content script and is not a SCENA application exception.

This documentation-only commit triggers the same verified production code through the existing Git integration. Verify its subsequent deployment READY before final handoff. Future AI, Telegram, payments, individual accounts and email password recovery remain separate configurations/features.

## Startup correction following owner feedback

The owner reported very slow opening. Runtime logs confirmed an actual first-request 500 while the gateway raced Streamlit startup. This release waits for backend HTTP readiness, removes duplicate child migrations and repeated publication schema writes, and exposes safe startup stage timings. Local public-page SQL calls fell from 81 to 11; all 247 tests completed successfully with three existing skips. See [PERFORMANCE.md](PERFORMANCE.md). This is not a measured promise of a particular load time on the owner's device.

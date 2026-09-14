# SCENA — durable production release, 2026-09-14

The owner authorized completing and deploying the existing project. This release replaces the temporary launcher with durable storage and an authenticated cabinet. Live acceptance is pending deployment of this commit; do not interpret local tests as production evidence.

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

245 tests completed in the native libSQL test configuration: OK, three existing skips. This includes eight cloud tests covering transactions, media cache loss, backup/restore, cookie expiry/rotation, HTTP/WS authentication, and the actual production launcher with Streamlit navigation. Cloud service probes still need to pass on Vercel.

## Operations and limits

Use the stable domain for future updates. GitHub `main` triggers the existing Vercel production pipeline. Storage credentials are Production-only; a preview deployment requires separately configured durable resources and must not use temporary storage for real data. `deploy/start_preview.py` remains available only for deliberately isolated trials.

[Пароль и восстановление](CABINET-ACCESS.md). The current product has one owner cabinet. Individual user accounts and email password recovery are not implemented. Telegram, AI and payment integrations require their own configuration; creating the three storage resources does not enable them.

Git stores code and starter assets, not live records or uploaded originals. Export private backups through the cabinet. No paid upgrade, new provider, real email, or real customer submission is included in this release.

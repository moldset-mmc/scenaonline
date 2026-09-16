# SCENA hosting: connection inventory and provisioning receipt

> Historical provisioning receipt from 14 September 2026. Its pending-work statements and allowances describe that date only. Current runtime, completed adapters and installation status: [DEPLOYMENT.md](../DEPLOYMENT.md) and [MBSTUDIO-CHECKPOINT.md](../docs/MBSTUDIO-CHECKPOINT.md). Do not recreate the pilot resources from this receipt.


Date: 2026-09-14 UTC. The three resources below have now been approved, created and connected. Application adaptation and production publication are not completed.

## Verified state

- Repository: `moldset-mmc/scenaonline`, `main`, commit `d838bd5b7a6dade1a9120f27b1103e0eb6980266`.
- Vercel team: `team_fJicG9DXWXAwA5PRe3Ah4XyI` (`moldset-8968s-projects`).
- Existing project: `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6` (`scenaonline`).
- The repository was NOT connected when inspected. It was connected during this session; the Vercel Git settings subsequently displayed `moldset-mmc/scenaonline`, `Connected just now`, and `Disconnect`.
- Production branch tracking: `main`; primary domain: `scenaonline.vercel.app`.
- Framework: Container; root directory: repository root; ignored build step: Automatic.
- Existing preview: `dpl_9RJtfKCkwFkYzy1dP9nAbKkg5he2`, READY, no production target. No new deployment was triggered by this session.
- Current container runs `deploy/start_preview.py`. It creates a new SQLite database and media directory under a temporary directory, forces `SCENA_PREVIEW_ONLY=1`, and refuses `VERCEL_ENV=production`.
- The live cabinet displays that access is closed. Its code requires a configured administrator password.
- At the initial inspection, no dedicated SCENA database was connected. After provisioning, the project Storage overview listed all three resources below as Available. Resources belonging to other projects were not changed.

Evidence links:
- https://vercel.com/moldset-8968s-projects/scenaonline/settings/git
- https://vercel.com/moldset-8968s-projects/scenaonline/settings/environments
- https://github.com/moldset-mmc/scenaonline/commit/d838bd5b7a6dade1a9120f27b1103e0eb6980266
- https://scenaonline-qapdlms9m-moldset-8968s-projects.vercel.app/

## Approved resource creation — completed

Use only the existing SCENA Vercel project and team above. No paid plan, trial, or upgrade was selected.

| Resource | Created name | Intended purpose | Access and cost ceiling |
| --- | --- | --- | --- |
| Turso database, compatible libSQL engine | `scenaonline` | Profile, services, bookings, orders, cabinet records | Server-side access; Starter $0/month selected |
| Vercel Blob store | `scenaonline-public` | Images explicitly published by the owner | Public; existing Hobby allowance only |
| Vercel Blob store | `scenaonline-private` | Original uploads and unpublished media | Private; existing Hobby allowance only |

The installation UI showed US East (Virginia), iad1, for Turso and IAD1 for both Blob stores. All three connections are scoped to Production only. Their existence does not mean application data has been migrated.

Published allowances checked on 2026-09-14: Turso Free is $0/month with 5 GB storage. Vercel Blob Hobby includes 1 GB storage, 10 GB transfer, 10,000 simple operations and 2,000 advanced operations; limits are shared, and remaining account allowance was NOT checked. These are bounded free allowances, not unlimited service. Reaching Vercel Hobby limits can make Blob unavailable without charging for overage.

Provider sources:
- https://turso.tech/pricing
- https://vercel.com/docs/vercel-blob/usage-and-pricing
- https://docs.turso.tech/sdk/python/reference
- https://vercel.com/docs/functions/container-images

## Required implementation before production publication

1. Introduce a shared database adapter and route all application database access through it. Direct SQLite access currently exists in core, cabinet, publications, shop, portfolio, model intro, model builder, prompts, licensing, and transfer/backup code.
2. Preserve transaction boundaries, row mapping, constraint handling, schema migrations, booking conflict protection, and backup semantics. A connection-string replacement is insufficient.
3. Introduce a media storage adapter. Upload to durable storage before committing a database reference; preserve private originals and use public storage only for approved published images. Cover uploads, reading, restyling, export, backup and restore. Local files may serve as a cache only.
4. Add a production launcher which requires durable storage and a configured administrator password. Keep the current preview launcher isolated. Select the production launcher only after validation; do not remove its current production guard as a shortcut.
5. Use the server-only database and Blob variables already injected by the integrations; do not generate duplicate resources. Configure the cabinet password privately. Never place its value in Git, logs, or the image build context. See [CABINET-ACCESS.md](../CABINET-ACCESS.md).
6. Check cabinet navigation and session recovery so normal navigation does not repeatedly lose authentication. This behavior has not been verified on a durable online instance.
7. Publish the reviewed commit to the existing project and verify the permanent domain. Future `main` updates should use Git integration. A successful push-triggered build has not yet been tested.

## Local compatibility check performed

In an isolated Python 3.12 environment, `libsql==0.1.11` was checked against database features used by SCENA. It supports transactions but its Connection has no `row_factory` or `backup`; a unique-constraint failure raises `ValueError`, not `sqlite3.IntegrityError`. These differences must be addressed explicitly by the adapter. This check does not verify a remote database.

The official Vercel Python SDK (`vercel==0.10.0`) was installed in the isolated environment and its Blob `put`/`get` signatures were inspected. No upload or remote storage request was made. Application dependencies remain unchanged. The checkpoint includes a separate preview-only password-length change, locally verified by four preview tests; it is not deployed.

## Publication acceptance evidence required

- A deployment ID linked to the exact reviewed Git commit, with READY status and successful HTTP checks on `scenaonline.vercel.app`.
- Successful cabinet sign-in, navigation and a saved profile change.
- A saved test image visible after a fresh container/deployment.
- A test booking and order retained after restart; conflicting bookings handled correctly.
- Unpublished originals inaccessible through public URLs.
- Backup and restore tested against isolated test data.
- No claims about notifications, Telegram, AI or payment integrations until each is separately verified.

## Earlier approval-review stop — resolved by explicit approval

After choosing Turso in Vercel's Browse Storage dialog, clicking Continue was rejected by automatic approval review. The stated reason was that it might provision persistent or billable external resources and inject environment variables, while this provider/resource creation had not been specifically authorized. No retry or alternate provisioning route was used. That operation stopped at the time; the later specific approval below resolved this block.

The owner subsequently answered `да` to the exact proposal to create these three resources on free terms. The authorized creation was then executed through Vercel's normal UI.

## Provisioning receipt — 2026-09-14

| Resource | Verified identifier | Verified state |
| --- | --- | --- |
| Turso `scenaonline` | Vercel `store_qEZAoDse2bOrRqaz`; Turso `01a0a088-7601-738d-b6ad-0d88880d2437` | Available; Starter, $0/month; US East (Virginia), iad1; connected to SCENA Production |
| Blob `scenaonline-public` | `store_SKh2gUtGGbN0Dcmn` | Public; IAD1; Hobby included limits; connected to SCENA Production |
| Blob `scenaonline-private` | `store_UDvDMqrvzblORjsg` | Private; IAD1; Hobby included limits; connected to SCENA Production |

Turso integration: `icfg_hQHBYaEJNdQzjemJFy0ZwClJ`.

Verification pages:
- https://vercel.com/moldset-8968s-projects/scenaonline/integrations/tursocloud/icfg_hQHBYaEJNdQzjemJFy0ZwClJ/resources/storage/store_qEZAoDse2bOrRqaz/projects
- https://vercel.com/moldset-8968s-projects/scenaonline/stores/blob/store_SKh2gUtGGbN0Dcmn/projects
- https://vercel.com/moldset-8968s-projects/scenaonline/stores/blob/store_UDvDMqrvzblORjsg/projects

Provider-generated variable names (values were not revealed):

```text
SCENA_TURSO_TURSO_AUTH_TOKEN
SCENA_TURSO_TURSO_DATABASE_URL
SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN
SCENA_PUBLIC_BLOB_STORE_ID
SCENA_PUBLIC_BLOB_WEBHOOK_PUBLIC_KEY
SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN
SCENA_PRIVATE_BLOB_STORE_ID
SCENA_PRIVATE_BLOB_WEBHOOK_PUBLIC_KEY
```

Both Blob creation forms initially connected Production and Preview. Their connections were updated and independently read back as Production only. The Turso connection was created for Production only and its project table was also read back. Sensitive settings remained enabled. No database query, image upload, paid subscription, trial, or paid upgrade was executed.

The final Vercel project read still returned the original preview deployment `dpl_9RJtfKCkwFkYzy1dP9nAbKkg5he2`, READY, with `target: null`. Resource provisioning does not make the existing application use durable storage or enable the cabinet. All implementation and publication acceptance items above remain outstanding.

## Checkpoint publication

[SCENA_CURRENT.md](../SCENA_CURRENT.md) records the source baseline and remaining launch work. Resource IDs and variable names are documented here; secret values and live database/media contents are not part of the checkpoint. The checkpoint is prepared on `checkpoint/scena-hosting-2026-09-14`. Its `vercel.json` disables automatic deployments only for that exact branch, leaving other branches at Vercel defaults. Verify remote publication separately; this document alone is not proof of a GitHub push.

## Cabinet credential receipt

After provisioning, the owner entered and saved `SCENA_ADMIN_PASSWORD` in Vercel. Browser readback confirmed the variable exists as a Secret scoped to Preview only. No value was read or written into Git. The offered Redeploy dialog was cancelled: the old source baseline rejects eight-character passwords, so a reviewed preview commit containing the length change must be deployed first. Cabinet login remains unverified. The three storage resources retain their Production-only connections.

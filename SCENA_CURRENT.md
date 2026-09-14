# SCENA global checkpoint — 2026-09-14 UTC

## Read this first

Scope: the existing SCENA online project and its source, hosting connections, cabinet access, and launch handoff. Public preview exists. Durable production launch is NOT complete. This checkpoint records configuration and code; it is NOT a backup of a live database or uploaded media.

Source baseline freshly checked on GitHub: `moldset-mmc/scenaonline`, `main`, `d838bd5b7a6dade1a9120f27b1103e0eb6980266` (2026-09-06, “Keep preview credential-free and document deployment handoff”). Do not substitute the separate legacy repository `moldset-mmc/scena`.

Checkpoint branch: `checkpoint/scena-hosting-2026-09-14`. The commit containing this file is the checkpoint identifier. A local commit is not evidence of a push: read the remote branch before claiming GitHub persistence. `vercel.json` suppresses automatic deployment only for this exact checkpoint branch; other branches retain default behavior. Do not merge into `main` just to save notes: its current production launcher is still incompatible with Production.

## Verified external state

| Component | Verified state |
| --- | --- |
| Vercel team | `moldset-8968s-projects`, ID `team_fJicG9DXWXAwA5PRe3Ah4XyI`, Hobby |
| Existing project | `scenaonline`, ID `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6` |
| Git connection | Connected to `moldset-mmc/scenaonline` during this session; production branch `main` |
| Runtime settings | Container; repository root; Node 24.x; Ignored Build Step Automatic |
| Latest deployment at checkpoint | `dpl_9RJtfKCkwFkYzy1dP9nAbKkg5he2`, READY, `target: null` |
| Existing public preview | https://scenaonline-qapdlms9m-moldset-8968s-projects.vercel.app/ |
| Configured project domains | `scenaonline.vercel.app`, `scenaonline-moldset-8968s-projects.vercel.app`; production serving not accepted yet |
| Turso database | `scenaonline`, Available, Starter $0/month, iad1, Production connection |
| Public Blob | `scenaonline-public`, Available, Public, IAD1, Production connection |
| Private Blob | `scenaonline-private`, Available, Private, IAD1, Production connection |

Full resource IDs, exact environment-variable names, provisioning receipt and verification links: [deploy/HOSTING-PROPOSAL.md](deploy/HOSTING-PROPOSAL.md). All three were approved and created. Do not create duplicates or reconnect resources belonging to other projects. Secrets were not revealed; only names belong in source control.

No new deployment, remote SQL query, image upload, migration, paid plan or trial was performed when provisioning these resources. The final project Storage overview was rechecked and showed all three as Available. Provider credentials are connected to Production only, not the temporary preview.

## Code and data state

- Streamlit SCENA Pilot V1.7 still uses SQLite and local media. The current container runs `deploy/start_preview.py`, creates an isolated temporary database/media directory and sets `SCENA_PREVIEW_ONLY=1`. It rejects `VERCEL_ENV=production`.
- No database or media adapter has been implemented. Direct SQLite usage occurs in core, cabinet, publications, shop, portfolio, model intro, model builder, prompts, licensing and transfer/backup code.
- Local `libsql==0.1.11` probe: transactions work, but `row_factory` and `backup` are absent; a unique constraint raised `ValueError`, not `sqlite3.IntegrityError`. Preserve row mapping, transactions, schema migrations, conflict checks and backup explicitly.
- `vercel==0.10.0` Blob SDK signatures were inspected locally. No remote write test was performed. Runtime dependencies remain unchanged.
- Git contains source and bundled starter media (about 8.4 MB), not an owner's working database, orders, bookings, private photos or provider credentials. These must eventually be backed up through the data layer, separately from Git.

## Cabinet and latest owner request

The live cabinet was closed when checked. Current auth uses one configured administrator password, not individual user accounts. The owner requested an eight-character temporary password plus change/recovery instructions. This checkpoint changes only the isolated preview password minimum from 16 to 8, keeps missing-password access closed and preserves the production guard. The actual secret is not embedded or saved here; it has not been entered by the agent. Four preview-isolation/password tests passed locally.

[Кабинет: пароль и восстановление](CABINET-ACCESS.md) documents private setup, redeployment, owner recovery through Vercel and the proposed future email reset flow. The owner subsequently entered and saved the credential through the browser. Readback confirmed `SCENA_ADMIN_PASSWORD` exists as a Secret for Preview only; its value was not read and sign-in is not yet verified. Vercel offered Redeploy after saving; that dialog was cancelled because baseline code still rejects eight-character passwords. No email reset, account registration or automatic session revocation exists yet.

## Browser observations and limits

Observed earlier in this session: public RU/RO/EN pages loaded; the Model gallery and pause/frame selection worked; a clean booking sequence reached the contact form. No real personal data was entered or submitted. Market/portfolio content was empty or placeholder. These observations are not acceptance of durable writes.

A booking return/reconnect lost selection once; a clean retry succeeded. Site console showed one WebSocket error and a component-registration warning. Browser-extension metadata errors were also reproduced on another site. The extension messages are not evidence that SCENA caused the chat stream interruptions. No full network trace or conclusive common root cause was established. Mobile, cabinet, upload durability, restart survival, backup/restore, Telegram, AI and payments remain unverified.

## Resume in this order

1. Read this file, the hosting receipt and cabinet guide. Fetch current remote refs and check for later owner changes. Recheck only state needed for the next action; preserve other worktrees and staged work.
2. For an immediate cabinet trial, use a reviewed preview commit containing the 8-character support and a privately configured Preview password. Do not redeploy baseline code with a short password. A trial still has temporary data.
3. Implement a shared database adapter with local compatibility tests, then verify against an isolated remote test namespace. Preserve SQLite semantics relied on by the app; URL substitution alone is insufficient.
4. Implement durable media storage across uploads, display, generated images, publication, export and restore. Upload durably before writing database references. Keep unpublished originals private; publish only owner-approved assets.
5. Add a Production launcher requiring durable storage and a configured administrator credential. Keep preview isolation. Add proper session invalidation and agree the account/recovery scope before advertising self-service reset.
6. Verify cabinet sign-in/navigation, saved profile, a test booking/order, image persistence after a fresh container, private access controls and backup/restore against disposable test data.
7. Preview the exact publication commit and target, execute the approved release through the existing Git/Vercel connection, and read back deployment SHA/ID, READY status and the permanent project domain. A push-triggered successful build is not yet proven.
8. Update this checkpoint with actual outcomes and failures. Do not label the site operational until these persistence/access checks pass.

## Decisions and approval state

Reuse the current repository, Vercel project and created resources. The owner wants a stable address and future updates through GitHub. The existing long URL identifies a particular preview deployment; future releases need the verified stable project domain. Do not claim it automatically changes with a settings update.

Git connection and the specific three free resources were already authorized and completed. The temporary password request is explicit; do not re-request its intended value in chat. For other external changes, present the concrete diff/target, obtain the necessary approval, execute, then read back. No approval for paid upgrades or real outgoing messages is implied.

## Short resumption prompt

> Продолжи запуск SCENA из `moldset-mmc/scenaonline`. Сначала прочитай `SCENA_CURRENT.md`, `deploy/HOSTING-PROPOSAL.md` и `CABINET-ACCESS.md` из актуальной ветки чекпойнта. Три ресурса уже созданы; используй их. Заверши постоянное сохранение, кабинет и проверку запуска на существующем проекте Vercel. Не считай подготовленные настройки доказательством работающего сайта.

## Provider reference

[Vercel branch deployment configuration](https://vercel.com/docs/project-configuration/git-configuration): unspecified branches default to enabled; this checkpoint disables only its named branch.

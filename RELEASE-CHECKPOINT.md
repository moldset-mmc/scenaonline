# SCENA native web release — verified 2026-09-14

## Published version

- Site: https://scenaonline.vercel.app
- Cabinet: https://scenaonline.vercel.app/auth/login
- Repository: https://github.com/moldset-mmc/scenaonline
- Production branch: main
- Production commit: dbbef60c744a4b06d0f182c79f7ccc8510778589
- Exact source tree: be7f397adfc82fcd2f00ec38f2d5f56dae49d60e
- Vercel deployment: dpl_45dAM52L7jdK1ixaBiEcdDJue7Ru
- Deployment hostname: scenaonline-alor7gp0q-moldset-8968s-projects.vercel.app
- Deployment state and production alias read back: READY, scenaonline.vercel.app
- Runtime health: native-html, exact production commit above.

## What was verified

The live health check verified Turso, both existing Blob stores, denial of
unauthenticated access to private Blob and recovery of a previous probe. The
first process reported startup 3.115 seconds, including deployment checks.

The actual browser displayed the complete existing scene with the saved owner
name, portrait and navigation. Its native runtime marker was read from the DOM.
The initial rendering fetched 3 resources instead of the baseline's 77 entries.

The owner cabinet opened with the existing login cookie. The section control
navigated from Work to Pages. Saving the existing, unchanged profile returned
“Моя Сцена сохранена.” Reloading the cabinet read back the same owner name.
The public booking UI changed services and navigated to the nearest available
day, then displayed the actual available appointment times. No synthetic client
request was added to production. The live Model page rendered its intro, text,
portrait, QR and navigation inside its frame.

## Full scene timing, same cloud browser and URL

| Version / condition | TTFB | Content, hero and fonts ready |
|---|---:|---:|
| Streamlit baseline, reload 1 | 582 ms | 11,758 ms |
| Streamlit baseline, reload 2 | 543 ms | 12,608 ms |
| Native, first request after deployment | 5,402 ms | 6,357 ms |
| Native, reload 1 | 797 ms | 874 ms |
| Native, reload 2 | 638 ms | 742 ms |

These are measured browser values, not server-only timings or a promise for all
networks. Caches were already used for the reload comparisons. The first native
request included startup and new deployment initialization. Background-tab
paint entries were occasionally absent; content readiness used the identical
local-only measurement script in both versions. The second native reload also
reported FCP/LCP 728 ms. No external analytics were configured.

## Automated acceptance

- Existing suite: 248 tests, OK, 3 skipped according to suite conditions.
- Native HTTP suite: 11 public routes and 18 cabinet views.
- Two HTTP application instances over one isolated database: profile persistence,
  one-use action token, upload over 3 MiB split between instances and validated
  by the original image pipeline, public inquiry, complete appointment workflow,
  portable backup download and rejection of anonymous private downloads.
- The same acceptance passed through the libSQL driver.
- Native imports passed with Streamlit imports explicitly blocked.
- QR cabinet HTML fell from about 5.3 MB to 63 KB in the isolated fixture.

## Boundaries and remaining observations

- Live browser acceptance used desktop viewport. A phone/real mobile network
  and Chrome DevTools device emulation were not available in this browser.
- Synthetic booking, chunked upload and backup transfer were tested against
  isolated fixtures. Production Blob/Turso acceptance was independently verified
  by the live deployment health checks. These are different evidence scopes.
- The cloud browser still logged “Error sending browser metadata to extension”
  from chrome-extension://kcdongibgcplmaagnmgpjhpjgmmaaaaa/content-script.bundle.js.
  It is a browser extension error, not emitted by SCENA. No SCENA application
  error was observed in the inspected browser log or Vercel error-log query.
- Authenticated form state expires after 12 hours. A submitted/expired form must
  be reopened; duplicate delivery is rejected rather than repeating a write.
- Temporary private objects have a 12-hour access expiry; automated Blob object
  deletion is not implemented. Retention cleanup is a separate follow-up.
- Editing photographs still hydrates the existing private media cache for editor
  compatibility. Public page rendering does not hydrate the entire media library.

## Recovery and ongoing work

Main continues to deploy through GitHub to the same Vercel project. The three
existing durable resources and existing password environment are preserved.
No provider migration, new subscription or domain change was made.

For emergency rollback, promote the known baseline deployment
`dpl_ChEPDM8Zyfi3kemThoMptoz6ojxG`, commit
`a6f5ae4e88c95788dc6a579586dd54761293b2a5`. Its original frontend remains in Git.
Do not delete the database or Blob stores when reverting frontend code.

This checkpoint branch disables its own Vercel deployment. Its documentation
commit records the production version above and does not replace that version.

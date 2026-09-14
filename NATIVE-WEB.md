# SCENA native Vercel web runtime

## Change and purpose

The cloud image starts `deploy/start_web.py`: one Tornado HTTP process returns
complete HTML. Streamlit, its browser runtime and its WebSocket gateway are not
installed or started in this production image. The desktop distribution keeps
Streamlit through the explicit `scena_ui.py` presentation boundary.

The existing public pages, forms and cabinet invoke the existing domain
validation and SQL transactions. A small server-side HTML component layer and
plain JavaScript implement the controls. No new provider or paid service.

- Main site: https://scenaonline.vercel.app
- Cabinet: https://scenaonline.vercel.app/auth/login
- Turso remains the authoritative database; the existing public/private Blob
  stores and administrator password remain the configured resources.
- Forms are encrypted in Turso, expire after 12 hours and have single-use tokens
  bound to a Secure, HttpOnly, SameSite browser cookie. They can reach any replica.
- Files are uploaded in chunks of at most 3 MiB. Private Blob stores the chunks;
  the final form validates their owner, allowed field, extension, size and hash.
- Downloads require both the owner login and the browser that prepared them.
  They use shared private storage and stream over HTTP.
- Backups exclude transient web tables and reusable authentication material.
  Existing owner content and portable backup validation remain intact.
- Public bundled photographs are resized and converted at build time to hashed
  WebP assets. The build only includes the explicit approved media allowlist.
  Uploaded photographs use approved public renditions or signed image routes.
- Only anonymous HTML without form state uses the short shared cache. Private
  pages, errors, forms and downloads use no-store. Hashed assets cache for a year.

## Verification

`python tests/native_web_acceptance.py` starts two independent HTTP application
instances over the same isolated database. It checks 11 public pages and 18
cabinet views, actual profile saving, duplicate-action rejection, an image over
3 MiB uploaded between instances, public inquiry persistence, the complete
service/date/time/contact booking flow, private backup download and anonymous
access denial. Run it separately from desktop tests to isolate UI imports.

`SCENA_DB_DRIVER=libsql python tests/native_web_acceptance.py` repeats that
acceptance through the same libSQL driver used in production, with local test
storage. These tests do not claim to exercise live Turso or Blob credentials.

`python -m unittest discover -s tests -q` checks the existing desktop/domain suite.

## Browser baseline and deployment acceptance

The measurement-only baseline is main commit
`a6f5ae4e88c95788dc6a579586dd54761293b2a5`, production deployment
`dpl_ChEPDM8Zyfi3kemThoMptoz6ojxG`.

In the same cloud browser, reloads of `/?page=scene&lang=ru` measured:

| Trial | Initial response | Hero/content/fonts ready |
|---|---:|---:|
| 1 | 582 ms | 11,758 ms |
| 2 | 543 ms | 12,608 ms |

The cache was already used; these are not cold-cache tests. Some paint entries
were absent in a background tab, so the primary comparison is the DOM/hero/font
readiness measurement, not a fabricated LCP. `scena_web/measure.js` is identical
to the baseline measurement script and sends no analytics. Read the hidden
`#scena-performance` output's `data-metrics` attribute for actual browser values.

Post-deployment measurements and the exact verified deployment are recorded in
the release checkpoint after deployment. HTTP 200 alone is not the acceptance.

## Rollback

Vercel can promote the measurement-only baseline deployment above. Its original
Streamlit code remains in Git, and the new SQL tables do not modify existing
owner tables. Do not delete Turso or Blob data during a rollback. Returning to
the old frontend also returns its measured delay and instance-bound sessions.

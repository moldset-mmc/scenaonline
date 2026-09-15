# Unified photos — review package

Base: `e1c47d29ae4f5b2d57950f9ce4c767be779604ec`, repository
`moldset-mmc/scenaonline`, branch `main`. Prepared locally; not published.

## Behavior

- Cabinet menu → Photos collects bundled and uploaded images. Thumbnails are
  paginated (12 at a time), with filters for each page, posts and saved photos.
  Page editors link to their filtered catalog. My Scene now previews its actual
  fallback image instead of describing it only as a branded image.
- Each photo lists its configured placements and retained history. Publication
  renditions map to their original, including restyled versions in other folders.
- Upload stores the exact original privately without assigning it to a page.
  Assignment and replacement act on one selected placement. Old originals stay
  available; no deletion or bulk replacement action is introduced.
- Destinations: My Scene, Professional/booking/course covers, Model intro and
  looks, both portfolios, and the three photo positions of existing products.
  Posts retain their own editing/publication flow and have a link to that editor.
- Implicit Model portfolios and Professional/course cover fallbacks are frozen
  when their source is replaced, so other placements retain the previous image.
  Two additive profile keys hold independent Professional and course covers.
- Original downloads require an authenticated owner and resolve an opaque ID
  against the media inventory. Private storage URLs/credentials are never emitted.
  Paths, symlinks, formats and dimensions are validated. Listing does not hydrate
  originals. Upload failure retains existing references; assignment checks the
  previous value/revision and uses the existing product service for Market.

## Evidence

- Python: 298 tests, OK with 3 pre-existing optional skips; 14 focused photo tests.
- Photo HTTP: three locales, 12-card pagination, exact original download, owner
  authorization, missing ID, real chunk upload, duplicate rejection, stale form
  protection, and assignment across two native server replicas.
- Full native HTTP acceptance: public routes, cabinet, original booking/order/
  schedule/Telegram-adapter workflows and private backup; isolated test data.
- Source compilation and immutable asset build pass. Review HTML contains actual
  application responses rendered against isolated data, with form tokens removed.

This is functional evidence, not a mobile visual/device pass. The available browser
previously rejected local preview URLs; no alternative browser or tunnel is used.
Samsung, soft keyboard and live cloud behavior of this new feature are unverified.
The preview offers widths 320/360/390/412/430/768/1024 and RU/RO/EN for owner review.

## Publication contract

The exact offline preview contains the complete diff and per-file SHA-256 values.
After approval, recheck the remote base and all hashes, commit the reviewed change
as `Add unified owner photo library`, and update the existing `main`. Its existing
Vercel integration deploys to `https://scenaonline.vercel.app/`. Verify that commit,
deployment readiness, health and read-only catalog views after publication.
Do not upload, replace or delete the owner's real photos during verification.

Rollback can revert the code without deleting media or resetting profile settings.
Keep the photo metadata/originals and any additive cover values for recovery.

# Introduction QR and photo trash — review package

Base: `813c3604fb81e573040b4e0de3990d4dd475b817`.
Status: prepared locally; publication requires approval of this exact package.

## User flows

- Cabinet → Pages → Model → Business card → QR code: choose a destination, open
  the QR preview, optionally align it with the photographed square, save QR.
- Destinations: Model, Professional, service booking, My Scene, Market, course,
  Model portfolio and Professional portfolio. The selected page and current
  language are encoded; the photo and other public links are independent.
- Placement is the centre in percent of image width/height, with size in percent
  of the shorter image side. Native preview supports tapping the image while
  the alignment controls are expanded. Number fields provide precise adjustment.
- The public QR always opens a labelled dialog with the selected page link and
  PNG download. The original implementation enabled this only for one filename,
  replacing it with a noninteractive bottom caption for all other photos.
- Known supplied photographs retain their original measured default positions.
  A different composition needs alignment in the owner preview. Saved placement
  survives replacing the photograph; no automatic object detection is claimed.
- Cabinet → Photos → photo → Delete photo → Move to Trash. Only currently unused
  photos can move to Trash. The toolbar and filter expose Trash; each item has
  Restore photo. Original bytes and historical references remain available for
  restoration. This is reversible deletion from the catalog, not a storage purge.

## Persistence and protection

QR settings join the existing additive introduction settings and public export.
QR saves compare the QR settings and photo seen by the editor in one transaction;
they do not overwrite text/photo changes. A stale QR editor must reload.
Public cache invalidation uses the existing profile-settings trigger.

Photo trash uses one `photo_trash:<path hash>` metadata record per original in
profile_settings. The reference check and trash marker write share a transaction.
Assignments from Trash are rejected. If an older page version explicitly reuses
an original, its active usage takes precedence and the photo is visible again.
No live owner records, photos, Telegram messages or credentials were changed.

## Evidence and limits

- Reproduced the baseline fallback with a different supplied portrait: corner
  figcaption present, overlay button absent.
- Nine added unit tests cover 24 destination/language combinations (QR PNG
  matches the selected URL's encoding), independent saves, stale edits,
  validation, default positions, trash/restore and active-use protection.
- Native HTTP test covers RU/RO/EN editor/public rendering, QR save across two
  server instances, repeat save, subsequent text save, cache refresh and the
  owner-only trash/restore journey.
- DOM tests use those HTTP documents and the actual QR script: contain/cover
  geometry, widths 320–768, at least 44px hit area, modal/focus behaviour,
  all destinations, direct positioning, and a replaced preview after save.
  These are simulated geometry tests, not rendered mobile-device screenshots.
- Existing native acceptance, photo HTTP and native DOM checks pass. Full suite
  initially exposed missing portable-distribution files; the QR module/assets
  were added and both affected restore suites passed (one optional skip).
- A live read confirmed the bottom QR on the replaced photograph. Local preview
  browser access was previously rejected and was not bypassed. The included
  offline preview contains the actual isolated HTTP HTML, CSS and QR script.
- Physical Samsung, camera scanning, keyboard layout and the new production
  deployment are not verified. Existing optional browser tests remain skipped.

Browser behaviour follows the documented dialog and image-fit APIs:
[dialog](https://developer.mozilla.org/en-US/docs/Web/API/HTMLDialogElement/showModal),
[object-fit](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/object-fit).

## Publish proposal

After APPROVE: recheck base and all reviewed hashes; commit exactly the reviewed
files to `moldset-mmc/scenaonline`, main, with message
`Fix configurable introduction QR and add photo trash`. The existing Vercel
integration deploys to `https://scenaonline.vercel.app/`. Verify deployment SHA,
health and read-only owner/public views. No additional photo assignments, QR
configuration writes, deletions, real orders or messages form part of publication.

# MBStudio mobile homepage and publication branding

Source repository: `moldset-mmc/scenaonline`, branch `main`.
Production address: `https://mbstudio.scena.life/ru/`.
Baseline: `6c1402ec0ccef9709ed67fd4e20f6d4fd8bd5c5c`.

## Delivered presentation

- Compact header: muted MB Studio. badge and the accepted SCENA.live artwork.
- Quiet navigation: My Scene, services/courses, `shop`, then the remaining pages.
- Cormorant Garamond headings/manifesto, Manrope body and controls, handwritten
  owner signature. Fonts are self-hosted; see `HOMEPAGE-FONTS.md`.
- Editable localized service heading and description before the existing booking
  action. The saved button label and destination remain controlled by the owner.
  Empty descriptions stay hidden until filled in the cabinet.
- Instagram icon and compact model SCENA link, with the shortened solid crown.
- Common page edges and quieter publication cards; mobile heading scroll stop
  respects reduced motion and does not affect desktop.

## Fixed artwork and two placements

The SVG files and transparent PNG under `scena_web/static/scena-live-*` are the
technical master derived from the owner-approved screenshot. Internal geometry
is fixed. `model-crown.svg` uses the same crown, without the extra lower bar.
Artwork restoration limitations remain documented in the separately supplied
SCENA.live brandbook.

`scena_brand.py` applies the entire mark to the fitted photograph:

- `editorial`: top center, 31% of photo width, top offset 2.5%, subtle shallow
  relief with a varying translucent fill. This implements the latest approved
  journal preview, which supersedes the earlier flat 36% / 62% trial.
- `compact`: lower left, 28% of photo width, 4% left/bottom offsets, opacity 94%.

Color adapts to the area underneath the mark. There is no opaque label or frame.
Both options are exposed in the publication editor and stored in its existing
JSON revision history. Social exports keep the selected mode. Original files
and old published renditions remain unchanged; saving and publishing an edited
post produces a new derivative from its original.

## Boundaries

No domain, URL, redirect, H1, metadata, canonical, hreflang, robots, sitemap or
analytics changes. No pricing, booking rules, Telegram configuration, owner
credentials, live content replacement or checkpoint merge. Existing RU/RO/EN
fields are retained; new owner fields follow the existing translation validation.

## Verification and rollback

Run the asset build, `tests/scene_home_http.py`, `tests/native_web_acceptance.py`,
the publication domain/frame tests and the existing MBStudio/SEO regression
checks. Native tests use isolated data and mocked Telegram delivery.

The local browser surface blocked loopback/file previews. This is a verification
limitation, not a passed mobile or desktop visual test. Check the deployed page
at narrow widths and on desktop after release.

Baseline production rollback candidate: `dpl_CaSGwvnrgzNA7KsFXX17mHxt3PLe`.
Revert the release code or restore that deployment; keep all database and Blob
data. The new placement field is additive JSON metadata and needs no destructive
database migration.

# Mobile refinement — prepared for review

Base: `60afda8272865e6eec05d514adaa9f573a08dbb5` in
`moldset-mmc/scenaonline`, branch `main`.
Status: local implementation and automated checks complete; publication pending
approval of the combined mobile preview. The earlier three-file request-card
preview is superseded by this package.

## Changed behavior

- The native cabinet uses one compact header and a section menu. Only the active
  section's views appear below it. Language and logout are in the menu.
- The overview prioritizes requests, orders, schedule and services. Requests and
  orders use compact lists; a direct link opens just the selected record, with
  phone, chosen reply channel, dates and status. Additional details are collapsed.
- My Scene and Professional organize translations in RU/RO/EN tabs. Model uses
  separate business-card, images, portfolio and settings tabs. The schedule uses
  regular hours, individual days and exceptions tabs. Product photos and Telegram
  connection settings use expandable sections.
- Shared controls use readable text, phone/email keyboards, larger tap areas,
  narrower page gutters, stacked fields and safe-area spacing. Booking reduces
  its decorative header on phones. Shop dialogs fit the available viewport.
- The standalone Model page allows vertical scrolling on phones, expands its
  introduction with content and uses larger controls. Its containing iframe
  follows the viewport height instead of a fixed 920 px height.
- A server-rendered validation error returned with HTTP 200 now blocks a queued
  cabinet navigation and receives focus. Saving retains selected tabs and both
  expanded and deliberately collapsed settings. Unsubmitted neighboring form
  values already survived ordinary saves; this behavior is regression-tested.
- English is retained when routing through the cabinet.

Business validation, booking conflict checks, authorization, persisted record
schema, Telegram status callbacks and external notification protocols are not
changed by this package. Tests use isolated records and intercepted Telegram
adapters, with no messages or status changes in the owner's live account.

## Verification

- Full Python suite: 284 tests, OK, 3 optional skips.
- Real local HTTP: all 11 public routes and 18 cabinet views in RU/RO/EN (87
  route/language combinations), plus authenticated direct records, missing IDs,
  schedule save/reset, photo upload, checkout, service booking, status changes,
  login return destinations and private backup access across two instances.
- JavaScript DOM tests: menu dismissal/focus, form scope, repeat save with a fresh
  token, unchanged neighboring input, tab and disclosure state, validation-error
  focus, gallery navigation, contact fields and zero-request local interactions.
- 102 rendered fixture documents inspected for duplicate IDs and broken label
  associations; no issues found. Immutable asset build: 21 resources.

These are functional and structural checks, not screenshots or proof of mobile
layout. New-version visual inspection at 320/360/390/430/768 px, soft-keyboard
behavior and Samsung/Telegram browser handling remain unverified. The available
browser rejected local preview URLs; no alternate browser or tunnel was used.
The external source analyzer was rejected by automatic approval review; source
inspection and project-owned tests were used instead.

## Publication after approval

Review the combined preview, its exact diff and file hashes first. The proposed
commit is `Refine mobile cabinet navigation and public layouts`. Push that reviewed
change to the existing `main` only after approval; its Vercel integration publishes
to `https://scenaonline.vercel.app/`. Recheck the base and diff before the write.
Verify the resulting deployment and live read-only views afterward. Do not
describe this local preview as a deployed or device-verified release.

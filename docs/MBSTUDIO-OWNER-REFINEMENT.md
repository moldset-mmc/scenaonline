# MBStudio: owner workflow refinement, 18 September 2026

Prepared locally against `main` at
`5aa6f7aa933e38cc40e408cb8478277e1aeb02b4` in `moldset-mmc/scenaonline`.
Publication is pending the owner's review of the full diff and preview.

## Delivery destination

GitHub `main` → the existing Vercel Git integration → `mbstudio.scena.life`.
Vercel project: `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6` (`scenaonline`).
Verified baseline deployment: `dpl_8rSYWZRyLkCyLppdvN9r7PgKmjL8`, READY,
Git source `main`, SHA matching the baseline above.
No manual production deployment or merge of the installation checkpoint.

Proposed commit: `Refine MBStudio owner workflows and shared mobile branding`.

## Changes

1. Visible section name is handwritten Latin `shopping`, including the cabinet.
   URLs, internal keys and search metadata retain their existing values.
2. Shared MB Studio. / SCENA.live identity in public, model, login and cabinet
   headers. Studio. is 15 px (14 px on narrow phones); the live contours in the
   canonical artwork are enlarged 45%. Crown shape, SCENA and dot are preserved.
   Master 1.1 has a fixed width/height ratio of 5.2799280866. Updated brandbook
   1.2 and transparent logo kit are supplied separately. Existing published
   photographs are not regenerated automatically.
3. Published posts have a separate visibility save. Clearing every placement
   hides the post immediately without publishing private draft text.
4. Posts show their persistent number, title, thumbnail when available,
   publication status, actual live destinations and pending draft changes.
5. Delete moves a post to Trash, removing it from feeds and the ordinary list.
   Recovery is available for 30 days and clears all placements; the owner must
   explicitly show it again. Previously published links keep the existing
   archive stub. No physical file purge or automatic purge job is introduced.
6. Work schedule opens on a month calendar: choose several dates, set hours,
   an optional break or a day off. Weekly repetition and individual overrides
   remain available. Existing bookings and availability rules are preserved.
7. Order rows are compact and show saved product names and quantities.
8. Refresh in Telegram is visible directly on the order card.
9. Discuss PRO opens an inline message form for the SCENA platform channel.
   It does not route to Help or fall back to the owner's bot.
10. The Telegram connection page can change the receiving @username and reuse
    the existing bot. Delivery is paused after a username change until the new
    account proves ownership with the connection code. Old action tokens are
    rotated after successful reconnection.

The scheduling interaction follows the date → hours → break → save workflow
documented in [Altegio's official mobile guide](https://alteg.io/en/support/knowledge-base/4906230240157/).
It is adapted to this single-owner application; it does not add team management
or shift-cycle generation such as 2-on/2-off.

## Verification

- Native asset build and complete native HTTP acceptance: RU/RO/EN public and
  cabinet routes, authenticated forms across replicas, booking, visibility,
  Trash, calendar, orders and Telegram mocks.
- Homepage HTTP acceptance: 17 requests, editable owner content, navigation,
  exact booking destination, local fonts and logos.
- Existing SEO HTTP regression: 86 requests; metadata, localized discovery,
  redirects/private routes and cache policy. This is a regression check, not
  a renewed SEO audit or evidence of actual indexing.
- Domain tests: publications, image framing, owner changes, schedule,
  Telegram connection and licensing.
- Native DOM tests: product modal, contact selection and scoped form saves.
- Signed PRO fixture: one-day renewal preserves remaining time; replay adds
  no days. All keys, subscriptions, messages and orders used by tests are local
  fixtures, with no change to production records.

## Not verified / not configured by this change

- Browser access to local/file previews was blocked. The supplied review image
  is a static layout illustration with demonstration data, not an application
  screenshot. Actual 320/360/390/430 px, tablet, desktop, keyboard and overflow
  checks remain unverified.
- No issuer public key exists in the repository at
  `config/pro-issuer-public.pem`. This change does not invent a new production
  issuer identity. A real renewal code has not been redeemed on the live site.
- SCENA's real Telegram channel and bot have not been supplied or verified.
  Configure `SCENA_PLATFORM_TELEGRAM_BOT_TOKEN` and
  `SCENA_PLATFORM_TELEGRAM_CHAT_ID` before real sending. The UI reports an
  unconfigured channel honestly. No real Telegram message was sent by tests.
- Legacy Streamlit UI tests require Streamlit, absent from the native web
  environment; native HTTP/DOM tests cover this application's current runtime.
- The additional storefront remark remains unspecified; its original
  screenshot was returned to the owner. No speculative storefront redesign.

## Non-actions and recovery

No domain/DNS changes, search registration, new SEO audit, changes to public
URLs/redirects/H1/canonical/hreflang/robots/sitemap/analytics, pricing changes,
production content replacement, production credentials, subscription extension,
physical deletion, external messages or broader SCENA repository changes.

No destructive database migration. Existing snapshots gain additional status
values `hidden` and `trashed`. Roll back code to the baseline commit/deployment
while retaining all data; publication visibility is also written to the legacy
`posts.active`/placement flags so hidden content stays absent from feeds.
The older cabinet does not provide the new Trash/visibility controls and may
label these states imprecisely; prefer a forward fix for that interface.

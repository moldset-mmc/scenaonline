# Multilingual search delivery

Current domain: **https://mbstudio.scena.life**. The September 16 correction, clean URLs, empty-section indexing policy, Yandex setup and validation are documented in [docs/MBSTUDIO-SEO.md](docs/MBSTUDIO-SEO.md). The earlier baseline below is historical.

Baseline: d6a1b48ecad9deb99446100999a82a441f5ff5ce. Prepared September 15, 2026; publication requires the reviewed artifact approval.

The native HTML renderer previously emitted one Russian title with no canonical, description, hreflang or structured data. Search flags did not reach HTTP. Model content was embedded in an iframe. Cabinet language links lost record/photo context, and several controls/auth pages were Russian-only. Public crawling also reproduced libSQL idle transaction expiry while storing temporary forms or public page cache snapshots.

This change introduces scena_seo.py, a public-data-only metadata/discovery layer, and an owner search settings view. Only published records and explicit public media are projected. Hidden/missing routes return404; disabled indexing preserves200+noindex. Public canonical origins are configured HTTPS URLs, never visitor Host input. Alternate languages are reciprocal; untranslated articles are not advertised as translated pages. No fake dates, address, coordinates or reviews are generated. robots/sitemap/optional llms are dynamic. Verification values are validated, stored and emitted on the public home page; they do not register an external property or prove indexing.

Model is now the actual HTML document in native mode; the existing visual content, slider and QR remain. Native internal navigation stays in the same tab. Visible Professional content includes the existing city, contacts and service descriptions. The cabinet retains language and record context through login/logout and detailed views. No owner translations, photos, real orders or notifications are changed by code publication; the separately reviewed six-field translation proposal is an owner-editor operation.

Temporary form snapshots use a single autocommit INSERT with explicit close. Cache writes retain the atomic revision guard and use separate autocommit cleanup. Remote driver kwargs are forwarded. Domain transactions, one-use consume and duplicate-action guards are unchanged. Cache errors return a freshly rendered response with BYPASS; no domain mutation is retried. Host-specific cache keys prevent preview noindex leakage.

Validation: 333 unittest cases (3 optional skips); native acceptance through two instances; 123 language screens/369 links; 86 SEO HTTP requests/42 catalog URLs; QR save/cache checks; five injected idle-expiry tests. Production latency, physical Samsung behavior, Search Console URL Inspection and consumer AI citation remain to be verified after approved publication/access. No proxying of previously denied local browser preview URLs was attempted.

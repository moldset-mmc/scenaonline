# SCENA platform indexing separation — proposed release

Status: local review candidate; no push, deployment, alias, DNS, database or Search Console changes.

## Evidence baseline

- Live project: `scenaonline`, `prj_1uMoeCzIfiqptGDmFYYIteSpwqc6`.
- Both `scena.life` and `mbstudio.scena.life` alias production deployment `dpl_GnjhyR7Mr326YunpcCiJrfqvDt9f`.
- Source: `moldset-mmc/scenaonline`, `main`, `3e83aa7a3d44621517db88a5e02f6fe644777712`.
- Created 2026-09-23 13:30:31.567 UTC.
- The live `/newcard` HTML is byte-identical to the baseline file (SHA256 `1d6a665e0771c9bc72f00ad6fab1150dfad5d04f49d3562b3d9f483b4c1cbcc6`).
- Root, language roots, robots and sitemap redirect to MB Studio; `/newcard` has HTML and HTTP noindex.

## Scope

Two distinct public websites in the existing deployment. No infrastructure migration and no changes to MB Studio's configured public origin or database. This restores the platform on its own host without replacing the salon renderer.

The platform page is the existing SCENA QR v1 review artifact, SHA256 `ffde651f189c785475e68b207683130a9e16b1b58e80485fd73567cabbc400dc`. Preserve the immutable artifact, including bundled license notices. `platform.py` fails closed if the artifact hash or unique integration points change. A later frontend release should replace this pinned artifact through a reviewed build, not arbitrary edits to its minified JavaScript.

| Host/path | Proposed behavior |
|---|---|
| scena.life/ | 200, Romanian platform, self canonical, index/follow |
| scena.life/ru/ | 200, Russian platform, self canonical, reciprocal RO/RU hreflang |
| scena.life/ro/ | 308 to / on the same host |
| scena.life/?lang=ro or ru | 308 to the corresponding platform URL, retaining other query values |
| scena.life/newcard | Existing public intake page; index/follow only on scena.life; existing canonical retained |
| scena.life/newcard/ | Existing 308 to /newcard |
| scena.life/en/ and unpublished localized /newcard routes | 404/noindex; no fake translation and no MB Studio fallback |
| scena.life/robots.txt | Platform robots, own sitemap; private/API routes disallowed |
| scena.life/sitemap.xml | /, /ru/, /newcard only; same-language canonical URLs |
| scena.life/llms.txt | Platform directory |
| mbstudio.scena.life/* | Existing MB Studio handlers and search metadata |
| Legacy explicit salon deep links, e.g. scena.life/ru/makiyazh/ | Existing migration redirects retained |
| POST /, webhook, intake API, health, private media | Existing handlers retained |
| Noncanonical preview hosts /newcard | noindex retained; forwarded Host cannot enable indexing |

The historical MB Studio migration and PUBLIC_ORIGIN remain for actual legacy salon URLs. Removing or globally replacing PUBLIC_ORIGIN would break existing salon links and is not this change.

## Validation

Run from the repository with its Python dependencies:

```bash
SCENA_NATIVE_WEB=1 python3 -m unittest tests.test_platform_isolation tests.test_newcard tests.test_mbstudio_seo tests.test_seo -v
```

Result in the audit environment: 31 tests PASS. Tests cover host routing, status/canonical/hreflang/sitemap alignment, noindex isolation, HEAD, retained POST/private handlers and existing MB Studio SEO rules. Two jsdom startup checks (18 assertions) verify RO/RU render, head metadata and absence of unexpected writes. They do not replace visual browser acceptance or end-to-end lead delivery.

## Approval and release

1. Review this exact candidate and the RO/RU HTML previews. Approval is required before any external push or deployment; a push to the current production branch can trigger an automatic deployment.
2. Re-read live alias targets and main SHA immediately before release. Stop and rebase/retest if either differs from the baseline. Recheck project environment names without printing values; no new credentials are required by this patch.
3. Build an isolated preview of the exact candidate; test with the intended Host routing and verify the actual rendered pages. Keep non-production pages noindexed. Do not promote the old static QR preview wholesale: it lacks the existing application backend and host separation.
4. Only after the user approves publication, deploy the approved candidate. Keep MB Studio's domain assignment, database, media, canonical origin and operational configuration unchanged. Verify GET/HEAD root, RU, RO normalization, newcard, robots, sitemap, MB Studio pages and non-mutating API availability. Sending real test submissions requires explicit authorization.
5. Re-read the production alias and deployment source SHA. If acceptance fails, restore the previously recorded deployment; this intentionally restores the old root redirect while the issue is corrected offline. Do not roll back the database.

Search Console changes are a separate approval scope. After access is available, export the actual alternate-canonical examples and inspect the relevant canonical pairs. Read Google-selected canonical, user canonical, last crawl and indexing status. Do not classify this email as a redirect/noindex incident without the URL evidence. Submit the platform sitemap/request recrawl only after a successful approved release and authorization for search actions. Leave MB Studio sitemap, DNS verification and intentional alternate/private exclusions intact.

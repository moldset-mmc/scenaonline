# MBStudio search release — 16 September 2026

## Approved target and scope

The owner explicitly corrected the intended pilot origin to **https://mbstudio.scena.life** and requested deployment plus the complete SEO checklist. This supersedes the earlier handoff that deferred the subdomain. The existing `moldset-mmc/scenaonline` repository, Vercel project and persistent data remain in use.

- Public canonical origin: `https://mbstudio.scena.life`.
- `scena.life` and `scenaonline.vercel.app`: permanent redirects for public GET/HEAD. Old Telegram webhook POST, health and private media handlers remain available.
- Search Console domain property: `sc-domain:scena.life`; retain its DNS verification. Submit the new subdomain sitemap.
- Yandex Webmaster: exact HTTPS subdomain; verification token in home metadata.
- Metrika counter: `112712591`, account `moldset@gmail.com`, restricted to `mbstudio.scena.life`, currency MDL. Interface time zone: Athens/Bucharest (same seasonal clock as Chișinău). Webvisor/form replay disabled.

## URL contract

| Page | RU | RO | EN |
|---|---|---|---|
| Personal page | `/ru/` | `/ro/` | `/en/` |
| Makeup | `/ru/makiyazh/` | `/ro/machiaj/` | `/en/makeup/` |
| Model | `/ru/model/` | `/ro/model/` | `/en/model/` |
| Booking | `/ru/zapis/` | `/ro/programare/` | `/en/booking/` |
| Shop | `/ru/market/` | `/ro/market/` | `/en/market/` |
| Course | `/ru/kurs/3/` | `/ro/curs/3/` | `/en/course/3/` |
| Makeup portfolio | `/ru/portfolio/professional/` | `/ro/portofoliu/professional/` | `/en/portfolio/professional/` |
| Model portfolio | `/ru/portfolio/model/` | `/ro/portofoliu/model/` | `/en/portfolio/model/` |

Other route mappings are deterministic in `scena_urls.py`. Query-based links remain supported. Course and post IDs remain stable. Extra functional/tracking query parameters survive redirects. Canonicals strip tracking and private state. Booking service selection remains a variant of the main booking page.

## Content and search

- One H1 on each public route, including empty sections. Portfolio and publication headings distinguish their purposes. Model introduction and gallery no longer provide two H1 tags.
- Distinct descriptions for portfolio/publication roles; localized title, description, canonical, hreflang, Open Graph, Twitter and JSON-LD.
- Schema graph: WebSite, Person, WebPage/ProfilePage/CollectionPage, BreadcrumbList and real published Services. City comes from the owner's published location. No invented street address, coordinates, awards, reviews or credentials.
- Original service descriptions for daytime/evening/bridal makeup and the Selfie Makeup course. Replace only matching placeholder descriptions; preserve custom owner copy. Do not invent a curriculum, dates, brands, included products or delivery terms.
- Visible route-specific guidance for booking, services, the course, shop and model enquiry forms. Existing personal/model copy and images are retained.
- Empty portfolio/publication listings remain accessible but receive noindex and are omitted from the sitemap. Publishing content restores eligibility automatically, subject to the owner's existing indexing switches.
- No WordPress demo pages were found. No owner content is deleted. Yoast is not applicable to the custom Python application.
- `robots.txt`, XML sitemap and the optional `llms.txt` directory use the canonical origin and current published catalog.

## Semantic core

`MBSTUDIO-keywords.csv` maps RU/RO/EN intent clusters to specific pages. Sources checked on 16 September 2026:

- https://visage.md/ — local service vocabulary: daytime, evening, bridal and personal makeup training.
- https://beautyavenue.md/make-up/ — Romanian service names and automachiaj terminology.
- https://baco.md/cursuri/auto-machiaj/ — Romanian self-makeup training terminology.
- Existing MBStudio public catalog — actual services and product categories.

Queries are research-informed editorial targets, not measured monthly volumes. No Wordstat/Keyword Planner frequency data was supplied. No competitor body copy is reused. Do not create empty city landing pages or promise services absent from the owner's catalog.

## Measurement

Only canonical public indexable GET pages initialize Metrika. Cabinet, preview hosts, POST responses and private query variants omit the script. Pageview URLs are canonical; referrer queries are removed. Session replay, clickmap, form analysis, automatic external-link collection, ecommerce and Tag Manager are disabled in initialization. No customer contact values are passed to goal events.

Goals: `booking_open`, `booking_request`, `shop_order`, `course_request`, `contact_click`. Successful submission markers originate from server-confirmed receipts. Re-rendering does not repeat the same goal within that document. Browser back/reload starts a fresh document; conversions require a fresh server result.

## Release gate and rollback

- Migration is production-only, compares the approved previous origins, and writes an atomic `app_meta` receipt at `seo_origin_migration:mbstudio.scena.life:v1`.
- Receipt contains prior changed settings and placeholder text. Existing indexing flags, photos, service prices, schedule, leads, bot credentials and accounts are not modified.
- Later owner edits are not overwritten by subsequent application starts.
- Isolated unit tests cover migration rollback and URL boundaries. Two-server HTTP acceptance checks all new public routes, old-host redirects, H1, language links, canonical/sitemap agreement, private analytics policy and form POST.
- Before any rollback, read the receipt and current values. Revert only unchanged values written by this release, then restore the matching code. Do not restore an entire live database over subsequent owner edits.

## Limits of completion

A working sitemap and verified ownership do not prove indexing. Search ranking, external plagiarism comparison and consumer ChatGPT/Claude/Perplexity mentions remain unmeasured. Empty sections need real owner publications/photos before entering search. Course curriculum details need owner facts; no fictitious programme is published.

Official references: https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes ; https://developers.google.com/search/docs/appearance/title-link ; https://yandex.ru/support/metrica/ru/code/counter-initialize ; https://yandex.ru/support/metrica/ru/objects/reachgoal .

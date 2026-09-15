# SCENA performance and individual schedule — 15 September 2026

Base production: `dbbef60c744a4b06d0f182c79f7ccc8510778589`.
Stable public address: https://scenaonline.vercel.app .

## Delivered behavior

- Availability is loaded with one connection and five SELECTs for a whole date range. The booking UI loads its supported horizon once and reuses it for the month, selected day and nearest-date suggestion. No cross-request availability cache. The final booking still checks the slot in its existing write transaction.
- Booking AJAX actions render and send only the booking region. Other form responses patch changed DOM nodes, preserving unchanged images/iframes. Full HTML remains the non-JavaScript fallback.
- Noninteractive, anonymous public HTML is retained in shared SQL storage for at most five minutes. Content-table triggers invalidate it within the edit transaction, across instances. A revision guard rejects stale concurrent renders. Deployment and language partition cache keys. Forms, authenticated requests, private content and errors are excluded. HTML CDN caching was removed to avoid a second, independently stale layer; hashed assets remain immutable.
- Editors list saved media references without downloading originals. They materialize only originals needed for the selected photo, publication or export. Backup/restore deliberately hydrate the entire library. Integrity checks and private storage remain in place.
- Work → Schedule → Hours for an individual day supports recurring weekday hours and an override for one calendar date. Both support an optional break, a day off and reset. Weekday changes update only the selected weekday; date changes replace only that date's exceptions atomically. Existing appointments are retained. Priority: date override, individual weekday, general schedule. Existing data is not converted or reset.

## Evidence and boundaries

| Measurement | Before | After | Conditions |
| --- | --- | --- | --- |
| Calendar database connections | 16 | 1 | Same 16 remaining September days, isolated SQLite trace |
| Calendar SELECTs | 80 | 5 | Published baseline code vs range loader; not a production SQL trace |
| Booking response body | 56,930 bytes | 21,827 bytes | Same service and fixture; complete HTML vs JSON booking region |
| Entire app calls during booking AJAX | 1 or more | 0 | HTTP test forbids `scena_app.run`; action succeeds |
| Media downloads while listing saved originals | Entire cache hydrated on editor entry | 0 | Mock private provider, two manifest entries |
| Downloads for one selected uncached original | Entire cache hydrated | 1 | Other original remains unmaterialized |

Before-deployment browser day transitions on production: 1,927 / 1,726 / 4,049 ms, timed around click plus visible-heading wait. These include automation overhead and are not server timings. Existing site data was being edited by the owner during this session, so timing comparisons are indicative, not controlled lab results.

Validation: 252 existing/new unit tests passed (3 skipped), plus the additional lazy-media test. Standalone native HTTP acceptance covers 11 public routes, 18 cabinet views, individual weekday/date save/reset, cache invalidation across instances, booking fragment, complete booking, profile save, duplicate rejection, image chunks over 3 MB and private backup/download. It also runs with the libSQL driver against a local fixture. Provider/network delays and Vercel cold starts are not eliminated; no always-on plan or provider migration is included.

## Using individual hours

Open Cabinet → Work → Schedule. Under “Часы для отдельного дня”, choose “День недели” for a recurring change, or “Конкретную дату” for a single day. Set “Работа с / Работа до”, optionally enable “Есть перерыв”, then press “Сохранить только этот день”. “Вернуть общий график для этого дня” removes that override. General schedule edits preserve individual overrides.

## Rollback

Revert this code commit and redeploy the previous code if needed; retain provider data. New runtime cache tables/triggers are excluded from portable backups. Full rollback of the weekday feature should first remove weekday overrides through the new UI, because older code does not interpret `schedule_day_hours`. Single-date overrides use the existing closed-plus-extra schema and remain understood by older releases.

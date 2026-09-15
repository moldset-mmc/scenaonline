# SCENA — verified release checkpoint, 15 September 2026

Production code: `6266b53ab38989b5e783ee53b4b155189eb6ee22`
Production tree: `23986ab586765163606a95fd98b6a84a4fae6f80`
Vercel deployment: `dpl_Cgggj7VU2BunyP2P3Yf7dyhG7u4u`, READY.
Stable site: https://scenaonline.vercel.app
Schedule: https://scenaonline.vercel.app/?page=admin&lang=ru&section=work&view=schedule

This checkpoint branch contains the production code plus this report and a deployment-disable rule. It does not publish another site.

## Verified live
- Day selection: browser-local updates 3 / 2 / 1 ms, no network request. The same click-and-visible-heading automation used before deployment took 293 / 267 / 276 ms vs 1,927 / 1,726 / 4,049 ms before. These outer timings include browser automation overhead.
- Month selection: 2 ms locally; time selection: below 1 ms at timer rounding, no network request.
- After choosing 19 September, 09:00, Continue displayed the correct service, date, time and contact form. No production customer record was created by verification.
- Public scene: first measured content-ready 2,456 ms (render 266.6 ms); repeat 470 ms, with navigation Server-Timing `page-cache;dur=121.8`. This compares cache miss with cache hit, not two equal cache conditions. Asset/browser caches were warm; no mobile-device benchmark was taken.
- Health HTTP 200, matching production commit, database/public Blob/private Blob verified for this deployment, private access blocked without token. Latest process startup 0.199 s.
- No deployment error logs returned for the ten-minute verification interval.
- Cabinet URL redirects unauthenticated browser to login while retaining the schedule destination. The owner UI's weekday/date saving and reset were verified using authenticated isolated HTTP fixtures, not by changing the owner's live schedule.

## Test evidence
253 unit tests passed, 3 skipped. Native HTTP fixtures verified all public/cabinet routes, weekday/date changes and reset, adjacent-day preservation, shared HTML cache invalidation, local-choice validation, stale-slot rejection, complete booking, profile save and large image upload. Portable backup/private download also passed earlier in this pass with SQLite and local libSQL. The last focused run reached booking success; its output did not include a final backup completion marker.

## Scope and operations
See PERFORMANCE-2026-09-15.md for architecture, priority rules and rollback. No owner content reset, password change, provider migration, new paid service or address change. User edits observed during testing (service names and general schedule) remain in the production database. Vercel cold starts and network delay still affect first opening and server-backed actions.

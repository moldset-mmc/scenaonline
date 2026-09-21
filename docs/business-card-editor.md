# Independent MBStudio business card

Owner route: `/?page=admin&section=pages&view=card&lang=ru` (also RO/EN).
Public address: `https://mbstudio.scena.life/card/`.

The card has its own `business_card_settings` table. Initial values reproduce the approved card. `init_db` seeds missing fields only. Editing the main profile cannot change this record, and card saves never write main-profile fields.

The editor covers name, profession, tagline, its own photo, primary button, website/social links and optional phone/email. Preview does not publish. Save immediately changes the public HTML, downloadable vCard and selected portrait. The card URL, QR and NFC URL stay fixed. Previously imported phone contacts are separate copies.

The existing owner session, form token, origin checks and uploads protect the editor. Saving compares the complete original snapshot to current data in one transaction. A stale tab is rejected. Images retain a private original and publish a metadata-free rendition through the existing media adapter. The photo catalog marks the selected card photo as in use.

Public HTML and vCard are rendered from saved data on each request, with no browser HTTP cache. The scoped service worker uses the network first and maintains an offline copy; an offline notice makes that state visible. The public portrait is served from the card origin so its offline cache can update after a photo change. No cabinet route is cached.

Validation performed against isolated local databases:

```sh
SCENA_NATIVE_WEB=1 python -m unittest tests.test_business_card tests.test_business_card_settings tests.test_scena_life_redirect -q
python tests/business_card_http.py
node --test tests/js/business_card_cache.test.cjs
node --check public/card/app.js
node --check public/card/sw.js
```

The HTTP scenario exercises the native cabinet form on two application instances, preview without writes, persistence across fresh requests, anonymous and cross-origin rejection, stale edits, recovery after validation errors, photo preview/upload and public download. Storage failures leave current data unchanged. Rendering and vCard escaping/folding are checked separately.

Not verified in this environment: visual browser inspection of the local editor (the browser blocked localhost), actual Android/iPhone installation, NFC hardware, phone address-book import, production Turso/Blob persistence for this new feature. Production has not been changed by this patch. Publication remains a separate final step.

# SCENA.LIVE questionnaire / Telegram

Public entry: https://scena.life/newcard. Bot: `@scenalive_bot`.

The questionnaire uses **its own Turso database and private Vercel Blob store**.
It never falls back to the salon database, salon media store, salon bot or salon recipient.

## Production configuration

Create a separate Turso database `scena-intake`, and connect it to `scenaonline`
with prefix `SCENA_INTAKE`. This creates:

- `SCENA_INTAKE_TURSO_DATABASE_URL`
- `SCENA_INTAKE_TURSO_AUTH_TOKEN`

Create a **private** Blob store `scena-intake-private`, prefix `SCENA_INTAKE_BLOB`,
including a read/write token. Required variable:

- `SCENA_INTAKE_BLOB_READ_WRITE_TOKEN`

In Vercel → scenaonline → Settings → Environment Variables, add these for **Production only**:

- `SCENA_INTAKE_TELEGRAM_BOT_TOKEN`: token for `@scenalive_bot`, entered directly by the owner.
- `SCENA_INTAKE_TELEGRAM_CHAT_ID`: owner's positive numeric **personal** Telegram chat ID.
- `SCENA_INTAKE_ENABLED=1`: enable only after the owner has started the bot and confirmed the recipient.

Do not put tokens in chat, source control, screenshots, browser URLs or frontend variables.
No credentials are needed in the React bundle. No webhook is installed or changed.
Redeploy the current commit after environment changes.

`GET /api/intake/status` is ready only when all variables exist, the bot's `getMe`
username is `scenalive_bot`, and `getChat` confirms the configured personal chat.
This check does not send a message. It caches the result for 60 seconds per instance.
Readiness is not proof of database/blob availability or actual message delivery.

## One-click submission

The visitor clicks once. The browser starts a JSON submission, uploads photographs
one at a time (raw body, maximum 4 MiB each), then finalizes. Six photos therefore do
not exceed Vercel's 4.5 MB request limit. Answers and photos must be durable before
Telegram is called. All mutations require `Origin: https://scena.life`.

- `POST /api/intake/start`: strict answers, consent, UUID, empty honeypot and photo manifest.
- `PUT /api/intake/:id/photos/:index`: capability-protected upload; hash, MIME, dimensions
  and image parser validation, up to 6 non-animated JPG/PNG/WebP images.
- `POST /api/intake/:id/send`: atomic delivery claim. Duplicate retries never send twice.
- `GET /api/intake/:id/gallery` and `/photos/:index`: separate gallery capability,
  no public object URL, no cache, 30-day expiration.

The gallery key is in the URL fragment, not server request URLs. Gallery requests
carry it in `Authorization`. Anyone with the complete gallery link can view it;
it is not tied to a Telegram login. The owner should not forward it to others.
Tokens are HMAC-derived from the dedicated private-store credential. Rotating that
credential invalidates previous upload and gallery links.

## Delivery failures and storage limits

`sent` requires Telegram `ok: true`, a numeric `message_id`, and the exact configured
chat ID. `failed`, `uncertain` and `sending` are retained for owner review. The UI says
“saved” when delivery is not confirmed. No automatic Telegram retry is made after
an ambiguous timeout, to avoid duplicate messages. A process interruption after the
atomic claim may leave `sending`; check the Telegram chat before any manual retry.

Operations review query (run only against **scena-intake**):

```sql
SELECT id, created, state, message_id FROM intake
WHERE state IN ('failed', 'uncertain', 'sending') ORDER BY created DESC;
```

Answers remain in `intake.answers`, photo manifests in `intake.manifest`, private
object locations in `intake_photos.location`. No owner inbox/automatic retry worker
is included in this first version. These rows need manual monitoring during launch.

To bound initial resource use, new submissions are limited to 4 per IP per hour,
2,000 reserved submissions and 256 MiB of reserved photo bytes in total. This is an
application guard, **not a statement of Vercel's included quota or a billing cap**.
Abandoned uploads reserve space too. Origin validation is not an anti-bot service.

Links expire after 30 days. **Stored answers and files are not automatically deleted**.
Before opening intake broadly, agree a retention policy. To remove an intake, delete
its private Blob objects first, then its `intake_photos` and `intake` rows; include
orphan files under the intake UUID from interrupted uploads. Do not delete live
uploads while a submission is being finalized.

## Verification and release

```sh
python -m unittest tests.test_intake tests.test_newcard -q
cd newcard-ui
npm run typecheck
npm run build
```

The built bundle in `public/newcard/assets` is committed. `gallery.html` and
`gallery.js` are independent static files and survive rebuilds.

Before declaring delivery connected, submit an explicitly labelled test questionnaire
with a small synthetic image, confirm the response `stored=true, delivered=true`,
check the recorded Telegram `message_id`, and open its private photo link. Verify
that the same submission retry does not create a second message. A passing local
test with fake Telegram and fake storage does not prove live delivery.

Rollback: remove `SCENA_INTAKE_ENABLED` or set it to `0`, then redeploy. Existing
private photo links remain readable until expiration while the database/blob
credentials are present. Rolling back the code does not delete submissions.

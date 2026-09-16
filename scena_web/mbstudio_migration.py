"""Owner-requested MBStudio origin correction with one atomic rollback receipt."""
from contextlib import closing
import json

ORIGIN = 'https://mbstudio.scena.life'
KEY = 'seo_origin_migration:mbstudio.scena.life:v1'
ALLOWED = ('https://scena.life', 'https://scena.life/',
           'https://scenaonline.vercel.app', 'https://scenaonline.vercel.app/', ORIGIN, ORIGIN + '/')


def migrate(database, environment, *, connector=None):
    if environment.get('VERCEL') != '1' or environment.get('VERCEL_ENV') != 'production':
        return 'skipped_environment'
    if connector is None:
        from scena_database import connect
        connector = connect
    with closing(connector(database, isolation_level=None)) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT 1 FROM app_meta WHERE key=?', (KEY,)).fetchone():
                db.commit()
                return 'already_recorded'
            current = dict(db.execute('SELECT key,value FROM profile_settings'))
            if current.get('public_base_url') not in ALLOWED:
                db.rollback()
                return 'skipped_unexpected_origin'
            values = {'public_base_url': ORIGIN, 'seo_pretty_urls': '1',
                      'seo_empty_sections_noindex': '1',
                      'seo_content_v1': '1',
                      'seo_yandex_counter': '112712591',
                      'seo_yandex_verification': '5b068d63b7164de0'}
            previous = {key: current.get(key) for key in values}
            for key, value in values.items():
                db.execute('INSERT INTO profile_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
            from scena_search_content import SERVICE_COPY
            services = []
            # Only replace confirmed placeholder descriptions, never custom copy.
            for row in db.execute('SELECT id,name,name_ro,name_en,description_ru,description_ro,description_en FROM services'):
                identifier, name, ro, en, *descriptions = row
                if name not in SERVICE_COPY:
                    continue
                placeholders = {'', name, ro, en, 'Невеста',
                    'Предварительная запись без автоматического подтверждения места.',
                    'Preînscriere fără confirmarea automată a locului.',
                    'Preregistration without automatic place confirmation.'}
                changes = {}
                for field, old, text in zip(('description_ru', 'description_ro', 'description_en'), descriptions, SERVICE_COPY[name]):
                    if old in placeholders:
                        db.execute(f'UPDATE services SET {field}=? WHERE id=?', (text, identifier))
                        changes[field] = {'previous': old, 'applied': text}
                if changes:
                    services.append({'id': identifier, 'fields': changes})
            db.execute('INSERT INTO app_meta(key,value) VALUES (?,?)',
                       (KEY, json.dumps({'previous': previous, 'applied': values, 'services': services}, sort_keys=True)))
            db.commit()
            return 'migrated'
        except Exception:
            db.rollback()
            raise

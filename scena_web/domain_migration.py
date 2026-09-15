"""Approved, one-time production origin migration. Never runs on preview data."""
from __future__ import annotations

from contextlib import closing
import json
from collections.abc import Mapping

OLD_ORIGINS = ("https://scenaonline.vercel.app", "https://scenaonline.vercel.app/")
NEW_ORIGIN = "https://scena.life"
MIGRATION_KEY = "seo_origin_migration:scena.life:v1"


def migrate_public_origin(database, environment: Mapping[str, str], *, connector=None):
    """Compare-and-set only the approved origin; keep a durable rollback receipt.

    The marker and setting change share a short transaction. Existing settings
    triggers invalidate rendered page caches in that same transaction. A later
    owner edit is never reverted when another replica starts. Tests may inject
    a SQLite connector; production uses the application's existing DB adapter.
    """
    if environment.get("VERCEL") != "1" or environment.get("VERCEL_ENV") != "production":
        return "skipped_environment"
    if connector is None:
        from scena_database import connect
        connector = connect
    with closing(connector(database, isolation_level=None)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if connection.execute("SELECT 1 FROM app_meta WHERE key=?", (MIGRATION_KEY,)).fetchone():
                connection.commit()
                return "already_recorded"
            row = connection.execute(
                "SELECT value FROM profile_settings WHERE key='public_base_url'"
            ).fetchone()
            previous = row[0] if row else None
            if previous not in OLD_ORIGINS and previous != NEW_ORIGIN:
                connection.rollback()
                return "skipped_unexpected_origin"
            changed = previous in OLD_ORIGINS
            if changed:
                connection.execute(
                    "UPDATE profile_settings SET value=? WHERE key='public_base_url' AND value=?",
                    (NEW_ORIGIN, previous),
                )
            receipt = json.dumps({"from": previous, "to": NEW_ORIGIN, "changed": changed}, sort_keys=True)
            connection.execute("INSERT INTO app_meta(key,value) VALUES (?,?)", (MIGRATION_KEY, receipt))
            connection.commit()
            return "migrated" if changed else "already_current"
        except Exception:
            connection.rollback()
            raise

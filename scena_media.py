"""Durable originals in private Blob, approved renditions in public Blob.

The local media directory is only a cache. A SQL reference is saved only after
the upload succeeds. The manifest travels with portable private backups.
"""
from __future__ import annotations

import hashlib
import io
import mimetypes
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
import time

from scena_database import cloud_database, connect

_lock = threading.RLock()
_last_refresh = {}


def _database():
    return os.environ['SCENA_DB_PATH']


def initialize():
    if not cloud_database():
        return
    connection = connect(_database())
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS scena_media_files (
            path TEXT PRIMARY KEY, private_url TEXT NOT NULL,
            sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
            public_url TEXT NOT NULL DEFAULT '')''')
        connection.commit()
    finally:
        connection.close()


def _relative(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root / 'media') or path.is_symlink():
        raise ValueError('Файл должен находиться в медиатеке SCENA.')
    return path.relative_to(root).as_posix()


def persist(path, app_dir, *, public=False, connection=None):
    if not cloud_database():
        return
    from vercel import blob
    path = Path(path)
    relative = _relative(app_dir, path)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    own = connection is None
    connection = connection or connect(_database())
    try:
        old = connection.execute('SELECT private_url,sha256,public_url FROM scena_media_files WHERE path=?', (relative,)).fetchone()
        if old and old[1] == digest and (not public or old[2]):
            return
        private_url = old[0] if old and old[1] == digest else blob.put(
            'originals/' + digest + '/' + path.name, content,
            access='private', token=os.environ['SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN'],
            content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
            overwrite=True,
        ).url
        public_url = old[2] if old and old[1] == digest else ''
        if public:
            # Publish a normalized image without metadata; retain exact bytes privately.
            from PIL import Image, ImageOps
            with Image.open(io.BytesIO(content)) as original:
                rendition = ImageOps.exif_transpose(original).convert('RGB')
                rendition.thumbnail((1800, 1800))
                output = io.BytesIO()
                rendition.save(output, format='WEBP', quality=90, method=4)
            public_url = blob.put(
                'published/' + digest + '.webp', output.getvalue(), access='public',
                token=os.environ['SCENA_PUBLIC_BLOB_READ_WRITE_TOKEN'],
                content_type='image/webp', overwrite=True,
            ).url
        connection.execute('''INSERT INTO scena_media_files(path,private_url,sha256,bytes,public_url)
            VALUES (?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
            private_url=excluded.private_url,sha256=excluded.sha256,
            bytes=excluded.bytes,public_url=excluded.public_url''',
            (relative, private_url, digest, len(content), public_url))
        if own:
            connection.commit()
    except Exception:
        if own:
            connection.rollback()
        raise OSError('Не удалось сохранить фотографию в облаке. Повторите сохранение.') from None
    finally:
        if own:
            connection.close()


def hydrate(app_dir, *, force=False, paths=None):
    """Fetch selected originals; a full hydration is reserved for backup/restore."""
    if not cloud_database():
        return
    from vercel import blob
    root = Path(app_dir).resolve()
    with _lock:
        cache_key = (str(root), tuple(sorted(str(p) for p in paths)) if paths is not None else None)
        if not force and time.monotonic() - _last_refresh.get(cache_key, 0) < 2:
            return
        connection = connect(_database())
        try:
            if paths is None:
                rows = connection.execute('SELECT path,private_url,sha256,bytes FROM scena_media_files').fetchall()
            else:
                relative_paths = [_relative(root, root / str(path)) for path in paths]
                if not relative_paths:
                    return
                rows = connection.execute('SELECT path,private_url,sha256,bytes FROM scena_media_files WHERE path IN (' + ','.join('?' for _ in relative_paths) + ')', relative_paths).fetchall()
        finally:
            connection.close()
        for relative, url, digest, size in rows:
            if '\\' in relative or '..' in PurePosixPath(relative).parts:
                raise OSError('Некорректный путь облачной фотографии.')
            path = root / relative
            _relative(root, path)
            if path.is_file() and path.stat().st_size == size and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                continue
            result = blob.get(url, access='private', token=os.environ['SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN'], timeout=30, use_cache=False)
            data = result.content
            if result.status_code != 200 or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise OSError('Не удалось проверить сохранённую фотографию.')
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.restore-', dir=path.parent)
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(data)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        _last_refresh[cache_key] = time.monotonic()


def ensure_local(app_dir, value):
    """Materialize just the original requested by an editor or export operation."""
    path = Path(app_dir) / str(value)
    if cloud_database():
        hydrate(app_dir, paths=[value])
    return path


def saved_files(app_dir, folder):
    """List original references without downloading their bytes."""
    root = Path(app_dir).resolve()
    directory = (root / folder).resolve()
    _relative(root, directory / 'placeholder')
    local = {p.relative_to(root).as_posix() for p in directory.glob('*') if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}}
    if cloud_database():
        with connect(_database()) as db:
            rows = db.execute('SELECT path FROM scena_media_files WHERE path LIKE ?', (folder.rstrip('/') + '/%',)).fetchall()
        for (relative,) in rows:
            path = root / relative
            _relative(root, path)
            if path.parent == directory and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
                local.add(relative)
    return sorted(local, reverse=True)


def publish_reference(app_dir, relative, *, connection=None):
    if cloud_database() and str(relative).startswith('media/'):
        path = ensure_local(app_dir, relative)
        persist(path, app_dir, public=True, connection=connection)

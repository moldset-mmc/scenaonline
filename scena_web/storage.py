"""Shared, expiring form state and private temporary binaries.

Every form has a one-use token bound to an HttpOnly browser cookie. It can be
handled by any Vercel instance. No pickle, client-provided schema or local-only
upload/session registry is used.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, time as daytime
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import time

from scena_database import connect, cloud_database

TTL = 12 * 3600


def connection():
    return connect(os.environ['SCENA_DB_PATH'])


def initialize():
    with connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS scena_web_forms (
            token TEXT PRIMARY KEY, browser_id TEXT NOT NULL, payload TEXT NOT NULL,
            expires REAL NOT NULL, consumed INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS scena_web_objects (
            id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, kind TEXT NOT NULL,
            name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
            sha256 TEXT NOT NULL, location TEXT NOT NULL, expires REAL NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS scena_web_forms_expiry ON scena_web_forms(expires)')
        from .page_cache import initialize as initialize_page_cache
        initialize_page_cache(db)


def cipher():
    from cryptography.fernet import Fernet
    secret = os.environ['SCENA_SESSION_SIGNING_KEY'] + '\0' + os.environ['SCENA_ADMIN_PASSWORD']
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


@dataclass
class BinaryRef:
    id: str
    browser_id: str
    name: str
    mime: str
    size: int

    def getvalue(self):
        return read_binary(self.id, self.browser_id)

    def __len__(self):
        return self.size


class Upload:
    def __init__(self, refs, name, mime, size):
        self.refs, self.name, self.type, self.size = refs, name, mime, size
        self._content = None
        self._position = 0

    def getvalue(self):
        if self._content is None:
            self._content = b''.join(ref.getvalue() for ref in self.refs)
            if len(self._content) != self.size:
                raise ValueError('Фотография загружена не полностью. Повторите загрузку.')
        return self._content

    def read(self, size=-1):
        content = self.getvalue()
        end = len(content) if size < 0 else self._position + size
        result = content[self._position:end]
        self._position += len(result)
        return result

    def tell(self):
        return self._position

    def seek(self, offset, whence=0):
        self._position = (0 if whence==0 else self._position if whence==1 else self.size) + offset
        return self._position


def store_binary(data, browser_id, name, mime='application/octet-stream', kind='download'):
    if isinstance(data, BinaryRef):
        if data.browser_id != browser_id:
            raise ValueError('Invalid binary owner')
        return data
    if hasattr(data, 'getvalue'):
        data = data.getvalue()
    if isinstance(data, str):
        data = data.encode()
    data = bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    identifier = hashlib.sha256((browser_id + ':' + kind + ':' + digest).encode()).hexdigest()
    with connection() as db:
        existing = db.execute('SELECT id FROM scena_web_objects WHERE id=? AND expires>?', (identifier, time.time())).fetchone()
        if existing:
            return BinaryRef(identifier, browser_id, name, mime, len(data))
    if cloud_database():
        from vercel import blob
        location = blob.put('web-temporary/' + browser_id + '/' + identifier, data, access='private',
            token=os.environ['SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN'], content_type=mime, overwrite=True).url
    else:
        folder = Path(os.environ['SCENA_DB_PATH']).parent / 'web-temporary'
        folder.mkdir(exist_ok=True)
        target = folder / identifier
        target.write_bytes(data)
        location = str(target)
    with connection() as db:
        db.execute('''INSERT INTO scena_web_objects(id,browser_id,kind,name,mime,size,sha256,location,expires)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET expires=excluded.expires''',
            (identifier, browser_id, kind, name, mime, len(data), digest, location, time.time()+TTL))
    return BinaryRef(identifier, browser_id, name, mime, len(data))


def binary_record(identifier, browser_id):
    with connection() as db:
        row = db.execute('SELECT name,mime,size,sha256,location,kind FROM scena_web_objects WHERE id=? AND browser_id=? AND expires>?',
                         (identifier, browser_id, time.time())).fetchone()
    if not row:
        raise ValueError('Файл больше недоступен. Подготовьте его повторно.')
    return row


def read_binary(identifier, browser_id):
    row = binary_record(identifier, browser_id)
    if cloud_database():
        from vercel import blob
        response = blob.get(row[4], access='private', token=os.environ['SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN'], use_cache=False)
        if response.status_code != 200:
            raise OSError('Не удалось прочитать сохранённый файл.')
        content = response.content
    else:
        content = Path(row[4]).read_bytes()
    if len(content) != row[2] or hashlib.sha256(content).hexdigest() != row[3]:
        raise OSError('Не удалось проверить целостность файла.')
    return content


def pack(value, browser_id):
    if isinstance(value, Upload):
        return {'$type': 'upload', 'name':value.name, 'mime':value.type, 'size':value.size,
                'refs':[pack(ref, browser_id) for ref in value.refs]}
    if isinstance(value, (bytes, bytearray)):
        value = store_binary(value, browser_id, 'SCENA.bin')
    if isinstance(value, BinaryRef):
        return {'$type':'binary', 'id':value.id, 'browser_id':value.browser_id, 'name':value.name, 'mime':value.mime, 'size':value.size}
    if isinstance(value, (datetime, date, daytime)):
        return {'$type':type(value).__name__, 'value':value.isoformat()}
    if isinstance(value, Path):
        return {'$type':'path', 'value':str(value)}
    if isinstance(value, tuple):
        return {'$type':'tuple', 'value':[pack(v,browser_id) for v in value]}
    if isinstance(value, dict):
        return {'$type':'dict', 'value':[[pack(k,browser_id),pack(v,browser_id)] for k,v in value.items()]}
    if isinstance(value, (list, set)):
        return [pack(v,browser_id) for v in value]
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    raise TypeError('Unsupported web state type: '+type(value).__name__)


def unpack(value):
    if isinstance(value,list):
        return [unpack(v) for v in value]
    if not isinstance(value,dict):
        return value
    kind = value['$type']
    if kind=='dict': return {unpack(k):unpack(v) for k,v in value['value']}
    if kind=='tuple': return tuple(unpack(v) for v in value['value'])
    if kind=='path': return Path(value['value'])
    if kind in ('date','datetime','time'):
        return {'date':date,'datetime':datetime,'time':daytime}[kind].fromisoformat(value['value'])
    if kind=='binary': return BinaryRef(**{k:v for k,v in value.items() if k!='$type'})
    if kind=='upload': return Upload([unpack(r) for r in value['refs']],value['name'],value['mime'],value['size'])
    raise ValueError('Unsupported saved state type')


def save_form(browser_id, state, query, widgets):
    token = secrets.token_urlsafe(32)
    body = json.dumps(pack({'state':state, 'query':dict(query), 'widgets':widgets}, browser_id), ensure_ascii=False, separators=(',',':')).encode()
    encrypted = cipher().encrypt(body).decode()
    # A rendered form is one independent insert, not an interactive transaction.
    # Remote libSQL may expire a stream before a separate COMMIT can arrive.
    from contextlib import closing
    with closing(connect(os.environ['SCENA_DB_PATH'], isolation_level=None)) as db:
        db.execute('INSERT INTO scena_web_forms(token,browser_id,payload,expires) VALUES (?,?,?,?)',
                   (token,browser_id,encrypted,time.time()+TTL))
    return token


def load_form(token, browser_id, *, consume=False):
    if len(token)>100 or len(browser_id)>100:
        raise ValueError('Обновите страницу и повторите действие.')
    with connection() as db:
        row = db.execute('SELECT payload FROM scena_web_forms WHERE token=? AND browser_id=? AND expires>? AND consumed=0',
                         (token,browser_id,time.time())).fetchone()
        if not row:
            raise ValueError('Эта форма уже отправлена или устарела. Откройте страницу снова.')
        if consume:
            changed = db.execute('UPDATE scena_web_forms SET consumed=1 WHERE token=? AND browser_id=? AND consumed=0', (token,browser_id))
            if changed.rowcount != 1:
                raise ValueError('Действие уже принято. Обновите страницу.')
    return unpack(json.loads(cipher().decrypt(row[0].encode())))


def download_url(data, name, mime):
    from .context import current
    ctx = current.get()
    if not ctx.private:
        raise ValueError('Downloads require the owner cabinet')
    ref = store_binary(data,ctx.session_id,name,mime)
    return '/scena-download/' + ref.id + '?name=' + __import__('urllib.parse',fromlist=['quote']).quote(name)

"""Images use immutable assets, public Blob, or authorized shared originals."""
from __future__ import annotations

import base64
from functools import lru_cache
import hashlib
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import time

from .context import current

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def assets():
    path=ROOT/'scena_web/asset_manifest.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def manifest():
    ctx=current.get()
    if ctx.manifest is None:
        from scena_database import cloud_database, connect
        ctx.manifest={}
        if cloud_database():
            with connect(os.environ['SCENA_DB_PATH']) as db:
                rows=db.execute('SELECT path,private_url,sha256,bytes,public_url FROM scena_media_files').fetchall()
            ctx.manifest={row[0]:{'private_url':row[1],'sha256':row[2],'bytes':row[3],'public_url':row[4]} for row in rows}
    return ctx.manifest


def sign(value):
    body=base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')
    sig=hmac.new(bytes.fromhex(os.environ['SCENA_SESSION_SIGNING_KEY']),body.encode(),hashlib.sha256).hexdigest()
    return body+'.'+sig


def verify(token):
    body,sig=token.split('.')
    expected=hmac.new(bytes.fromhex(os.environ['SCENA_SESSION_SIGNING_KEY']),body.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig,expected):raise ValueError('Invalid image token')
    value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
    if value['expires']<time.time():raise ValueError('Image link expired')
    return value


def reference(app_dir, value):
    ctx=current.get()
    root=Path(app_dir).resolve()
    path=(root/str(value)).resolve()
    if not path.is_relative_to(root/'media'):
        return None
    relative=path.relative_to(root).as_posix()
    entry=manifest().get(relative)
    if entry:
        if entry['public_url']:
            return entry['public_url']
        # A public renderer may display an approved reference without exposing
        # the private Blob credential, its raw URL, or unrelated originals.
        token=sign({'path':relative,'sha256':entry['sha256'],'private':ctx.private,
                    'expires':int(time.time()//3600)*3600+24*3600})
        return '/scena-media/'+token
    if relative in assets():
        return assets()[relative]
    if path.is_file():
        # Newly staged previews are already authorized cabinet content. Keeping
        # these small previews inline avoids any process-local media registry.
        return image_data(path.read_bytes())
    return None


def image_data(data):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as image:
        image=ImageOps.exif_transpose(image)
        image.thumbnail((1200,1200))
        output=io.BytesIO()
        image.save(output,format='WEBP',quality=84,method=3)
    return 'data:image/webp;base64,'+base64.b64encode(output.getvalue()).decode()


def display_image(image):
    if isinstance(image,str) and image.startswith(('http://','https://','data:','/scena-')):
        return image
    if isinstance(image,(str,Path)):
        path=Path(image).resolve()
        root=Path(os.environ.get('SCENA_APP_DIR',ROOT)).resolve()
        if path.is_relative_to(root/'media'):
            return reference(root,path.relative_to(root)) or ''
        raise ValueError('Image outside the media library')
    if hasattr(image,'getvalue'):
        image=image.getvalue()
    if isinstance(image,(bytes,bytearray)):
        return image_data(bytes(image))
    output=io.BytesIO()
    image.save(output,format='PNG')
    return image_data(output.getvalue())


def media_bytes(descriptor):
    from scena_database import connect
    from vercel import blob
    relative=descriptor['path']
    if not relative.startswith('media/') or '..' in Path(relative).parts:
        raise ValueError('Invalid media path')
    with connect(os.environ['SCENA_DB_PATH']) as db:
        row=db.execute('SELECT private_url,sha256,bytes FROM scena_media_files WHERE path=?',(relative,)).fetchone()
    if not row or row[1]!=descriptor['sha256']:
        raise ValueError('Image changed or unavailable')
    response=blob.get(row[0],access='private',token=os.environ['SCENA_PRIVATE_BLOB_READ_WRITE_TOKEN'],use_cache=False)
    data=response.content
    if response.status_code!=200 or len(data)!=row[2] or hashlib.sha256(data).hexdigest()!=row[1]:
        raise OSError('Image integrity check failed')
    from PIL import Image,ImageOps
    with Image.open(io.BytesIO(data)) as image:
        image=ImageOps.exif_transpose(image)
        image.thumbnail((1600,1600))
        output=io.BytesIO()
        image.save(output,format='WEBP',quality=83,method=4)
    return output.getvalue()

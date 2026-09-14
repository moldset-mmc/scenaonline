"""Build immutable, portable browser assets without a JS framework build."""
from pathlib import Path
import hashlib
import io
import json
import sys

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def build():
    target = ROOT / 'public/scena-assets'
    target.mkdir(parents=True, exist_ok=True)
    manifest = {}
    sys.path.insert(0,str(ROOT))
    from scena_restore import BUNDLED_MEDIA_FILES
    inputs = [ROOT / name for name in BUNDLED_MEDIA_FILES] + list((ROOT / 'scena_web/static').glob('*'))
    for source in inputs:
        if not source.is_file() or source.is_symlink() or source.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.svg','.woff2','.otf','.css','.js'}:
            continue
        content = source.read_bytes()
        extension = source.suffix.lower()
        if extension in {'.png','.jpg','.jpeg','.webp'} and source.name!='favicon.png':
            with Image.open(io.BytesIO(content)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1600,1600))
                buffer=io.BytesIO()
                image.save(buffer, format='WEBP', quality=83, method=4)
                content=buffer.getvalue()
                extension='.webp'
        name = hashlib.sha256(content).hexdigest()[:20] + extension
        (target / name).write_bytes(content)
        manifest[source.relative_to(ROOT).as_posix()]='/scena-assets/'+name
    (ROOT / 'scena_web/asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True))
    print('SCENA native assets:',len(manifest),'files')


if __name__=='__main__':
    build()

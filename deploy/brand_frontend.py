"""Set the first HTML document title at image build time, before JS connects."""
from importlib.util import find_spec
from pathlib import Path


def brand(index):
    original = index.read_text(encoding='utf-8')
    title = '<title>SCENA — Моя Сцена</title>'
    measurement = Path(__file__).with_name('measure.js').read_text(encoding='utf-8')
    if 'scena-performance' not in original:
        original = original.replace('</head>', '<script>' + measurement + '</script></head>')
    if title in original:
        index.write_text(original, encoding='utf-8')
        return
    if original.count('<title>Streamlit</title>') != 1:
        raise RuntimeError('Review the Streamlit initial document after this dependency update.')
    index.write_text(original.replace('<title>Streamlit</title>', title), encoding='utf-8')


if __name__ == '__main__':
    package = find_spec('streamlit')
    brand(Path(package.origin).parent / 'static' / 'index.html')

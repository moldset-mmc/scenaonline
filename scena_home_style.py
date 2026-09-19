"""Self-hosted typefaces shared by the homepage and its publication iframe."""
from pathlib import Path

from model_landing import data_uri_for_file


def scene_brand_markup(*, light=False):
    """One complete, proportional lockup for the public site and cabinet."""
    from html import escape
    wordmark = data_uri_for_file(Path(__file__).resolve().parent / ('scena_web/static/scena-live-ivory.svg' if light else 'scena_web/static/scena-live-ink.svg'))
    return ('<span class="scene-brand-badge"><span class="scene-brand-initials">MB</span>'
            '<span class="scene-brand-studio">Studio.</span></span>'
            '<img class="scene-brand-logo" src="'+escape(wordmark, quote=True)+'" alt="SCENA.live">')


def scene_brand_css():
    return '''
    .scene-home-brand{display:inline-flex!important;align-items:baseline!important;gap:5px;min-height:44px;padding-block:6px;flex-shrink:0;text-decoration:none!important;letter-spacing:normal!important}
    .scene-brand-badge{display:inline-flex;align-items:baseline;gap:2px;flex-shrink:0;padding:0 4px;background:#d9c99f;color:#201b17;border-radius:2px;line-height:20px}
    .scene-brand-initials{font:700 24px/20px Georgia,serif;letter-spacing:0}
    .scene-brand-studio{font:400 15px/20px SceneText,sans-serif;letter-spacing:0}
    .scene-brand-logo{display:block;width:126px;height:auto;align-self:baseline}
    .shopping-word,.scene-shop-link{font:400 1.35em/1.05 SceneSignature,cursive!important;text-transform:none!important;letter-spacing:0!important}
    @media(max-width:380px){.scene-brand-initials{font-size:22px}.scene-brand-studio{font-size:14px}.scene-brand-logo{width:116px}}
    '''


def shopping_labels(markup):
    """Style the section word in visible text, preserving attributes and metadata."""
    from html.parser import HTMLParser
    import re
    class Labels(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.parts, self.skip = [], []
        def handle_starttag(self, tag, attrs):
            self.parts.append(self.get_starttag_text())
            if tag in {'script','style','textarea','option','code','pre'}:
                self.skip.append(tag)
        def handle_endtag(self, tag):
            self.parts.append('</'+tag+'>')
            if self.skip and self.skip[-1] == tag: self.skip.pop()
        def handle_startendtag(self, tag, attrs): self.parts.append(self.get_starttag_text())
        def handle_data(self, data):
            self.parts.append(data if self.skip else re.sub(r'\bshopping\b', '<span class="shopping-word">shopping</span>', data))
        def handle_entityref(self, name): self.parts.append('&'+name+';')
        def handle_charref(self, name): self.parts.append('&#'+name+';')
        def handle_comment(self, data): self.parts.append('<!--'+data+'-->')
    parser = Labels();parser.feed(markup)
    return ''.join(parser.parts)


def scene_font_css() -> str:
    static = Path(__file__).resolve().parent / "scena_web/static"
    faces = (
        ("SceneEditorial", "cormorant-regular", "normal", 500),
        ("SceneEditorial", "cormorant-italic", "italic", 500),
        ("SceneText", "manrope-regular", "normal", 400),
        ("SceneText", "manrope-medium", "normal", 500),
        ("SceneSignature", "marck-script", "normal", 400),
    )
    return "\n".join(
        f'@font-face{{font-family:"{family}";font-style:{style};'
        f'font-weight:{weight};font-display:swap;'
        f'src:url("{data_uri_for_file(static / (filename + ".woff2"))}") format("woff2")}}'
        for family, filename, style, weight in faces
    )

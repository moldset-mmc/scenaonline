"""The approved SCENA.live artwork, placed as one proportional mark."""
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

LOGO_STYLES = {"editorial", "compact"}


@lru_cache(maxsize=1)
def _logo_alpha():
    path = Path(__file__).resolve().parent / "scena_web/static/scena-live-logo.png"
    with Image.open(path) as image:
        return image.getchannel("A").copy()


def apply_publication_mark(canvas, photo_box, style="editorial"):
    """Apply the same master to the fitted photo, never the surrounding mat."""
    if style not in LOGO_STYLES:
        raise ValueError("Unknown logo style")
    x, y, width, height = photo_box
    source = _logo_alpha()
    ratio = source.width / source.height
    fraction = .28 if style == "compact" else .31
    mark_width = max(1, round(min(width*fraction, height*.65*ratio)))
    mark_height = max(1, round(mark_width/ratio))
    mask = source.resize((mark_width, mark_height), Image.Resampling.LANCZOS)
    if style == "compact":
        gap = max(0, min(round(width*.04), height-mark_height))
        left, top = x+round(width*.04), y+height-gap-mark_height
    else:
        left, top = x+(width-mark_width)//2, y+min(round(width*.025), height-mark_height)
    result = canvas.convert("RGBA")
    luminance = ImageStat.Stat(result.crop((left, top, left+mark_width, top+mark_height)).convert("L")).mean[0]
    color = (37, 35, 33) if luminance > 165 else (255, 250, 243)

    def stamp(alpha, rgb, dx=0, dy=0, strength=1):
        layer = Image.new("RGBA", mask.size, (*rgb, 0))
        layer.putalpha(alpha.point(lambda a: round(a*strength)))
        result.alpha_composite(layer, (left+dx, top+dy))

    if style == "compact":
        stamp(mask, color, strength=.94)
    else:
        # Light on the upper edge and a fine lower shadow suggest shallow relief.
        unit = width/400
        stamp(mask.filter(ImageFilter.GaussianBlur(max(.3, unit*.4))),
              (0, 0, 0), dy=max(1, round(unit*.8)), strength=.42)
        stamp(mask, (255, 255, 255), dy=-max(1, round(unit*.45)), strength=.55)
        stops = [(0, .98), (.23, .86), (.47, .52), (.52, .59), (.76, .84), (1, .62)]
        gradient = Image.new("L", (1, mark_height))
        draw = ImageDraw.Draw(gradient)
        for row in range(mark_height):
            position = row/max(1, mark_height-1)
            for (a, va), (b, vb) in zip(stops, stops[1:]):
                if a <= position <= b:
                    value = va+(vb-va)*(position-a)/(b-a)
                    draw.point((0, row), fill=round(255*value*.94))
                    break
        stamp(ImageChops.multiply(mask, gradient.resize(mask.size)), color)
    return result.convert("RGB")

"""Self-hosted typefaces shared by the homepage and its publication iframe."""
from pathlib import Path

from model_landing import data_uri_for_file


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

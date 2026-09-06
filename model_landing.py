"""Immersive public Model landing and QR helpers for SCENA."""

from __future__ import annotations

import base64
import html
import io
import json
import mimetypes
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode, urlparse, urlunparse
from scena_i18n import content_text


SLIDE_COUNT = 5
DEFAULT_BASE_URL = "http://localhost:8501"


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return min(max(result, minimum), maximum)


def normalize_public_base_url(value: object) -> str:
    """Return a safe HTTP(S) application base URL without query or fragment."""

    candidate = str(value or "").strip() or DEFAULT_BASE_URL
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return DEFAULT_BASE_URL
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def public_page_url(
    settings: Mapping[str, str],
    page: str,
    *,
    locale: str | None = None,
    **params: object,
) -> str:
    """Build one absolute, shareable SCENA page URL."""

    allowed_pages = {"scene", "professional", "model", "portfolio", "invite-model", "booking"}
    if page not in allowed_pages:
        raise ValueError("Unsupported public SCENA page.")
    query: dict[str, str] = {"page": page}
    if locale in {"ru", "ro", "en"}:
        query["lang"] = locale
    query.update({key: str(value) for key, value in params.items() if value not in (None, "")})
    return f"{normalize_public_base_url(settings.get('public_base_url'))}/?{urlencode(query)}"


def internal_page_url(
    page: str,
    *,
    locale: str | None = None,
    **params: object,
) -> str:
    """Build a same-application route that follows the active local port."""

    allowed_pages = {"scene", "professional", "model", "portfolio", "invite-model", "booking"}
    if page not in allowed_pages:
        raise ValueError("Unsupported internal SCENA page.")
    query: dict[str, str] = {"page": page}
    if locale in {"ru", "ro", "en"}:
        query["lang"] = locale
    query.update({key: str(value) for key, value in params.items() if value not in (None, "")})
    return f"?{urlencode(query)}"


def qr_png_bytes(value: str) -> bytes:
    from scena_qr import qr_png_bytes as branded_qr
    return branded_qr(value)


def resolve_media_path(app_dir: Path, value: object) -> Path | None:
    """Resolve only files inside the pilot directory."""

    candidate = str(value or "").strip()
    if not candidate or urlparse(candidate).scheme in {"http", "https"}:
        return None
    path = (app_dir / candidate).resolve()
    try:
        path.relative_to(app_dir.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def data_uri_for_file(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def image_uri(app_dir: Path, value: object) -> str | None:
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"}:
        return candidate
    path = resolve_media_path(app_dir, candidate)
    return data_uri_for_file(path) if path else None


def model_slides_from_settings(
    settings: Mapping[str, str], app_dir: Path
) -> list[dict[str, object]]:
    """Return public-ready slides in cabinet-defined order."""

    slides: list[dict[str, object]] = []
    for slot in range(1, SLIDE_COUNT + 1):
        prefix = f"model_slide_{slot}"
        manifesto_ru = str(settings.get(f"{prefix}_manifesto_ru", "")).strip()
        manifesto_ro = str(settings.get(f"{prefix}_manifesto_ro", "")).strip()
        alt_ru = str(settings.get(f"{prefix}_alt_ru", "")).strip()
        alt_ro = str(settings.get(f"{prefix}_alt_ro", "")).strip()
        source = image_uri(app_dir, settings.get(f"{prefix}_image", ""))
        if (
            settings.get(f"{prefix}_visible", "0") != "1"
            or settings.get(f"{prefix}_translations_approved", "0") != "1"
            or not manifesto_ru
            or not manifesto_ro
            or not alt_ru
            or not alt_ro
            or not source
        ):
            continue
        slides.append(
            {
                "slot": slot,
                "order": _bounded_int(settings.get(f"{prefix}_order"), slot, 1, SLIDE_COUNT),
                "src": source,
                "manifesto": {"ru": manifesto_ru, "ro": manifesto_ro, "en": content_text(settings, f"{prefix}_manifesto", "en")},
                "alt": {"ru": alt_ru, "ro": alt_ro, "en": content_text(settings, f"{prefix}_alt", "en")},
                "duration": _bounded_int(
                    settings.get(f"{prefix}_duration_seconds"), 7, 3, 30
                )
                * 1000,
                "desktop_x": _bounded_int(settings.get(f"{prefix}_desktop_x"), 50, 0, 100),
                "desktop_y": _bounded_int(settings.get(f"{prefix}_desktop_y"), 50, 0, 100),
                "mobile_x": _bounded_int(settings.get(f"{prefix}_mobile_x"), 50, 0, 100),
                "mobile_y": _bounded_int(settings.get(f"{prefix}_mobile_y"), 50, 0, 100),
            }
        )
    slides.sort(key=lambda slide: (int(slide["order"]), int(slide["slot"])))
    return slides


def _safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def model_intro_from_settings(
    settings: Mapping[str, str], app_dir: Path
) -> dict[str, object] | None:
    """Return an optional, bilingual introduction without changing old landings."""

    if (
        settings.get("model_published", "0") != "1"
        or settings.get("model_intro_enabled", "0") != "1"
        or settings.get("model_intro_translations_approved", "0") != "1"
    ):
        return None
    content = {
        field: {
            language: str(settings.get(f"model_intro_{field}_{language}", "")).strip()
            for language in ("ru", "ro")
        }
        for field in ("title", "text", "details", "alt")
    }
    if any(not content[field][language] for field in ("title", "text", "alt") for language in ("ru", "ro")):
        return None
    if bool(content["details"]["ru"]) != bool(content["details"]["ro"]):
        return None
    for field in content:
        content[field]['en'] = content_text(settings, f'model_intro_{field}', 'en')
    candidate = str(settings.get("model_intro_image", "")).strip()
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc or parsed.username or parsed.password:
            return None
    else:
        path = resolve_media_path(app_dir, candidate)
        if path is None or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}:
            return None
    source = image_uri(app_dir, candidate)
    if not source:
        return None
    return {
        **content,
        "src": source,
        "desktop_x": _bounded_int(settings.get("model_intro_desktop_x"), 50, 0, 100),
        "desktop_y": _bounded_int(settings.get("model_intro_desktop_y"), 35, 0, 100),
        "mobile_x": _bounded_int(settings.get("model_intro_mobile_x"), 50, 0, 100),
        "mobile_y": _bounded_int(settings.get("model_intro_mobile_y"), 28, 0, 100),
    }


def build_model_landing_html(
    settings: Mapping[str, str], locale: str, app_dir: Path
) -> str:
    """Build the self-contained responsive landing embedded by Streamlit."""

    from scena_model_builder import parse_model_design
    design = parse_model_design(settings.get("model_design_json"))
    language = locale if locale in {"ru", "ro", "en"} else "ro"
    slides = model_slides_from_settings(settings, app_dir)
    intro = model_intro_from_settings(settings, app_dir)
    if intro and settings.get("model_slider_enabled", "1") != "1":
        slides = []
    if not slides and not intro:
        raise ValueError("No approved model slides are available.")

    requested_first = _bounded_int(settings.get("model_slider_first"), 1, 1, SLIDE_COUNT)
    first_index = next(
        (index for index, slide in enumerate(slides) if slide["slot"] == requested_first),
        0,
    )
    autoplay = settings.get("model_slider_autoplay", "1") == "1"
    from scena_i18n import localized_name
    master_name = localized_name(settings, language) or "Model"
    name_parts = master_name.split(maxsplit=1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    location = content_text(settings, "location", language)
    role = content_text(settings, "model_title", language, "Model")

    copy = {
        "ru": {
            "scene": "МОЯ СЦЕНА",
            "available": "ДОСТУПНА ДЛЯ ПРОЕКТОВ",
            "manifesto": "ЛИЧНЫЙ МАНИФЕСТ",
            "portfolio": "ПОРТФОЛИО",
            "invite": "ПРИГЛАСИТЬ В ПРОЕКТ",
            "previous": "Предыдущий кадр",
            "next": "Следующий кадр",
            "pause": "Остановить показ",
            "play": "Продолжить показ",
            "select": "Показать кадр",
            "unavailable": "Этот кадр пока недоступен. Выберите другой.",
            "introduction": "Знакомство",
            "enter": "Смотреть образы",
        },
        "ro": {
            "scene": "SCENA MEA",
            "available": "DISPONIBILĂ PENTRU PROIECTE",
            "manifesto": "MANIFEST PERSONAL",
            "portfolio": "PORTOFOLIU",
            "invite": "INVITĂ ÎN PROIECT",
            "previous": "Cadrul anterior",
            "next": "Cadrul următor",
            "pause": "Oprește prezentarea",
            "play": "Continuă prezentarea",
            "select": "Arată cadrul",
            "unavailable": "Acest cadru nu este disponibil. Alege altul.",
            "introduction": "Cunoaște-mă",
            "enter": "Vezi imaginile",
        },
        "en": {
            "scene": "MY SCENE", "available": "OPEN TO PROJECTS", "manifesto": "PERSONAL MANIFESTO",
            "portfolio": "PORTFOLIO", "invite": "INVITE TO A PROJECT", "previous": "Previous image",
            "next": "Next image", "pause": "Pause show", "play": "Resume show", "select": "Show image",
            "unavailable": "Choose another image.", "introduction": "Meet me", "enter": "Explore the looks",
        },
    }[language]
    location_line = " · ".join(part for part in (location.upper(), copy["available"]) if part)

    slider_dir = app_dir / "media" / "model-slider"
    serif_uri = data_uri_for_file(slider_dir / "P052-Roman.otf")
    sans_uri = data_uri_for_file(slider_dir / "NimbusSans-Regular.otf")
    icons = {
        name: data_uri_for_file(slider_dir / f"{name}.svg")
        for name in ("arrow-left", "arrow-right", "pause", "play")
    }
    image_markup = "".join(
        (
            f'<figure class="slide{" is-active" if index == first_index else ""}" '
            f'data-index="{index}" style="--dx:{slide["desktop_x"]}%;--dy:{slide["desktop_y"]}%;'
            f'--mx:{slide["mobile_x"]}%;--my:{slide["mobile_y"]}%">'
            f'<img src="{slide["src"]}" alt="{html.escape(str(slide["alt"][language]), quote=True)}" '
            f'{"fetchpriority=\"high\"" if index == first_index else "loading=\"eager\""} decoding="async"></figure>'
        )
        for index, slide in enumerate(slides)
    )
    dot_markup = "".join(
        f'<button type="button" class="dot{" is-current" if index == first_index else ""}" '
        f'data-index="{index}" aria-label="{html.escape(copy["select"], quote=True)} {index + 1}"><span></span></button>'
        for index in range(len(slides))
    )
    scene_url = internal_page_url("scene", locale=language)
    model_url_ru = internal_page_url("model", locale="ru")
    model_url_ro = internal_page_url("model", locale="ro")
    model_url_en = internal_page_url("model", locale="en")
    qr_uri = "data:image/png;base64," + base64.b64encode(qr_png_bytes(public_page_url(settings, "model", locale=language))).decode("ascii")
    portfolio_url = internal_page_url("portfolio", locale=language, view="model")
    invite_url = internal_page_url("invite-model", locale=language)
    initial_statement = str(slides[first_index]["manifesto"][language]) if slides else ""
    intro_markup = ""
    intro_return_markup = ""
    cube_intro = bool(intro and settings.get("model_intro_image") == "media/qr-scenes/model.png")
    qr_label = {"ru": "Моя Сцена — с вами", "ro": "Scena mea, cu tine", "en": "My Scene, with you"}[language]
    if intro:
        intro_details = (
            f'<p class="intro-details">{html.escape(str(intro["details"][language]))}</p>'
            if intro["details"][language] else ""
        )
        qr_markup = (
            f'<button class="cube-qr" type="button" aria-label="QR — Model"><img src="{qr_uri}" alt="QR — Model"></button>'
            if cube_intro else f'<figcaption class="intro-qr"><img src="{qr_uri}" alt="QR — Model"><span>{html.escape(qr_label)}</span></figcaption>'
        )
        intro_markup = (
            '<section class="introduction" id="introduction" aria-labelledby="intro-title">'
            '<div class="intro-copy" tabindex="0" role="region" '
            f'aria-label="{html.escape(copy["introduction"], quote=True)}">'
            f'<p class="intro-kicker">{html.escape(copy["introduction"])}</p>'
            f'<h2 id="intro-title">{html.escape(str(intro["title"][language]))}</h2>'
            f'<p class="intro-text">{html.escape(str(intro["text"][language]))}</p>'
            f'{intro_details}<div class="intro-signature"><h1 class="intro-name"><span class="first">{html.escape(first_name)}</span>'
            f'<span class="last">{html.escape(last_name)}</span></h1><span class="intro-role">{html.escape(role)}</span></div></div>' 
            '<figure class="intro-photo" '
            f'style="--dx:{intro["desktop_x"]}%;--dy:{intro["desktop_y"]}%;'
            f'--mx:{intro["mobile_x"]}%;--my:{intro["mobile_y"]}%">'
            f'<img src="{html.escape(str(intro["src"]), quote=True)}" '
            f'alt="{html.escape(str(intro["alt"][language]), quote=True)}" '
            'fetchpriority="high" decoding="async">'
            f'{qr_markup}</figure>'
            '<div class="intro-actions"><div id="intro-invite-slot"></div>'
            f'<button type="button" class="intro-enter" id="enter-images" {"" if slides else "hidden"}>{html.escape(copy["enter"])}'
            f'<img class="icon" src="{icons["arrow-right"]}" alt=""></button></div></section>'
        )
        intro_return_markup = f'<button type="button" id="return-intro" class="return-intro" hidden>{html.escape(copy["introduction"])}</button>'
    client_slides = [
        {
            "manifesto": slide["manifesto"],
            "duration": slide["duration"],
        }
        for slide in slides
    ]
    state_json = _safe_json(
        {
            "slides": client_slides,
            "language": language,
            "firstIndex": first_index,
            "autoplay": autoplay,
            "hasIntro": bool(intro),
            "cubeIntro": cube_intro,
            "animation": design["animation"],
            "copy": copy,
            "icons": icons,
        }
    )

    design_css = f":root{{--stage-accent:{design['accent']};--stage-background:{design['background']}}}"
    design_css += ".shell,.stage,.manifest{background-color:var(--stage-background)}.role,.intro-kicker,.intro-role{color:var(--stage-accent)}.intro-enter,.portfolio-link{border-color:var(--stage-accent)}.shell.intro-open .stage{background:radial-gradient(ellipse at 75% 25%,color-mix(in srgb,var(--stage-accent) 10%,transparent),transparent 60%),var(--stage-background)}"
    if design['theme'] == 'club':
        design_css += ".intro-photo:before{box-shadow:0 0 70px color-mix(in srgb,var(--stage-accent) 30%,transparent);border-color:var(--stage-accent)}.intro-photo{border-radius:4px}.shell.intro-open .stage{background:linear-gradient(125deg,var(--stage-background) 40%,color-mix(in srgb,var(--stage-accent) 16%,var(--stage-background)))}"
    elif design['theme'] in {'editorial', 'custom'}:
        design_css += ".intro-photo{border-radius:0}.intro-photo:before{display:none}"
    if design['layout'] == 'portrait-left':
        design_css += "@media(min-width:721px){.intro-photo{grid-column:1}.intro-copy,.intro-actions{grid-column:2}.intro-photo{grid-row:1/3}.slide img{margin-left:0;margin-right:auto}.identity{left:auto;right:5vw;width:45vw}.stage:after{transform:scaleX(-1)}}"
    if not design['show_location']:
        design_css += ".location{display:none}"
    if not design['show_manifesto']:
        design_css += ".manifest-copy{display:none}"
    if not design['show_portfolio']:
        design_css += ".portfolio-link{display:none}"
    return f'''<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
@font-face{{font-family:ScenaSerif;src:url("{serif_uri}") format("opentype");font-display:swap}}
@font-face{{font-family:ScenaSans;src:url("{sans_uri}") format("opentype");font-display:swap}}
:root{{--paper:#f5f2ed;--muted:rgba(245,242,237,.66);--hairline:rgba(245,242,237,.22);--black:#030303}}
*{{box-sizing:border-box}}html,body{{margin:0;min-width:0;height:100%;overflow:hidden;background:var(--black);color:var(--paper);font-family:ScenaSans,Arial,sans-serif;-webkit-font-smoothing:antialiased}}
button,a{{-webkit-tap-highlight-color:transparent}}button{{font:inherit}}button:focus-visible,a:focus-visible{{outline:1px solid var(--paper);outline-offset:4px}}
.shell{{height:100vh;overflow:hidden;background:var(--black)}}
[hidden]{{display:none!important}}
.stage{{position:relative;height:calc(100vh - 182px);min-height:540px;overflow:hidden;background:#030303;isolation:isolate}}
.slides,.slide{{position:absolute;inset:0}}.slide{{margin:0;opacity:0;visibility:hidden;z-index:0}}
.slide.is-active{{opacity:1;visibility:visible;z-index:1}}.slide img{{width:min(62vw,920px);height:100%;margin-left:auto;display:block;object-fit:contain;object-position:var(--dx) var(--dy);transform:scale(1.012);filter:saturate(.97) contrast(1.015) blur(0px)}}
.slide.is-moving img{{will-change:transform,filter}}.slide.is-moving{{will-change:opacity}}
.stage:after{{content:"";position:absolute;inset:0;z-index:2;pointer-events:none;background:linear-gradient(90deg,rgba(3,3,3,.68) 0%,rgba(3,3,3,.12) 48%,transparent 72%),linear-gradient(180deg,#030303 0%,transparent 18%,transparent 76%,rgba(3,3,3,.48) 100%)}}
.header{{position:absolute;inset:0 0 auto;height:96px;padding:32px clamp(26px,4vw,64px);display:flex;justify-content:space-between;align-items:flex-start;z-index:4;pointer-events:none}}
.wordmark{{color:var(--paper);font-family:ScenaSerif,Georgia,serif;font-size:clamp(25px,2.4vw,38px);line-height:1;letter-spacing:-.02em;text-decoration:none;pointer-events:auto}}
.header nav{{display:flex;align-items:center;gap:28px;pointer-events:auto}}.header nav>a,.languages{{color:rgba(255,255,255,.8);font-size:11px;letter-spacing:.23em;line-height:1;text-decoration:none}}
.separator{{width:1px;height:18px;background:rgba(255,255,255,.25)}}.languages{{display:flex;align-items:center;gap:8px}}.languages a{{color:rgba(255,255,255,.48);text-decoration:none}}.languages a.current{{color:#fff}}
.identity{{position:absolute;left:clamp(48px,5vw,76px);top:50%;width:min(52vw,760px);z-index:4;transform:translateY(-42%);text-shadow:0 2px 32px rgba(0,0,0,.9)}}
.role{{margin:0 0 14px;color:#c9c1b5;font-size:10px;letter-spacing:.42em;text-transform:uppercase}}.identity h1{{margin:0 0 22px;color:#fff;font-family:ScenaSerif,Georgia,serif;font-weight:400;line-height:.84;letter-spacing:-.035em;text-transform:uppercase}}
.identity h1 span{{display:block}}.first{{font-size:clamp(52.5px,6.6vw,99px)}}.last{{font-size:clamp(25.5px,3.3vw,49.5px)}}.location{{display:block;color:rgba(255,255,255,.74);font-size:10px;letter-spacing:.24em}}
.hero-actions{{margin-top:30px;display:flex;gap:12px}}.hero-actions a,.invite{{min-height:48px;min-width:190px;padding:0 18px;border:1px solid rgba(255,255,255,.46);display:inline-flex;align-items:center;justify-content:space-between;gap:24px;color:var(--paper);background:rgba(3,3,3,.3);font-size:10px;letter-spacing:.16em;text-decoration:none}}
.hero-actions a:last-child{{border-color:#c9c1b5;background:#161513}}.icon{{width:18px;height:18px;display:block}}
.manifest{{height:182px;padding:24px clamp(26px,4vw,64px) 20px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;align-items:center;column-gap:clamp(28px,5vw,84px);row-gap:18px;position:relative;z-index:5;background:#030303;border-top:1px solid var(--hairline)}}
.manifest-copy{{min-width:0}}.manifest-label{{margin-bottom:10px;display:flex;align-items:center;gap:18px;color:var(--muted);font-size:10px;letter-spacing:.22em}}.manifest-label span:last-child{{color:rgba(255,255,255,.38)}}
blockquote{{margin:0;max-width:900px;color:var(--paper);font-family:ScenaSerif,Georgia,serif;font-size:clamp(23px,2.25vw,38px);line-height:1.12;letter-spacing:-.018em}}
.invite{{min-height:54px;padding:0 24px;background:transparent;justify-content:center}}.invite:hover{{color:#080808;background:var(--paper);border-color:var(--paper)}}
.controls{{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center}}.dots{{display:flex;align-items:center;gap:9px}}.dot{{width:30px;height:22px;padding:0;border:0;display:grid;place-items:center;background:transparent;cursor:pointer}}.dot span{{width:100%;height:1px;background:rgba(255,255,255,.24)}}.dot.is-current span{{height:2px;background:var(--paper)}}
.transport{{display:flex;align-items:center;gap:8px}}.transport button{{width:38px;height:38px;padding:0;border:1px solid rgba(255,255,255,.2);border-radius:50%;display:grid;place-items:center;background:transparent;cursor:pointer}}.transport button:hover{{border-color:rgba(255,255,255,.8);background:rgba(255,255,255,.08)}}
.progress{{position:absolute;inset:auto 0 0;height:2px;overflow:hidden;background:rgba(255,255,255,.08)}}.progress span{{display:block;width:100%;height:100%;background:rgba(255,255,255,.82);transform-origin:left center;animation:progress var(--duration) linear both}}@keyframes progress{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@media(max-width:720px){{.stage{{height:67vh;min-height:500px}}.slide img{{width:100%;margin:0;object-fit:cover;object-position:var(--mx) var(--my)}}.stage:after{{background:linear-gradient(180deg,rgba(3,3,3,.16) 0%,transparent 24%,rgba(3,3,3,.08) 58%,rgba(3,3,3,.92) 100%),linear-gradient(90deg,rgba(3,3,3,.28),transparent 34%,transparent 76%,rgba(3,3,3,.12))}}.header{{height:82px;padding:24px 20px}}.wordmark{{font-size:26px}}.header nav{{gap:15px}}.header nav>a,.separator{{display:none}}.languages{{font-size:10px}}
.identity{{left:20px;right:20px;bottom:24px;top:auto;width:auto;transform:none}}.role{{margin-bottom:9px;color:rgba(255,255,255,.75);font-size:9px;letter-spacing:.34em}}.identity h1{{margin-bottom:10px;max-width:100%;font-size:clamp(22.5px,6.375vw,30px);line-height:.88;white-space:nowrap}}.first,.last{{font-size:inherit}}.location{{font-size:8px;letter-spacing:.17em}}.hero-actions{{display:none}}
.manifest{{height:33vh;min-height:0;padding:20px 20px max(17px,env(safe-area-inset-bottom));grid-template-columns:1fr auto;grid-template-rows:auto auto auto;column-gap:14px;row-gap:15px}}.manifest-copy,.invite,.controls{{grid-column:1/-1}}.manifest-label{{margin-bottom:8px;justify-content:space-between;font-size:8px}}blockquote{{max-width:32ch;font-size:clamp(21px,6.4vw,28px);line-height:1.06}}.invite{{width:100%;min-height:48px;padding:0 16px;font-size:10px}}.dots{{gap:3px}}.dot{{width:22px}}.transport{{gap:5px}}.transport button{{width:34px;height:34px}}}}
@media(max-width:380px),(max-height:720px){{.stage{{height:64vh;min-height:420px}}.manifest{{height:36vh;padding-top:14px;row-gap:10px}}blockquote{{font-size:20px}}.invite{{min-height:43px}}}}
.introduction{{position:absolute;inset:112px clamp(30px,5vw,76px) 28px;z-index:3;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.9fr);grid-template-rows:minmax(0,1fr) auto;column-gap:clamp(30px,6vw,92px);row-gap:24px}}
.intro-copy{{min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#555 transparent;padding:8px 18px 8px 0;align-self:stretch;overflow-wrap:anywhere}}
.intro-kicker{{margin:0 0 24px;color:#d6c7ae;font-size:10px;letter-spacing:.32em;text-transform:uppercase}}
.intro-name{{margin:0 0 32px;font-family:ScenaSerif,Georgia,serif;font-weight:400;line-height:.88;letter-spacing:-.035em;text-transform:uppercase}}.intro-name span{{display:block}}
.intro-copy h2{{margin:0 0 20px;font-family:ScenaSerif,Georgia,serif;font-size:clamp(27px,2.7vw,40px);font-weight:400;line-height:1.14;white-space:pre-line}}
.intro-text,.intro-details{{white-space:pre-wrap;font-size:clamp(15px,1.15vw,18px);line-height:1.65;margin:0 0 18px;color:#d0ceca}}
.intro-details{{padding-top:18px;border-top:1px solid var(--hairline);color:#a7a4a0;font-size:14px}}
.intro-photo{{grid-column:2;grid-row:1/3;margin:0;min-height:0;display:flex;align-items:center;justify-content:center;position:relative;background:radial-gradient(ellipse at center,rgba(177,168,141,.1),transparent 68%)}}
.intro-photo img{{display:block;max-width:100%;width:100%;height:100%;object-fit:contain;object-position:var(--dx) var(--dy);filter:none}}
.intro-enter{{grid-column:1;grid-row:2;align-self:start;justify-self:start;display:inline-flex;align-items:center;justify-content:space-between;gap:38px;min-height:54px;max-width:100%;padding:14px 24px;background:#161513;border:1px solid #c9c1b5;color:#fff;font-size:13px;cursor:pointer}}.intro-enter:hover{{background:#302c27}}
.return-intro{{border:0;border-bottom:1px solid #c9c1b5;background:transparent;color:#e4dfd7;min-height:32px;font-size:12px;cursor:pointer;white-space:nowrap}}
.shell.intro-open .stage{{height:calc(100vh - 94px);min-height:0}}.shell.intro-open .stage:after{{display:none}}.shell.intro-open .slides,.shell.intro-open .identity{{display:none}}
.shell.intro-open .manifest{{height:94px;padding-top:18px;padding-bottom:18px;display:flex;justify-content:flex-end;align-items:center}}
.shell.intro-open .manifest-copy,.shell.intro-open .controls,.shell.intro-open .progress{{display:none}}.shell.intro-open .invite{{min-width:260px}}
@media(max-width:1000px) and (min-width:721px){{.introduction{{column-gap:30px;left:30px;right:30px}}.intro-name .first{{font-size:clamp(42px,6.2vw,65px)}}.intro-name .last{{font-size:clamp(22px,3.1vw,33px)}}}}
@media(max-width:720px){{
  .introduction{{inset:76px 20px 18px;grid-template-columns:minmax(0,1fr);grid-template-rows:max(260px,48%) minmax(0,1fr) auto;gap:18px}}
  .intro-photo{{grid-column:1;grid-row:1;min-height:0;overflow:hidden}}.intro-photo img{{object-fit:cover;object-position:var(--mx) var(--my)}}
  .intro-photo:after{{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(180deg,transparent 75%,rgba(3,3,3,.12) 87%,#030303 100%)}}
  .intro-copy{{grid-column:1;grid-row:2;padding:2px 8px 2px 0}}.intro-kicker{{margin-bottom:12px;font-size:9px;letter-spacing:.24em}}
  .intro-name{{margin-bottom:18px;line-height:.94}}.intro-name .first,.intro-name .last{{font-size:clamp(22.5px,6.375vw,30px)}}
  .intro-copy h2{{font-size:25px;margin-bottom:12px}}.intro-text{{font-size:15px;line-height:1.55;margin-bottom:14px}}.intro-details{{font-size:13px}}
  .intro-enter{{grid-row:3;width:100%;min-height:48px;justify-self:stretch;padding:12px 18px}}
  .shell.intro-open .stage{{height:calc(100vh - 80px)}}.shell.intro-open .manifest{{height:80px;padding:13px 20px 17px}}.shell.intro-open .invite{{min-width:0;width:100%;min-height:48px}}
  .header nav .return-intro{{display:inline-block;font-size:11px}}.header nav:has(.return-intro:not([hidden])){{gap:12px}}
}}
@media(max-height:650px) and (max-width:720px){{.introduction{{top:68px;gap:12px;grid-template-rows:260px minmax(0,1fr) auto}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{animation:none!important;transition:none!important}}}}

.cube-qr{{position:absolute;z-index:5;padding:0;border:0;background:transparent;cursor:pointer;min-width:44px;min-height:44px;display:grid;place-items:center}}.cube-qr img{{display:block;width:var(--qr-size);height:var(--qr-size);object-fit:contain;mask-image:none;filter:none}}.qr-dialog{{max-width:calc(100vw - 36px);background:#fff;border:0;border-radius:8px;padding:24px;text-align:center;color:#151413}}.qr-dialog::backdrop{{background:#000c}}.qr-dialog img{{width:280px;max-width:100%;display:block}}.qr-dialog button{{border:0;background:white;min-width:44px;min-height:44px;font-size:30px;float:right;cursor:pointer}}
/* V1.7: a personal stage, calm chrome actions, readable QR, no blue controls. */
.identity{{top:auto;bottom:52px;transform:none}}
.hero-actions{{display:flex;max-width:400px}}.invite{{background:#eee9df;color:#161513;border-color:#eee9df;letter-spacing:.1em;font-size:12px;min-height:52px;min-width:250px;font-weight:600}}
.hero-actions a.invite{{background:#eee9df;color:#161513;border-color:#eee9df}}.invite .icon{{filter:invert(1)}}.invite:hover{{background:white}}.portfolio-link{{grid-column:2;grid-row:1;min-height:48px;display:flex;align-items:center;justify-content:center;gap:22px;padding:12px 22px;border:1px solid #6d6862;color:#e8e3da;text-decoration:none;font-size:12px;letter-spacing:.12em;background:#0c0c0b}}.portfolio-link:hover{{border-color:#e8e3da}}
.manifest-copy{{grid-column:1;grid-row:1}}.introduction{{inset:112px clamp(30px,5vw,76px) 26px;grid-template-columns:minmax(0,1fr) minmax(0,1.04fr);row-gap:22px}}
.shell.intro-open .stage{{height:100vh;background:radial-gradient(ellipse at 75% 24%,#3a322526,transparent 53%),linear-gradient(140deg,#050505,#0e0d0b 60%,#040404)}}
.shell.intro-open .manifest{{display:none}}.intro-photo{{background:radial-gradient(ellipse at 50% 46%,#a5966b23,transparent 66%);border:1px solid #ffffff18;border-top-left-radius:50% 22%;border-top-right-radius:50% 22%;overflow:hidden}}
.intro-photo:before{{content:"";position:absolute;inset:4% 7%;border-radius:50% 50% 0 0;border:1px solid #d0c5ae33;pointer-events:none;box-shadow:0 0 80px #d4c5a312}}
.intro-photo>img{{position:relative;z-index:1;object-fit:contain;mask-image:linear-gradient(to bottom,#000 88%,transparent)}}
.intro-kicker{{font-size:12px;color:#c3b49b;margin-bottom:22px;letter-spacing:.27em}}
.intro-copy{{display:flex;flex-direction:column;padding-top:38px}}.intro-copy h2{{font-size:clamp(33px,3.8vw,58px);max-width:14ch;letter-spacing:-.015em;line-height:1.05}}
.intro-text{{max-width:42ch;color:#c9c4bb;font-size:17px;line-height:1.65}}.intro-signature{{margin-top:auto;padding-top:26px}}.intro-name{{margin-bottom:10px}}.intro-name .first{{font-size:clamp(36px,4vw,58px)}}.intro-name .last{{font-size:clamp(25px,2.8vw,39px)}}.intro-role{{color:#bfb4a2;font-size:12px;letter-spacing:.18em;text-transform:uppercase}}
.intro-actions{{grid-column:1;grid-row:2;display:flex;flex-direction:column;gap:10px;align-items:stretch;max-width:400px}}.intro-actions .invite{{width:100%;min-width:0}}.intro-enter{{grid-row:auto;min-height:46px;background:transparent;border:1px solid #6c655c;justify-content:center;gap:22px;font-size:13px;letter-spacing:.08em;width:100%;padding:12px 18px}}
.intro-qr{{position:absolute;z-index:3;bottom:22px;right:18px;display:flex;align-items:center;gap:12px;color:#e2dbcf;background:#10100fce;padding:10px;border:1px solid #bdb29b45;border-radius:4px;backdrop-filter:blur(12px)}}.intro-qr img{{width:106px;height:106px;display:block;object-fit:contain;filter:none;mask-image:none}}.intro-qr span{{max-width:90px;font-family:ScenaSerif,Georgia,serif;font-size:19px;line-height:1.15}}
@media(max-width:720px){{
  .header{{padding:22px 20px}}.languages{{font-size:12px;gap:7px}}.languages a{{min-height:28px;display:inline-flex;align-items:center}}.header nav{{gap:12px}}.header nav .return-intro{{font-size:12px}}
  .introduction{{inset:78px 20px 18px;grid-template-rows:minmax(200px,37%) minmax(0,1fr) auto;gap:15px;grid-template-columns:minmax(0,1fr)}}
  .intro-photo{{border-radius:44% 44% 0 0;grid-column:1;grid-row:1}}.intro-photo>img{{object-fit:contain}}.intro-photo:after{{display:none}}.intro-qr{{bottom:8px;right:8px;padding:5px;border-radius:2px;gap:0}}.intro-qr img{{width:80px;height:80px}}.intro-qr span{{display:none}}
  .intro-copy{{grid-row:2;display:block;padding:0 4px 0 0}}.intro-kicker{{font-size:10px;margin-bottom:10px}}.intro-copy h2{{font-size:30px;max-width:20ch;margin-bottom:12px}}.intro-text{{font-size:15px;line-height:1.5}}.intro-details{{font-size:14px}}
  .intro-signature{{padding-top:8px;margin-top:14px}}.intro-name .first,.intro-name .last{{font-size:26px;line-height:1}}.intro-name{{margin-bottom:8px}}.intro-role{{font-size:11px;letter-spacing:.11em}}
  .intro-actions{{grid-row:3;max-width:none;width:100%;gap:8px}}.intro-actions .invite{{min-height:48px;font-size:11px}}.intro-enter{{min-height:44px;font-size:12px;padding:10px}}
  .identity{{bottom:22px;left:20px;right:20px}}.identity .hero-actions{{display:flex;margin-top:17px;max-width:none}}.identity .invite{{min-width:0;width:100%;font-size:11px;min-height:48px}}.identity .location{{font-size:10px;line-height:1.5}}
  .manifest{{grid-template-rows:auto auto auto;row-gap:12px}}.manifest-copy{{grid-column:1/-1;grid-row:1}}.portfolio-link{{grid-column:1/-1;grid-row:2;min-height:43px;font-size:11px}}.controls{{grid-row:3}}.transport button{{width:40px;height:40px}}
}}
@media(max-height:660px) and (max-width:720px){{.introduction{{top:72px;grid-template-rows:185px minmax(0,1fr) auto;gap:10px}}.intro-copy h2{{font-size:25px}}.intro-enter{{min-height:42px}}}}

@media(max-width:340px){{.header nav .return-intro{{position:absolute;right:20px;top:57px;min-height:32px;font-size:11px}}.intro-copy h2{{font-size:27px}}.intro-name .first,.intro-name .last{{font-size:23px}}.intro-text{{font-size:14px}}.intro-actions .invite{{font-size:10px;letter-spacing:.02em;gap:10px}}.hero-actions .invite{{letter-spacing:0;font-size:10px;gap:12px}}}}
{design_css}
</style>
</head>
<body>
<main class="shell{" intro-open" if intro else ""}" id="top" data-view="{"intro" if intro else "images"}">
  <section class="stage" aria-roledescription="carousel" aria-label="SCENA — {html.escape(master_name, quote=True)}">
    <div class="slides" aria-live="off">{image_markup}</div>
    <header class="header">
      <a class="wordmark" target="_blank" rel="noopener noreferrer" href="{html.escape(scene_url, quote=True)}" aria-label="SCENA">SCENA</a>
      <nav aria-label="Navigation">{intro_return_markup}<a target="_blank" rel="noopener noreferrer" href="{html.escape(scene_url, quote=True)}">{copy["scene"]}</a><span class="separator"></span><div class="languages"><a target="_blank" rel="noopener noreferrer" href="{html.escape(model_url_ru, quote=True)}" class="{"current" if language == "ru" else ""}">RU</a><span>/</span><a target="_blank" rel="noopener noreferrer" href="{html.escape(model_url_ro, quote=True)}" class="{"current" if language == "ro" else ""}">RO</a><span>/</span><a target="_blank" rel="noopener noreferrer" href="{html.escape(model_url_en, quote=True)}" class="{"current" if language == "en" else ""}">EN</a></div></nav>
    </header>
    <div class="identity"><p class="role">{html.escape(role)}</p><h1><span class="first">{html.escape(first_name)}</span><span class="last">{html.escape(last_name)}</span></h1><span class="location">{html.escape(location_line)}</span><div class="hero-actions" id="show-invite-slot"></div></div>
    {intro_markup}
  </section>
  <section class="manifest" id="manifesto"><a class="portfolio-link" target="_blank" rel="noopener noreferrer" href="{html.escape(portfolio_url, quote=True)}">{copy["portfolio"]}<img class="icon" src="{icons["arrow-right"]}" alt=""></a><div class="manifest-copy" aria-live="polite"><div class="manifest-label"><span>{copy["manifesto"]}</span><span id="counter"></span></div><blockquote id="statement">“{html.escape(initial_statement)}”</blockquote></div><a class="invite" target="_blank" rel="noopener noreferrer" href="{html.escape(invite_url, quote=True)}">{copy["invite"]}<img class="icon" src="{icons["arrow-right"]}" alt=""></a><div class="controls"><div class="dots">{dot_markup}</div><div class="transport"><button id="previous" type="button" aria-label="{html.escape(copy["previous"], quote=True)}"><img class="icon" src="{icons["arrow-left"]}" alt=""></button><button id="toggle" type="button"><img class="icon" id="toggle-icon" alt=""></button><button id="next" type="button" aria-label="{html.escape(copy["next"], quote=True)}"><img class="icon" src="{icons["arrow-right"]}" alt=""></button></div></div><div class="progress" id="progress"><span></span></div></section>
</main><dialog class="qr-dialog" id="qr-dialog"><form method="dialog"><button aria-label="Close">×</button></form><img src="{qr_uri}" alt="QR — Model"><p>SCENA · {html.escape(master_name)}</p></dialog>
<script>
const state={state_json},reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
let introOpen=state.hasIntro,entered=false;
let active=state.firstIndex,requested=active,playing=!introOpen&&state.autoplay&&!reducedMotion.matches,timer=null,touchStart=null,requestVersion=0,moving=false,drift=null;
const stage=document.querySelector('.stage'),figures=[...document.querySelectorAll('.slide')],dots=[...document.querySelectorAll('.dot')],statement=document.getElementById('statement'),counter=document.getElementById('counter'),progress=document.getElementById('progress'),toggle=document.getElementById('toggle'),toggleIcon=document.getElementById('toggle-icon');
const shell=document.querySelector('.shell'),introduction=document.getElementById('introduction'),enterButton=document.getElementById('enter-images'),returnButton=document.getElementById('return-intro');
const images=figures.map(figure=>figure.querySelector('img')),baseFilter='saturate(.97) contrast(1.015) blur(0px)',motionDuration=1400;
let transitionAnimations=[];
const pad=n=>String(n+1).padStart(2,'0');
function syncPlay(){{toggleIcon.src=playing?state.icons.pause:state.icons.play;toggle.ariaLabel=playing?state.copy.pause:state.copy.play;toggle.setAttribute('aria-pressed',String(playing));progress.hidden=!playing||figures.length<2}}
function syncCopy(){{
  if(!figures.length)return;
  dots.forEach((node,i)=>{{node.classList.toggle('is-current',i===active);if(i===active)node.setAttribute('aria-current','true');else node.removeAttribute('aria-current')}});
  statement.textContent='“'+state.slides[active].manifesto[state.language]+'”';counter.textContent=pad(active)+' / '+pad(figures.length-1);stage.dataset.active=String(active);
}}
function schedule(){{
  clearTimeout(timer);timer=null;if(introOpen||!figures.length||moving||requested!==active)return;
  const duration=state.slides[active].duration;progress.style.setProperty('--duration',duration+'ms');
  const bar=progress.querySelector('span');bar.style.animation='none';void bar.offsetWidth;bar.style.animation='';
  if(playing&&figures.length>1)timer=setTimeout(()=>show(active+1),duration);
}}
// Freeze the rendered values before cancelling drift; removing a class cannot
// reset the outgoing photo to an earlier scale or restart its animation.
function freezeImage(image){{
  const computed=getComputedStyle(image),snapshot={{transform:computed.transform,filter:computed.filter}};
  image.style.transform=snapshot.transform;image.style.filter=snapshot.filter;
  image.getAnimations().forEach(animation=>animation.cancel());return snapshot;
}}
function startDrift(){{
  drift=null;if(introOpen||!figures.length||!playing||reducedMotion.matches||state.animation!=='recede')return;
  const image=images[active],snapshot=freezeImage(image);
  drift=image.animate([{{transform:snapshot.transform}},{{transform:'scale(1.045)'}}],{{duration:state.slides[active].duration,easing:'linear',fill:'forwards'}});
}}
function settleFrame(index){{
  if(!figures.length)return;
  figures.forEach((figure,i)=>{{
    figure.classList.toggle('is-active',i===index);figure.classList.remove('is-moving');
    figure.style.opacity=i===index?'1':'0';figure.style.visibility=i===index?'visible':'hidden';figure.style.zIndex=i===index?'1':'0';
    figure.setAttribute('aria-hidden',String(i!==index));
    if(i!==index)images[i].getAnimations().forEach(animation=>animation.cancel());
  }});
  images[index].style.transform='scale(1.012)';images[index].style.filter=baseFilter;
}}
async function decodeFrame(index){{
  const image=images[index];
  // Decode the actual current source on every selection, including a replaced
  // image. Keeping the old frame visible avoids a flash during slow loading.
  await image.decode();if(!image.naturalWidth)throw new Error('unavailable');
}}
async function transitionTo(target){{
  moving=true;stage.dataset.transition='moving';const previous=active;
  const oldFigure=figures[previous],newFigure=figures[target],oldImage=images[previous],newImage=images[target];
  const outgoing=freezeImage(oldImage);drift=null;freezeImage(newImage);
  active=target;syncCopy();
  if(!reducedMotion.matches&&state.animation!=='none'){{
    oldFigure.classList.add('is-moving');newFigure.classList.add('is-moving');
    oldFigure.style.zIndex='2';newFigure.style.zIndex='1';newFigure.style.visibility='visible';newFigure.style.opacity='0';
    const options={{duration:motionDuration,easing:'cubic-bezier(.22,.61,.36,1)',fill:'both'}};
    transitionAnimations=state.animation==='fade'?[oldFigure.animate([{{opacity:1}},{{opacity:0}}],options),newFigure.animate([{{opacity:0}},{{opacity:1}}],options)]:[
      oldImage.animate([outgoing,{{transform:'scale(.97)',filter:'saturate(.97) contrast(1.015) blur(10px)'}}],options),
      oldFigure.animate([{{opacity:1}},{{opacity:0}}],options),
      newImage.animate([{{transform:'scale(1.035)',filter:'saturate(.97) contrast(1.015) blur(8px)'}},{{transform:'scale(1.012)',filter:baseFilter}}],options),
      newFigure.animate([{{opacity:0}},{{opacity:1}}],options)
    ];
    await Promise.all(transitionAnimations.map(animation=>animation.finished.catch(()=>undefined)));
  }}
  // Commit the exact final values before removing the finished effects.
  settleFrame(target);transitionAnimations.forEach(animation=>animation.cancel());transitionAnimations=[];
  moving=false;stage.dataset.transition='idle';
  if(requested!==active){{show(requested);return}}
  startDrift();schedule();
}}
async function show(index){{
  if(introOpen||!figures.length)return;
  requested=(index+figures.length)%figures.length;const version=++requestVersion;clearTimeout(timer);timer=null;
  // Finish one visual transition cleanly, then honour only the newest request.
  if(moving)return;
  if(requested===active){{stage.dataset.transition='idle';schedule();return}}
  const target=requested;stage.dataset.transition='loading';
  try{{await decodeFrame(target)}}catch(error){{
    if(version===requestVersion){{requested=active;stage.dataset.transition='idle';counter.textContent=state.copy.unavailable;schedule()}}
    return;
  }}
  if(version!==requestVersion||moving)return;
  await transitionTo(target);
}}
function setPlaying(value){{
  playing=Boolean(value)&&!introOpen&&figures.length>0&&!reducedMotion.matches;
  if(!playing){{if(drift){{freezeImage(images[active]);drift=null}}}}else if(!moving)startDrift();
  syncPlay();schedule();
}}
function syncIntroduction(){{
  const invite=document.querySelector('a.invite'),slot=document.getElementById(introOpen?'intro-invite-slot':'show-invite-slot');if(invite&&slot)slot.appendChild(invite);
  shell.classList.toggle('intro-open',introOpen);shell.dataset.view=introOpen?'intro':'images';
  if(introduction){{introduction.hidden=!introOpen;introduction.inert=!introOpen}}
  if(returnButton)returnButton.hidden=introOpen;
  for(const selector of ['.slides','.identity','.manifest-copy','.controls']){{
    const node=document.querySelector(selector);node.inert=introOpen;node.setAttribute('aria-hidden',String(introOpen));
  }}
  if(introOpen)stage.removeAttribute('aria-roledescription');else stage.setAttribute('aria-roledescription','carousel');
}}
function enterImages(){{
  if(!introOpen||!figures.length)return;
  introOpen=false;syncIntroduction();
  // Only the first deliberate entry uses the saved autoplay choice. Returning
  // to the business card pauses the show, and re-entry keeps that pause.
  setPlaying(!entered&&state.autoplay);entered=true;
  returnButton?.focus({{preventScroll:true}});
}}
function returnToIntroduction(){{
  if(!state.hasIntro||introOpen)return;
  setPlaying(false);introOpen=true;requestVersion++;requested=active;touchStart=null;
  transitionAnimations.forEach(animation=>animation.finish());
  syncIntroduction();syncPlay();schedule();
  (enterButton?.hidden?document.querySelector('.intro-copy'):enterButton)?.focus({{preventScroll:true}});
}}
if(state.cubeIntro){{
  const photo=document.querySelector('.intro-photo>img'),cube=document.querySelector('.cube-qr');
  const positionQR=()=>{{if(!photo?.naturalWidth||!cube)return;const box=photo.getBoundingClientRect(),parent=photo.parentElement.getBoundingClientRect(),ratio=Math.min(box.width/photo.naturalWidth,box.height/photo.naturalHeight),pos=getComputedStyle(photo).objectPosition.split(' ').map(parseFloat);const size=140*ratio,hit=Math.max(44,size);cube.style.left=(box.left-parent.left+(box.width-photo.naturalWidth*ratio)*(pos[0]/100)+429*ratio-(hit-size)/2)+'px';cube.style.top=(box.top-parent.top+(box.height-photo.naturalHeight*ratio)*(pos[1]/100)+452*ratio-(hit-size)/2)+'px';cube.style.width=hit+'px';cube.style.height=hit+'px';cube.style.setProperty('--qr-size',size+'px')}};
  photo.addEventListener('load',positionQR);new ResizeObserver(positionQR).observe(photo);positionQR();cube.onclick=()=>document.getElementById('qr-dialog').showModal();
}}
if(enterButton)enterButton.onclick=enterImages;
if(returnButton)returnButton.onclick=returnToIntroduction;
document.getElementById('previous').onclick=()=>show(requested-1);document.getElementById('next').onclick=()=>show(requested+1);toggle.onclick=()=>setPlaying(!playing);dots.forEach(node=>node.onclick=()=>show(Number(node.dataset.index)));
stage.addEventListener('touchstart',event=>{{touchStart=!introOpen&&event.changedTouches[0]?{{x:event.changedTouches[0].clientX,y:event.changedTouches[0].clientY}}:null}},{{passive:true}});
stage.addEventListener('touchend',event=>{{if(introOpen||touchStart===null)return;const end=event.changedTouches[0],start=touchStart;touchStart=null;if(!end)return;const dx=end.clientX-start.x,dy=end.clientY-start.y;if(Math.abs(dx)>=48&&Math.abs(dx)>Math.abs(dy))show(requested+(dx>0?-1:1))}},{{passive:true}});
stage.addEventListener('touchcancel',()=>{{touchStart=null}},{{passive:true}});
addEventListener('keydown',event=>{{
  if(introOpen||event.target.closest('input,textarea,select,[contenteditable="true"]'))return;
  if(event.key==='ArrowLeft'){{event.preventDefault();show(requested-1)}}if(event.key==='ArrowRight'){{event.preventDefault();show(requested+1)}}
  if(event.key===' '&&!event.target.closest('button,a,input,textarea,select')){{event.preventDefault();setPlaying(!playing)}}
}});
document.addEventListener('visibilitychange',()=>{{if(document.hidden)setPlaying(false)}});
reducedMotion.addEventListener('change',()=>{{if(reducedMotion.matches){{setPlaying(false);if(drift){{freezeImage(images[active]);drift=null}}transitionAnimations.forEach(animation=>animation.finish())}}}});
function resizeFrame(){{let height=innerHeight;try{{height=parent.innerHeight}}catch(error){{}}height=Math.max(innerWidth<=720?720:760,height);parent.postMessage({{isStreamlitMessage:true,type:'streamlit:setFrameHeight',height}},'*')}}
addEventListener('resize',resizeFrame);resizeFrame();settleFrame(active);syncIntroduction();syncCopy();syncPlay();stage.dataset.transition='idle';
if(figures.length)decodeFrame(active).then(()=>{{if(!moving&&active===state.firstIndex)startDrift()}}).catch(()=>undefined);schedule();
</script>
</body>
</html>'''

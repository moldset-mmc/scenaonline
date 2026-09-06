"""A focused, accessible portfolio stage and persistent twelve-frame editor."""
from __future__ import annotations

import base64
import html
import io
import json
import os
import sqlite3
import tempfile
import uuid
import warnings
from datetime import datetime
from contextlib import closing
from pathlib import Path
from typing import Mapping

import streamlit as st
from PIL import Image, UnidentifiedImageError

from scena_core import DEFAULT_SETTINGS

PORTFOLIO_CAPACITY = 12
MAX_IMAGE_BYTES = 20 * 1024 * 1024
_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


def _prefix(kind: str) -> str:
    if kind in {"Professional", "professional", "beauty"}:
        return "beauty"
    if kind in {"Model", "model"}:
        return "model"
    raise ValueError("Неизвестное портфолио.")


from scena_i18n import tr as _tr, localized_name, translate_literaltext

def ui(value):
    return translate_literaltext(st.session_state.get("scena_ui_locale", "ru"), value)


def _media_path(app_dir: Path, value: object) -> Path | None:
    """Portfolio content can only expose raster images inside this app's media."""
    if not value:
        return None
    root = app_dir.resolve()
    media = (root / "media").resolve()
    try:
        media.relative_to(root)
        path = (root / str(value)).resolve()
        path.relative_to(media)
    except (ValueError, OSError):
        return None
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not path.is_file():
        return None
    return path


def _source(app_dir: Path, value: object) -> str | None:
    path = _media_path(app_dir, value)
    if path is None:
        return None
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def effective_slots(settings: Mapping[str, str], kind: str) -> dict[int, str]:
    """Keep legacy slot numbers; a deliberate empty portfolio stays empty."""
    prefix = _prefix(kind)
    slots = {i: str(settings.get(f"{prefix}_image_{i}", "")).strip() for i in range(1, PORTFOLIO_CAPACITY + 1)}
    if prefix != "model" or any(slots.values()) or settings.get("model_portfolio_customized") == "1":
        return slots
    candidates: list[tuple[int, int, str]] = []
    for index in range(1, 6):
        key = f"model_slide_{index}"
        if settings.get(f"{key}_visible") != "1" or settings.get(f"{key}_translations_approved") != "1":
            continue
        if not all(str(settings.get(f"{key}_{field}", "")).strip() for field in ("manifesto_ru", "manifesto_ro", "alt_ru", "alt_ro")):
            continue
        try:
            order = int(settings.get(f"{key}_order", index))
        except (TypeError, ValueError):
            order = index
        path = str(settings.get(f"{key}_image", "")).strip()
        if path:
            candidates.append((order, index, path))
    for index, (_, _, path) in enumerate(sorted(candidates), 1):
        slots[index] = path
    return slots


def portfolio_frames(app_dir: Path, settings: Mapping[str, str], locale: str, kind: str) -> list[dict[str, str | int]]:
    frames = []
    for slot, value in effective_slots(settings, kind).items():
        source = _source(app_dir, value)
        if source:
            frames.append({"slot": slot, "src": source, "label": _tr(locale, f'Образ {slot}', f'Imaginea {slot}', f'Look {slot}')})
    return frames


def build_portfolio_html(frames: list[dict[str, str | int]], locale: str, name: str = "") -> str:
    """Keep public text escaped and serialize data safely across the script tag."""
    if not frames:
        return ""
    previous = _tr(locale, "Предыдущая фотография", "Fotografia precedentă")
    following = _tr(locale, "Следующая фотография", "Fotografia următoare")
    choose = _tr(locale, "Выбрать фотографию", "Alege fotografia")
    guide = _tr(locale, "Выберите кадр. Посмотрите ближе.", "Alege un cadru. Privește mai aproape.")
    esc = html.escape
    images = "".join(
        f'<figure class="frame {"active" if i == 0 else ""}" aria-hidden="{"false" if i == 0 else "true"}"><img src="{esc(str(frame["src"]), quote=True)}" alt="{esc(str(frame["label"]), quote=True)}" decoding="async" {"fetchpriority=\"high\"" if i == 0 else "loading=\"lazy\""}></figure>'
        for i, frame in enumerate(frames)
    )
    thumbs = "".join(
        f'<button class="thumb {"selected" if i == 0 else ""}" type="button" aria-label="{esc(choose, quote=True)} {i + 1}" aria-pressed="{"true" if i == 0 else "false"}" data-index="{i}"><img src="{esc(str(frame["src"]), quote=True)}" alt="" loading="lazy"><span>{i + 1:02}</span></button>'
        for i, frame in enumerate(frames)
    )
    labels = json.dumps([str(frame["label"]) for frame in frames], ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f'''<!doctype html><html lang="{esc(locale, quote=True)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
*{{box-sizing:border-box}}body{{margin:0;background:#0b0c0d;color:#f7f3ed;font-family:Arial,sans-serif}}.gallery{{padding:22px 26px 20px;background:radial-gradient(ellipse at 50% 0%,#303238 0%,#111315 43%,#080909 80%);border-radius:20px;overflow:hidden}}.top{{display:flex;justify-content:space-between;gap:16px;align-items:center;padding-bottom:16px}}.brand{{font-family:Georgia,serif;letter-spacing:.25em;font-size:18px}}.name{{color:#c1c1bc;font-size:13px;text-align:right;max-width:65%;overflow-wrap:anywhere}}.stage{{position:relative;height:510px;overflow:hidden;background:radial-gradient(ellipse at center,#22262a,#090a0b 75%);border:1px solid #ffffff12;border-radius:8px;touch-action:pan-y}}.frame{{position:absolute;inset:0;margin:0;opacity:0;visibility:hidden;transition:opacity .38s ease,visibility .38s;pointer-events:none}}.frame.active{{opacity:1;visibility:visible}}.frame img{{width:100%;height:100%;object-fit:contain}}button{{font:inherit;cursor:pointer}}.arrow{{position:absolute;z-index:2;top:calc(50% - 24px);height:48px;width:48px;border-radius:50%;border:1px solid #ffffff5c;background:#111b;color:white;font-size:25px;backdrop-filter:blur(8px)}}.arrow:hover{{background:#424348}}.prev{{left:16px}}.next{{right:16px}}.info{{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:17px 0 13px}}.caption{{margin:0;font-size:15px}}.guide{{font-size:12px;color:#adada8;margin-top:6px}}.count{{font-size:13px;letter-spacing:.15em;color:#c9c2b7;white-space:nowrap}}.thumbnails{{display:flex;gap:10px;overflow-x:auto;scrollbar-width:thin;scrollbar-color:#777 #151617;padding:4px 2px 9px;scroll-behavior:smooth}}.thumb{{flex:0 0 82px;width:82px;height:92px;position:relative;border:1px solid #ffffff2b;background:#141617;padding:0;border-radius:5px;overflow:hidden;opacity:.62}}.thumb img{{width:100%;height:100%;object-fit:cover}}.thumb span{{position:absolute;left:0;right:0;bottom:0;background:linear-gradient(transparent,#000d);color:white;text-align:left;padding:13px 6px 5px;font-size:10px}}.thumb.selected{{border:2px solid #e2c98e;opacity:1}}button:focus-visible{{outline:3px solid #f5d591;outline-offset:3px}}@media(max-width:600px){{.gallery{{padding:17px 12px 12px;border-radius:12px}}.stage{{height:465px}}.arrow{{width:44px;height:44px;top:calc(50% - 22px)}}.prev{{left:7px}}.next{{right:7px}}.thumb{{width:66px;flex-basis:66px;height:77px}}.guide{{max-width:225px;line-height:1.5}}.name{{font-size:11px}}}}@media(prefers-reduced-motion:reduce){{.frame{{transition:none}}.thumbnails{{scroll-behavior:auto}}}}
</style></head><body><section class="gallery" aria-label="{_tr(locale, 'Портфолио', 'Portofoliu')}"><header class="top"><span class="brand">SCENA</span><span class="name">{esc(name)}</span></header><div class="stage" tabindex="0" aria-label="{_tr(locale, 'Просмотр фотографий', 'Vizualizarea fotografiilor')}">{images}<button class="arrow prev" type="button" aria-label="{previous}">‹</button><button class="arrow next" type="button" aria-label="{following}">›</button></div><div class="info"><div><p class="caption" aria-live="polite">{esc(str(frames[0]['label']))}</p><div class="guide">{guide}</div></div><span class="count">01 / {len(frames):02}</span></div><div class="thumbnails" role="group" aria-label="{choose}">{thumbs}</div></section><script>
const frames=[...document.querySelectorAll('.frame')],thumbs=[...document.querySelectorAll('.thumb')],labels={labels};let current=0,touch=null;
function show(index){{current=(index+frames.length)%frames.length;frames.forEach((el,i)=>{{el.classList.toggle('active',i===current);el.setAttribute('aria-hidden',String(i!==current))}});thumbs.forEach((el,i)=>{{el.classList.toggle('selected',i===current);el.setAttribute('aria-pressed',String(i===current))}});document.querySelector('.caption').textContent=labels[current];document.querySelector('.count').textContent=String(current+1).padStart(2,'0')+' / '+String(frames.length).padStart(2,'0');const rail=document.querySelector('.thumbnails'),thumb=thumbs[current];if(thumb.offsetLeft<rail.scrollLeft||thumb.offsetLeft+thumb.offsetWidth>rail.scrollLeft+rail.clientWidth)rail.scrollTo({{left:thumb.offsetLeft-rail.offsetLeft-rail.clientWidth/2+thumb.offsetWidth/2,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}})}}
document.querySelector('.prev').onclick=()=>show(current-1);document.querySelector('.next').onclick=()=>show(current+1);thumbs.forEach((el,i)=>el.onclick=()=>show(i));document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){{e.preventDefault();show(current+(e.key==='ArrowRight'?1:-1))}}}});const stage=document.querySelector('.stage');stage.addEventListener('touchstart',e=>{{touch={{x:e.touches[0].clientX,y:e.touches[0].clientY}}}},{{passive:true}});stage.addEventListener('touchend',e=>{{if(!touch)return;const dx=e.changedTouches[0].clientX-touch.x,dy=e.changedTouches[0].clientY-touch.y;if(Math.abs(dx)>45&&Math.abs(dx)>Math.abs(dy)*1.3)show(current+(dx<0?1:-1));touch=null}},{{passive:true}});stage.addEventListener('touchcancel',()=>touch=null,{{passive:true}});if(frames.length<2)document.querySelectorAll('.arrow').forEach(el=>el.hidden=true);
</script></body></html>'''


def render_portfolio(app_dir: Path, settings: Mapping[str, str], locale: str, kind: str) -> None:
    frames = portfolio_frames(app_dir, settings, locale, kind)
    if frames:
        st.iframe(build_portfolio_html(frames, locale, str(localized_name(settings, locale))), height=790)
        return
    st.markdown(
        '<div style="background:linear-gradient(130deg,#17191c,#343332);border-radius:20px;padding:clamp(32px,6vw,80px);color:#f8f2e7;min-height:320px">'
        '<p style="letter-spacing:.25em;font-size:12px;color:#d6bb7d">SCENA · PORTFOLIO</p>'
        f'<h2 style="color:inherit;font-family:Georgia,serif;font-weight:400">{_tr(locale, "У каждой работы — своя история", "Fiecare lucrare are povestea ei")}</h2>'
        f'<p style="max-width:480px;line-height:1.65;color:#d8d6d1">{_tr(locale, "Здесь появится подборка работ. А пока познакомьтесь с автором на её Сцене.", "Aici va apărea o selecție de lucrări. Între timp, descoperă autoarea pe Scena ei.")}</p></div>',
        unsafe_allow_html=True,
    )
    st.link_button(_tr(locale, "Открыть её Сцену", "Deschide Scena ei"), f"?page=scene&lang={locale}")


def _validate_original(data: bytes) -> tuple[str, tuple[int, int]]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Выберите фотографию размером до 20 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                kind, size = image.format, image.size
                if kind not in _FORMATS:
                    raise ValueError("Выберите фотографию JPG, PNG или WebP.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Для портфолио нужна неподвижная фотография.")
                image.verify()
                if max(size) < 600 or min(size) < 400:
                    raise ValueError("Фотография слишком маленькая: нужна длинная сторона от 600 px и короткая от 400 px. Выберите более крупный оригинал.")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Не удалось открыть фотографию. Выберите другой JPG, PNG или WebP.") from exc
    return _FORMATS[kind][0], size


def saved_originals(app_dir: Path) -> list[str]:
    """Only this editor's retained originals are offered for reuse."""
    folder = (app_dir / "media" / "portfolio").resolve()
    try:
        folder.relative_to(app_dir.resolve())
    except ValueError:
        return []
    if not folder.is_dir():
        return []
    files = [path for path in folder.iterdir() if not path.is_symlink() and _media_path(app_dir, path) is not None]
    return [path.relative_to(app_dir.resolve()).as_posix() for path in sorted(files, key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)]


def _persist_portfolio_slot(db_path: Path, prefix: str, slot: int, value: str) -> None:
    """Serialize the one-time default gallery materialization with slot updates."""
    with closing(sqlite3.connect(db_path, timeout=5)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            settings = dict(connection.execute("SELECT key, value FROM profile_settings"))
            required = {f"{prefix}_portfolio_customized", f"{prefix}_image_{slot}"}
            if not required.issubset(settings):
                raise ValueError("Не удалось сохранить портфолио. Перезапустите SCENA и повторите попытку.")
            updates = {f"{prefix}_portfolio_customized": "1"}
            if prefix == "model" and settings.get("model_portfolio_customized") != "1" and not any(settings.get(f"model_image_{i}") for i in range(1, PORTFOLIO_CAPACITY + 1)):
                updates.update({f"model_image_{i}": image for i, image in effective_slots(settings, prefix).items()})
            updates[f"{prefix}_image_{slot}"] = value
            if not set(updates).issubset(DEFAULT_SETTINGS):
                raise ValueError("Не удалось сохранить портфолио. Перезапустите SCENA и повторите попытку.")
            connection.executemany(
                "INSERT INTO profile_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                updates.items(),
            )


def update_portfolio_slot(db_path: Path, app_dir: Path, kind: str, slot: int, *, data: bytes | None = None, remove: bool = False, existing_image: str | None = None) -> str:
    """Persist the original first, then the reference; never delete replaced media."""
    prefix = _prefix(kind)
    if slot not in range(1, PORTFOLIO_CAPACITY + 1):
        raise ValueError("В портфолио доступно 12 кадров.")
    if sum((data is not None, remove, existing_image is not None)) != 1:
        raise ValueError("Выберите фотографию или удаление кадра.")
    destination: Path | None = None
    temporary: Path | None = None
    value = ""
    try:
        if existing_image is not None:
            if existing_image not in saved_originals(app_dir):
                raise ValueError("Эта фотография недоступна. Выберите другой сохранённый оригинал.")
            _validate_original((app_dir / existing_image).read_bytes())
            value = existing_image
        elif data is not None:
            extension, _ = _validate_original(data)
            media = (app_dir.resolve() / "media").resolve()
            media.relative_to(app_dir.resolve())
            folder = (media / "portfolio").resolve()
            folder.relative_to(media)
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / f"{uuid.uuid4().hex}.{extension}"
            handle, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=folder)
            temporary = Path(temporary_name)
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            value = destination.relative_to(app_dir.resolve()).as_posix()
        _persist_portfolio_slot(db_path, prefix, slot, value)
    except Exception:
        if temporary:
            temporary.unlink(missing_ok=True)
        if destination:
            destination.unlink(missing_ok=True)
        raise
    return value


def render_portfolio_editor(db_path: Path, app_dir: Path, settings: Mapping[str, str], kind: str) -> None:
    prefix = _prefix(kind)
    slots = effective_slots(settings, kind)
    key = f"portfolio_{prefix}"
    if message := st.session_state.pop(f"{key}_notice", None):
        st.success(ui(message))
    st.subheader(ui('Фотографии портфолио'))
    st.caption(f"{sum((bool(value) for value in slots.values()))}{ui(' из ')}{PORTFOLIO_CAPACITY}{ui(' кадров. Посетитель выбирает миниатюру и рассматривает фотографию целиком.')}")
    # Stable option labels keep Streamlit from resetting the selected slot after
    # a save changes its occupied/empty state.
    selected = st.selectbox(ui('Выберите кадр'), list(slots), format_func=lambda index: f"{ui('Кадр ')}{index}", key=f"{key}_slot")
    current = _media_path(app_dir, slots[selected])
    left, right = st.columns([1, 1.6], gap="large")
    with left:
        if current:
            st.image(str(current), width=280, caption=f"{ui('Кадр ')}{selected}")
        elif slots[selected]:
            st.warning(ui('Фотография недоступна. Выберите замену.'))
        else:
            st.info(ui('Место для новой фотографии.'))
    with right:
        generation = st.session_state.get(f"{key}_generation", 0)
        with st.form(f"{key}_edit_{selected}_{generation}"):
            upload = st.file_uploader(ui('Добавить или заменить фотографию'), type=["jpg", "jpeg", "png", "webp"], key=f"{key}_upload_{selected}_{generation}")
            st.caption(ui('JPG, PNG или WebP · до 20 МБ. Длинная сторона от 600 px, короткая от 400 px. Для чёткого большого кадра рекомендуем оригинал от 1600 px по длинной стороне.'))
            save = st.form_submit_button(ui('Сохранить фотографию'), type="primary")
            remove = st.form_submit_button(ui('Убрать кадр из портфолио'), disabled=not bool(slots[selected]))
        st.caption(ui('Исходная фотография сохраняется. Удаление кадра из портфолио не удаляет оригинал.'))
    originals = saved_originals(app_dir)
    reuse = False
    chosen = None
    if originals:
        with st.expander(f"{ui('Выбрать из сохранённых фотографий · ')}{len(originals)}"):
            labels = {value: f"{ui('Фотография ')}{index + 1} · {datetime.fromtimestamp((app_dir / value).stat().st_mtime).strftime('%d.%m.%Y %H:%M')}" for index, value in enumerate(originals)}
            chosen = st.selectbox(ui('Сохранённый оригинал'), originals, format_func=lambda value: labels[value], key=f"{key}_saved_original")
            st.image(str(app_dir / chosen), width=240)
            reuse = st.button(f"{ui('Использовать в кадре ')}{selected}", key=f"{key}_reuse_{selected}")
            st.caption(ui('Можно вернуть прежнюю фотографию или использовать её в другом кадре.'))
    if not save and not remove and not reuse:
        return
    if save and upload is None:
        st.warning(ui('Сначала выберите фотографию.'))
        return
    try:
        update_portfolio_slot(db_path, app_dir, kind, selected, data=upload.getvalue() if save else None, remove=remove, existing_image=chosen if reuse else None)
    except sqlite3.Error:
        st.error(ui('Не удалось сохранить изменения. Попробуйте ещё раз через несколько секунд.'))
        return
    except (OSError, ValueError) as exc:
        st.error(ui(str(exc)))
        return
    st.session_state[f"{key}_generation"] = generation + 1
    st.session_state[f"{key}_notice"] = "Кадр убран из портфолио. Оригинал сохранён." if remove else ("Сохранённая фотография возвращена в портфолио." if reuse else "Фотография сохранена в портфолио.")
    st.rerun()

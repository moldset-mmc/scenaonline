"""Local branded QR codes. The encoded address remains real and configurable."""
from __future__ import annotations

import io
import base64
import html
import json
from pathlib import Path


QR_DESTINATIONS = (
    ('scene', 'Моя Сцена', 'Scena mea', 'My Scene'),
    ('professional', 'Профессиональная страница', 'Pagina profesională', 'Professional page'),
    ('model', 'Страница Model', 'Pagina Model', 'Model page'),
    ('booking', 'Запись к мастеру', 'Programare', 'Book a service'),
)

# Blank front faces measured on the four 1024 x 1536 generated source assets.
# The data graphic stays inside the surface and clear of the model's hands.
QR_SURFACES = {
    'scene': (443, 470, 119),
    'professional': (437, 507, 163),
    'model': (429, 452, 140),
    'booking': (489, 410, 144),
}


def qr_campaign_html(settings, page: str, locale: str, app_dir: Path) -> str:
    """A genuine address on a photographed prop, plus local PNG download."""
    from model_landing import public_page_url
    from scena_i18n import localized_name, tr
    if page not in QR_SURFACES:
        raise ValueError('Unknown QR destination')
    image_path = Path(app_dir) / 'media' / 'qr-scenes' / f'{page}.png'
    photo = 'data:image/png;base64,' + base64.b64encode(image_path.read_bytes()).decode('ascii')
    address = public_page_url(settings, page)
    code = 'data:image/png;base64,' + base64.b64encode(qr_png_bytes(address)).decode('ascii')
    x, y, size = QR_SURFACES[page]
    title_row = next(row for row in QR_DESTINATIONS if row[0] == page)
    title = tr(locale, *title_row[1:])
    name = localized_name(settings, locale)
    state = json.dumps({'photo': photo, 'qr': code, 'x': x, 'y': y, 'size': size,
                        'title': title, 'name': name, 'page': page}, ensure_ascii=False).replace('</', '<\\/')
    show = tr(locale, 'Показать QR-код', 'Arată codul QR', 'Show QR code')
    download = tr(locale, 'Скачать постер PNG', 'Descarcă posterul PNG', 'Download PNG poster')
    return f'''<!doctype html><html lang="{locale}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{{box-sizing:border-box}}body{{margin:0;color:#f5f0e7;background:#080807;font-family:Arial,sans-serif}}
.poster{{position:relative;width:100%;max-width:640px;margin:auto}}.portrait{{display:block;width:100%;height:auto}}
.code{{position:absolute;left:{x/1024*100}%;top:{y/1536*100}%;width:{size/1024*100}%;height:auto}}
.brand{{position:absolute;top:3%;left:6%;font-family:Georgia,serif;font-size:clamp(20px,4.7vw,32px);letter-spacing:.13em;text-shadow:0 2px 10px #000}}
.footer{{position:absolute;bottom:2%;left:6%;right:6%;display:flex;justify-content:space-between;gap:16px;align-items:end;font-size:clamp(11px,2.5vw,16px);text-shadow:0 2px 12px #000;background:linear-gradient(transparent,#080807cc)}}
.footer span{{max-width:50%}}button{{display:block;min-height:48px;width:calc(100% - 32px);margin:16px;padding:12px;background:#eee8df;color:#1d1b18;border:1px solid #b8ab94;border-radius:4px;font-size:15px;cursor:pointer}}button:focus-visible{{outline:3px solid #b9a77d;outline-offset:3px}}
dialog{{border:0;border-radius:10px;max-width:calc(100vw - 28px);padding:16px}}dialog::backdrop{{background:#000d}}dialog img{{display:block;width:280px;max-width:100%}}.code{{cursor:pointer}}
</style><div class="poster"><img class="portrait" src="{photo}" alt="{html.escape(title)}"><img class="code" src="{code}" alt="QR — {html.escape(title)}"><div class="brand">SCENA</div><div class="footer"><span>{html.escape(name)}</span><span>{html.escape(title)}</span></div></div><button id="show">{show}</button><button id="download">{download}</button><dialog id="qr-dialog"><form method="dialog"><button>×</button></form><img src="{code}" alt="QR — {html.escape(title)}"></dialog>
<script>const state={state};document.getElementById("show").onclick=()=>document.getElementById("qr-dialog").showModal();document.querySelector(".code").onclick=()=>document.getElementById("qr-dialog").showModal();document.getElementById('download').onclick=async()=>{{
 const photo=new Image(),qr=new Image();photo.src=state.photo;qr.src=state.qr;await Promise.all([photo.decode(),qr.decode()]);
 const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=1536;const c=canvas.getContext('2d');c.drawImage(photo,0,0,1024,1536);c.imageSmoothingEnabled=false;c.drawImage(qr,state.x,state.y,state.size,state.size);
 c.fillStyle='#f5f0e7';c.shadowColor='#000';c.shadowBlur=16;c.font='46px Georgia';c.fillText('SCENA',62,89);c.font='22px Arial';c.fillText(state.name,62,1490,590);c.textAlign='right';c.fillText(state.title,962,1490,330);
 const a=document.createElement('a');a.download='SCENA-'+state.page+'.png';a.href=canvas.toDataURL('image/png');a.click();
}};</script></html>'''


def render_qr_campaigns(settings, locale: str, app_dir: Path) -> None:
    import streamlit as st
    from scena_i18n import tr
    st.subheader(tr(locale, 'Четыре приглашения в вашу Сцену', 'Patru invitații în Scena ta', 'Four invitations to your Scene'))
    st.caption(tr(locale, 'Выберите направление. QR-код на постере ведёт прямо на нужную страницу.',
                  'Alege direcția. Codul QR de pe poster deschide pagina potrivită.',
                  'Choose a destination. The QR code on the poster opens its page directly.'))
    pages = [row[0] for row in QR_DESTINATIONS]
    labels = {row[0]: tr(locale, *row[1:]) for row in QR_DESTINATIONS}
    selected = st.segmented_control(tr(locale, 'Постер', 'Poster', 'Poster'), pages,
                                    default='model', format_func=lambda item: labels[item],
                                    selection_mode='single', key='scena_qr_campaign') or 'model'
    st.iframe(qr_campaign_html(settings, selected, locale, app_dir), height=930, width=520)


def qr_png_bytes(value: str, *, logo: bool = True) -> bytes:
    """A four-module quiet zone and high correction protect the small wordmark."""
    import qrcode
    from PIL import ImageDraw, ImageFont
    if not isinstance(value, str) or not value or len(value) > 1800:
        raise ValueError('Проверьте адрес страницы для QR-кода.')
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                         box_size=10, border=4)
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(fill_color='#151413', back_color='white').convert('RGB')
    if logo:
        draw = ImageDraw.Draw(image)
        width, height = image.size
        # Only a narrow central strip is occupied; never touch finder patterns
        # or the required outer quiet zone.
        plate_w = int(width * .18)
        plate_h = max(20, int(width * .065))
        left, top = (width - plate_w) // 2, (height - plate_h) // 2
        draw.rounded_rectangle((left, top, left + plate_w, top + plate_h),
                               radius=3, fill='white')
        font_path = Path(__file__).parent / 'media/model-slider/NimbusSans-Regular.otf'
        size = max(11, int(plate_h * .64))
        font = ImageFont.truetype(str(font_path), size) if font_path.is_file() else ImageFont.load_default(size=size)
        bounds = draw.textbbox((0, 0), 'SCENA', font=font)
        draw.text((width / 2 - (bounds[2] - bounds[0]) / 2,
                   height / 2 - (bounds[3] - bounds[1]) / 2 - bounds[1]),
                  'SCENA', font=font, fill='#151413')
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()

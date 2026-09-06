"""Shared editorial presentation; native forms remain accessible and functional."""
from html import escape
import streamlit as st
from model_landing import image_uri, model_slides_from_settings


def public_model_image(app_dir, settings, preferred=1):
    """Only reuse a photograph currently approved for public Model display."""
    if settings.get('model_published', '1') != '1':
        return ''
    slides = model_slides_from_settings(settings, app_dir)
    if not slides:
        return ''
    allowed = {str(slide['slot']) for slide in slides}
    chosen = str(preferred) if str(preferred) in allowed else str(slides[0]['slot'])
    return settings.get(f'model_slide_{chosen}_image', '')


def apply_editorial_styles():
    st.markdown('''<style>
    .scena-stage-intro{display:grid;grid-template-columns:1.15fr 1fr;min-height:320px;background:#171716;color:#faf7ef;margin:1rem 0 1.6rem;overflow:hidden;border-radius:4px}
    .scena-stage-copy{padding:clamp(24px,4vw,54px);display:flex;flex-direction:column;justify-content:center}
    .scena-stage-kicker{font-size:11px;letter-spacing:.19em;text-transform:uppercase;color:#d9bc86;margin-bottom:22px}
    .scena-stage-intro h1{font-family:Georgia,serif!important;font-size:clamp(30px,3.9vw,52px)!important;font-weight:400!important;line-height:1.08!important;color:#faf7ef!important;margin:0 0 18px!important;padding:0!important}
    .scena-stage-intro p{color:#d5d2cd;max-width:520px;font-size:16px;line-height:1.6;margin:0}
    .scena-stage-image{position:relative;min-height:320px;overflow:hidden}
    .scena-stage-image img{width:100%;height:100%;position:absolute;object-fit:cover;object-position:50% 35%}
    .scena-stage-tag{display:block;border-top:1px solid #545047;margin-top:26px;padding-top:14px;font-size:12px;letter-spacing:.05em;color:#e0d2ba}
    .scena-editorial-scene{display:grid;grid-template-columns:1fr 1fr;align-items:center;border-bottom:1px solid #d9ceba;margin:1rem 0 2rem;min-height:540px}
    .scena-editorial-scene .scene-art{width:100%;height:530px;object-fit:contain;mix-blend-mode:multiply}
    .scene-identity{padding:30px 20px 35px 45px;min-width:0}
    .scene-identity .scena-personal-name{font-size:clamp(1.5rem,3.15vw,2.5125rem)!important;line-height:1.15!important;overflow-wrap:normal;text-transform:none}
    .scene-identity p{max-width:440px;line-height:1.75;color:#625c51}
    .scene-identity .scena-cta-row{justify-content:flex-start;flex-wrap:wrap;margin:24px 0 0}
    .scene-identity .scena-cta{width:auto;min-width:150px;border-radius:3px;font-family:inherit;font-size:14px}
    .scene-identity .scena-cta.primary{background:#24231e;box-shadow:none;border-color:#24231e}
    .scena-path-note{display:flex;gap:20px;justify-content:space-between;border-top:1px solid #d8ccb8;border-bottom:1px solid #d8ccb8;padding:16px 0;margin:0 0 24px;font-size:13px;color:#635c4f}
    .scena-path-note b{display:block;color:#211e19;font-size:15px;margin-bottom:4px}
    .scena-professional-title{font-size:clamp(1.5rem,2.7vw,2.6rem)!important}
    .scena-professional-shell{border-radius:4px!important;box-shadow:none!important}
    .scena-professional-kicker{font-size:.8rem!important}
    .scena-professional-portrait img{object-position:50% 30%!important}
    .scena-pro-banner{padding:16px 22px!important;border-radius:10px!important;margin-bottom:20px!important;box-shadow:none!important}
    .scena-pro-banner strong{font-size:17px!important}.scena-pro-days{font-size:14px!important}
    .scena-admin-title{font-size:clamp(28px,3vw,40px)!important;margin-top:14px!important}
    .scena-admin-lead{font-size:16px!important;margin-bottom:24px!important}
    .scena-breadcrumbs{padding:12px 18px!important;font-size:14px!important;border-radius:8px!important}
    .st-key-scena_admin_header{margin-bottom:12px!important}
    [data-testid="stForm"]{padding:22px!important;border-radius:12px!important}
    [data-testid="stForm"] [data-testid="stVerticalBlock"]{gap:.7rem}
    .scena-footer{text-align:left!important;font-size:12px!important;padding:20px 0!important}
    @media(max-width:640px){
      .scena-stage-intro{grid-template-columns:1fr;min-height:0;margin-top:.5rem}
      .scena-stage-image{grid-row:1;height:230px;min-height:0}
      .scena-stage-image img{object-position:50% var(--stage-mobile-y,28%)}
      .scena-stage-copy{padding:24px}.scena-stage-kicker{margin-bottom:12px}
      .scena-stage-intro h1{font-size:30px!important}.scena-stage-intro p{font-size:14px}
      .scena-stage-tag{margin-top:16px;padding-top:12px}
      .scena-editorial-scene{grid-template-columns:1fr;min-height:0}
      .scena-editorial-scene .scene-art{height:310px;object-fit:contain}
      .scene-identity{padding:12px 4px 30px}
      .scene-identity .scena-personal-name{font-size:clamp(1.275rem,6.75vw,1.9125rem)!important}
      .scena-path-note{gap:14px;flex-wrap:wrap}.scena-path-note>span{flex:1;min-width:110px}
      [data-testid="stForm"]{padding:16px!important}
    }
    </style>''', unsafe_allow_html=True)


def render_stage_intro(app_dir, settings, locale, *, kicker, title, text, image, tag='', mobile_y=28):
    uri = image_uri(app_dir, image)
    alt = settings.get('master_name', 'SCENA')
    visual = f'<div class="scena-stage-image"><img src="{escape(uri, quote=True)}" alt="{escape(alt, quote=True)}"></div>' if uri else ''
    layout = f' style="--stage-mobile-y:{max(0,min(100,int(mobile_y)))}%;' + ('' if uri else 'grid-template-columns:1fr;') + '"'
    tag_html = f'<span class="scena-stage-tag">{escape(tag)}</span>' if tag else ''
    st.markdown(f'<section class="scena-stage-intro"{layout}><div class="scena-stage-copy"><div class="scena-stage-kicker">{escape(kicker)}</div><h1>{escape(title)}</h1><p>{escape(text)}</p>{tag_html}</div>{visual}</section>', unsafe_allow_html=True)


def render_path_note(locale, items):
    st.markdown('<div class="scena-path-note">'+''.join(f'<span><b>{escape(title)}</b>{escape(text)}</span>' for title,text in items)+'</div>',unsafe_allow_html=True)

"""SCENA PRO: benefits, personal prompts, shop and signed renewals."""
from __future__ import annotations
import html
from datetime import datetime
from pathlib import Path
import streamlit as st
from model_landing import image_uri
from scena_cabinet import CabinetValidationError, get_pro_status, list_pro_applications, submit_pro_application
from scena_licensing import LicenseError, owner_id, redeem_code


def _tr(locale, ru, ro, en=None):
    return {'ru': ru, 'ro': ro, 'en': en or ru}.get(locale, ru)


def _escape(value):
    return html.escape(str(value), quote=True)


def _go(section, view, locale):
    st.query_params.update({'page': 'admin', 'admin': '1', 'section': section, 'view': view, 'lang': locale})
    st.rerun()


def _history_item(item, locale):
    message, reply = str(item.get('message', '')), str(item.get('decision_note', ''))
    if item.get('source') == 'pilot_preapproval':
        if message == 'Льготный PRO Trial пилотного проекта SCENA':
            message = _tr(locale, 'Пробный PRO на 60 дней', 'PRO de probă pentru 60 de zile', '60-day PRO trial')
        if reply == 'Пилотный доступ одобрен автоматически.':
            reply = _tr(locale, 'Пробный период активирован', 'Perioada de probă a fost activată', 'Trial activated')
    statuses = {'pending': _tr(locale, 'На рассмотрении', 'În curs de examinare', 'Under review'),
                'approved': _tr(locale, 'Одобрена', 'Aprobată', 'Approved'),
                'rejected': _tr(locale, 'Отклонена', 'Respinsă', 'Declined')}
    return {_tr(locale, 'Дата', 'Data', 'Date'): datetime.fromisoformat(str(item['created_at'])).strftime('%d.%m.%Y %H:%M'),
            _tr(locale, 'Статус', 'Stare', 'Status'): statuses.get(str(item['status']), str(item['status'])),
            _tr(locale, 'Ваше сообщение', 'Mesajul dvs.', 'Your message'): message,
            _tr(locale, 'Ответ SCENA', 'Răspuns SCENA', 'SCENA response'): reply or '—'}


def _render_cards(cards, label, *, soon=False):
    markup = ''.join(f'<article class="scena-pro-card scena-pro-card-{i}"><span class="scena-pro-tag">{_escape(label)}</span><h3>{_escape(title)}</h3><p>{_escape(body)}</p></article>' for i, (title, body) in enumerate(cards))
    st.markdown(f'<div class="scena-pro-grid">{markup}</div>', unsafe_allow_html=True)


def render_pro(db_path, app_dir, settings, locale='ru'):
    status = get_pro_status(db_path)
    active = status['is_active']
    applications = list_pro_applications(db_path)
    pending = next((item for item in applications if item['status'] == 'pending'), None)
    portrait = image_uri(Path(app_dir), settings.get('scene_hero_image') or 'media/scena-v13/my-scena-hero.webp')
    title = _tr(locale, 'Вас замечают.\nВас выбирают.', 'Vă remarcă.\nVă aleg.', 'Be seen.\nBe chosen.')
    lead = _tr(locale, 'Ваша история, ваши работы и ваш выбор. Создайте пространство, в котором знакомство продолжается записью, проектом или покупкой.',
               'Povestea, lucrările și alegerile dvs. Creați un spațiu în care o primă impresie continuă cu o programare, un proiect sau o achiziție.',
               'Your story, your work and your choices. Create a space where a first impression becomes a booking, a project or a purchase.')
    st.markdown('''<style>
    .scena-pro-hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,32%);overflow:hidden;background:radial-gradient(ellipse at 75% 0%,#6e58442d,transparent 65%),#211f1d;border-radius:24px;color:#fbf7ef;margin:0 0 22px;border:1px solid #3e3a34}
    .scena-pro-copy{padding:clamp(24px,4vw,50px);min-width:0}.scena-pro-kicker{font-size:13px;letter-spacing:.16em;color:#d3bc8b;margin:0 0 20px}
    .scena-pro-copy h2{font-size:clamp(30px,3.7vw,52px);line-height:1.12;font-weight:500;letter-spacing:-.025em;color:#fffaf3;margin:0 0 22px;white-space:pre-line}
    .scena-pro-copy p{font-size:17px;line-height:1.65;max-width:610px;color:#e4ddd3}.scena-pro-photo{height:100%;width:100%;object-fit:cover;object-position:center 28%;min-height:340px}
    .scena-pro-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:16px 0 28px}.scena-pro-card{position:relative;overflow:hidden;padding:24px;border:1px solid #ddd3c3;border-radius:18px;min-width:0;background:radial-gradient(ellipse at 95% 5%,#ac85482a,transparent 60%),linear-gradient(145deg,#fffdf8,#f0eade)}
    .scena-pro-card-1{background:radial-gradient(circle at 85% 0%,#b38f9126,transparent 55%),linear-gradient(155deg,#fffdf8,#f3eae6)}.scena-pro-card-2{background:radial-gradient(ellipse at 85% 15%,#74918825,transparent 65%),linear-gradient(155deg,#fffdf8,#e8eee9)}
    .scena-pro-card h3{font-size:22px;line-height:1.3;margin:12px 0;font-weight:500;color:#201d18}.scena-pro-card p{font-size:16px;line-height:1.6;color:#635c52;margin:0}.scena-pro-tag{display:inline-block;padding:5px 11px;border-radius:20px;border:1px solid #d5c6aa;color:#786342;font-size:12px;letter-spacing:.06em}
    .scena-pro-promise{border-left:3px solid #a98648;background:linear-gradient(130deg,#efe7da,#f5f0e7);padding:22px 24px;margin:20px 0 26px;border-radius:0 14px 14px 0;color:#302b23;font-size:16px;line-height:1.65}.scena-pro-promise strong{display:block;margin-bottom:8px;font-size:21px}
    @media(max-width:720px){.scena-pro-grid{grid-template-columns:1fr}.scena-pro-hero{grid-template-columns:1fr}.scena-pro-photo{height:220px;min-height:0;object-position:center 26%}.scena-pro-copy{padding:25px}.scena-pro-copy h2{font-size:34px}.scena-pro-card{padding:23px}}
    </style>''', unsafe_allow_html=True)
    photo = f'<img class="scena-pro-photo" src="{_escape(portrait)}" alt="{_escape(_tr(locale, "Ваш образ на Сцене", "Imaginea dvs. pe Scenă", "Your image on Scene"))}">' if portrait else ''
    st.markdown(f'<section class="scena-pro-hero"><div class="scena-pro-copy"><div class="scena-pro-kicker">SCENA · PRO</div><h2>{_escape(title)}</h2><p>{_escape(lead)}</p></div>{photo}</section>', unsafe_allow_html=True)
    st.subheader(_tr(locale, 'Больше возможностей для вашей Сцены', 'Mai multe posibilități pentru Scena dvs.', 'More possibilities for your Scene'))
    pro_cards = [
        (_tr(locale, 'Сценарии вашего образа', 'Scenarii pentru imaginea dvs.', 'Scenarios for your image'),
         _tr(locale, 'Глянец, клубная атмосфера, журнальный портрет или ваша идея. Подготовьте точное задание для своего ИИ, сохраняйте варианты и возвращайтесь к удачным решениям.', 'Luciu, atmosferă de club, portret editorial sau propria idee. Pregătiți instrucțiuni precise pentru AI, salvați variantele și reveniți la ideile reușite.', 'Gloss, a club atmosphere, an editorial portrait or your own idea. Prepare clear briefs for your AI, keep variations and return to your best ideas.')),
        (_tr(locale, 'Личный Shop', 'Shop personal', 'Your personal Shop'),
         _tr(locale, 'Соберите товары, которым доверяете как мастер. Фотографии, цены и ваш комментарий помогут клиенту выбрать и отправить вам заказ.', 'Reuniți produsele în care aveți încredere ca specialistă. Fotografiile, prețurile și recomandările dvs. ajută clientul să aleagă și să vă trimită o comandă.', 'Bring together the products you trust as a professional. Photos, prices and your recommendations help clients choose and send you an order.')),
        (_tr(locale, 'История, которая остаётся', 'Un istoric care rămâne', 'A history you keep'),
         _tr(locale, 'Развивайте несколько идей параллельно. Каждая сохранённая PRO-версия промпта остаётся в истории с датой; её можно прочитать, скачать и вернуть новым черновиком.', 'Dezvoltați mai multe idei în paralel. Fiecare versiune PRO salvată rămâne în istoric cu data; o puteți citi, descărca și restabili ca o ciornă nouă.', 'Develop several ideas in parallel. Each saved PRO prompt version stays in your dated history, ready to read, download or restore as a new draft.')),
    ]
    _render_cards(pro_cards, 'PRO')
    buttons = st.columns(3)
    with buttons[0]:
        if st.button(_tr(locale, 'Мои промпты', 'Prompturile mele', 'My prompts'), key='pro_open_prompts', type='primary', width='stretch'):
            _go('promotion', 'prompts', locale)
    with buttons[1]:
        if st.button(_tr(locale, 'Открыть мой Shop', 'Deschide Shop-ul meu', 'Open my Shop'), key='pro_open_shop', width='stretch'):
            _go('pages', 'shop', locale)
    with buttons[2]:
        if st.button(_tr(locale, 'Моя страница Model', 'Pagina mea Model', 'My Model page'), key='pro_open_model', width='stretch'):
            _go('pages', 'model', locale)
    st.subheader(_tr(locale, 'Ваша основа — всегда с вами', 'Baza dvs. rămâne mereu', 'Your foundation stays with you'))
    _render_cards([
        (_tr(locale, 'Первое впечатление', 'Prima impresie', 'The first impression'), _tr(locale, 'Личная Сцена, Model и портфолио рассказывают о вас через фотографии и ваши слова.', 'Scena personală, Model și portofoliul vă prezintă prin fotografii și cuvintele dvs.', 'Your personal Scene, Model and portfolio tell your story through your photos and words.')),
        (_tr(locale, 'Понятный следующий шаг', 'Un pas următor clar', 'A clear next step'), _tr(locale, 'Услуги, доступное время и приглашения в проекты связаны с вашим образом.', 'Serviciile, orele disponibile și invitațiile în proiecte sunt legate de imaginea dvs.', 'Services, available times and project invitations connect with your profile.')),
        (_tr(locale, 'Повод вернуться', 'Un motiv să revină', 'A reason to return'), _tr(locale, 'Истории, публикации и персональные QR-коды помогают делиться вашей Сценой.', 'Poveștile, publicațiile și codurile QR personale vă ajută să distribuiți Scena.', 'Stories, posts and personal QR codes make your Scene easy to share.')),
    ], _tr(locale, 'FREE и PRO', 'FREE și PRO', 'FREE and PRO'))
    promise_title = _tr(locale, 'Созданное вами остаётся вашим', 'Ceea ce creați rămâne al dvs.', 'What you create stays yours')
    promise = _tr(locale, 'После окончания PRO оформленная страница и фотографии сохраняются. Тексты, фотографии и кадрирование можно менять. История промптов остаётся для чтения и скачивания. Для новых PRO-сценариев и версий требуется продление; базовый «Глянец» остаётся доступен.', 'După expirarea PRO, pagina creată și fotografiile se păstrează. Puteți schimba textele, fotografiile și încadrarea. Istoricul prompturilor rămâne accesibil pentru citire și descărcare. Pentru scenarii și versiuni PRO noi este necesară reînnoirea; scenariul de bază «Luciu» rămâne disponibil.', 'After PRO ends, your page and photos remain. You can change text, photographs and cropping. Prompt history stays readable and downloadable. New PRO scenarios and versions require renewal; the basic Gloss scenario remains available.')
    st.markdown(f'<div class="scena-pro-promise"><strong>{_escape(promise_title)}</strong>{_escape(promise)}</div>', unsafe_allow_html=True)
    st.subheader(_tr(locale, 'Продлить PRO', 'Reînnoiește PRO', 'Renew PRO'))
    st.write(_tr(locale, 'Согласуйте срок с командой SCENA. После подтверждения оплаты вы получите персональный код. Введите его здесь — оставшиеся дни сохранятся.', 'Stabiliți perioada împreună cu echipa SCENA. După confirmarea plății primiți un cod personal. Introduceți-l aici; zilele rămase se păstrează.', 'Agree on a term with the SCENA team. Once payment is confirmed, you receive a personal code. Enter it here and keep your remaining days.'))
    try:
        profile = owner_id(db_path)
    except LicenseError:
        profile = ''
    if profile:
        with st.expander(_tr(locale, 'Мой номер профиля для продления', 'Numărul profilului meu pentru reînnoire', 'My profile number for renewal')):
            st.code(profile, language=None)
            st.caption(_tr(locale, 'Передайте этот номер команде SCENA: код будет создан именно для вашего профиля.', 'Trimiteți acest număr echipei SCENA; codul va fi creat pentru profilul dvs.', 'Give this number to SCENA so the code is issued for your profile.'))
    with st.form('pro_code_form', clear_on_submit=True):
        code = st.text_area(_tr(locale, 'Код продления', 'Cod de reînnoire', 'Renewal code'), max_chars=2048, height=90, placeholder='SCENA1.…')
        redeem = st.form_submit_button(_tr(locale, 'Активировать код', 'Activează codul', 'Activate code'), type='primary', width='stretch')
    if redeem:
        try:
            result = redeem_code(db_path, app_dir, code)
            end = datetime.fromisoformat(result['expires_at']).strftime('%d.%m.%Y')
            st.success(_tr(locale, f'Код уже применён. PRO действует до {end}.' if result['already_used'] else f'Готово. PRO продлён до {end}.', f'PRO este valabil până la {end}.', f'PRO is valid until {end}.'))
        except (LicenseError, ImportError) as exc:
            st.error(str(exc) if locale == 'ru' and isinstance(exc, LicenseError) else _tr(locale, 'Не удалось проверить код. Обратитесь в команду SCENA.', 'Codul nu a putut fi verificat. Contactați echipa SCENA.', 'The code could not be verified. Contact the SCENA team.'))
    if st.button(_tr(locale, 'Обсудить продление с SCENA', 'Discută reînnoirea cu SCENA', 'Discuss renewal with SCENA'), key='pro_contact_support', width='stretch'):
        _go('help', 'support', locale)
    if not active and not pending:
        with st.expander(_tr(locale, 'Подать заявку на PRO', 'Trimite o cerere pentru PRO', 'Apply for PRO')):
            with st.form('pro_application_form', clear_on_submit=True):
                message = st.text_area(_tr(locale, 'Расскажите о своей задаче', 'Descrieți ce doriți să faceți', 'Tell us what you want to do'), max_chars=2000, height=100, key='pro_application_message')
                submitted = st.form_submit_button(_tr(locale, 'Отправить заявку', 'Trimite cererea', 'Send application'), type='primary', width='stretch')
            if submitted:
                try:
                    submit_pro_application(db_path, message)
                    st.rerun()
                except CabinetValidationError as exc:
                    st.error(str(exc) if locale == 'ru' else _tr(locale, '', 'Verificați starea cererii dvs.', 'Check the status of your application.'))
    if pending:
        st.info(_tr(locale, 'Заявка на PRO принята. Команда SCENA уточнит условия.', 'Cererea pentru PRO a fost primită. Echipa SCENA va clarifica condițiile.', 'Your PRO application was received. SCENA will confirm the terms.'))
    if applications:
        with st.expander(_tr(locale, 'Мои заявки и ответы SCENA', 'Cererile mele și răspunsurile SCENA', 'My applications and SCENA responses')):
            st.dataframe([_history_item(item, locale) for item in applications], hide_index=True, width='stretch')

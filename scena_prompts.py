"""Personal, persistent image briefs. Generation happens in the owner's chosen AI."""
from __future__ import annotations

import html
import sqlite3
import uuid
from datetime import datetime, timezone


def tr(locale, ru, ro, en):
    return {'ru': ru, 'ro': ro, 'en': en}.get(locale, ru)


SCENARIOS = {
    'gloss': {'name': ('Глянец', 'Luciu', 'Gloss'), 'description': (
        'Чёрная зеркальная сцена, направленный свет и выразительные образы.',
        'Scenă neagră cu reflexii, lumină direcționată și imagini expresive.',
        'A reflective black stage, focused lighting and expressive looks.'), 'pro': False},
    'club': {'name': ('Ночь в городе', 'Noapte în oraș', 'City after dark'), 'description': (
        'Живая клубная атмосфера: вы в фокусе, люди и движение вокруг.',
        'Atmosferă de club: dvs. în prim-plan, oameni și mișcare în jur.',
        'A lively club setting: you in focus, people and movement around you.'), 'pro': True},
    'editorial': {'name': ('Журнальная история', 'Poveste editorială', 'Editorial story'), 'description': (
        'Характерный портрет, архитектура света и свобода журнальной съёмки.',
        'Portret cu caracter, arhitectura luminii și libertatea unei ședințe editoriale.',
        'A characterful portrait, sculpted light and an editorial composition.'), 'pro': True},
    'travel': {'name': ('Путешествие', 'Călătorie', 'Journey'), 'description': (
        'Выбранный вами город как декорация творческой истории.',
        'Orașul ales de dvs. ca decor al unei povești creative.',
        'Your chosen city as the setting for a creative story.'), 'pro': True},
    'custom': {'name': ('Моя идея', 'Ideea mea', 'My idea'), 'description': (
        'Начните с чистого листа и опишите собственный сюжет.',
        'Începeți de la o pagină albă și descrieți propria idee.',
        'Start with a blank page and describe your own concept.'), 'pro': True},
}

IDENTITY = """Use the uploaded original photographs of {name} as the identity references. The same adult person must remain recognizable: preserve her facial proportions, eye shape and colour, nose, lips, jawline, natural skin tone, hair colour and body proportions. Treat photographs as identity references and the written scene as art direction. Keep realistic skin texture and an anatomically natural pose. A creative image is not evidence of an actual event or professional achievement. Produce a single photographic image, with a small elegant label reading exactly \"SCENA\". Website names, biography, prices, navigation and buttons will be added separately as editable page elements."""
FORMAT = """Prepare one high-resolution 4:5 portrait original with generous space around the subject and a quiet dark area for page text. Keep the face, hands and main garment fully within the central safe area, so separate desktop and mobile crops can be chosen manually. If one crop cannot preserve these elements, prepare a second composition using the same original identity references. Inspect face resemblance and fingers before accepting the result."""
QR_FINISH = """The visible face of the white object must be flat, front-facing and evenly lit, with a clean square reserved for the QR. First create the photograph with that square blank. In a separate compositing step place the supplied real QR file for {target_url} on the square; preserve its modules, proportions, high contrast and full four-module quiet border. The QR is a functional graphic, never an invented decorative pattern. A small SCENA mark may be placed only where the verified QR permits it. Decode the FINAL composite with two readers and compare the result with the exact supplied URL before sharing. Add the personal URL to the accompanying caption, not as extra words baked into the photograph."""


def _template(key, scenario, names, description, scene, *, qr=False):
    return {'id': key, 'scenario': scenario, 'name': names, 'description': description,
            'scene': scene, 'qr': qr, 'pro': SCENARIOS[scenario]['pro']}


TEMPLATES = [
    _template('scene', 'gloss', ('Моя Сцена: знакомство', 'Scena mea: prezentare', 'My Scene: introduction'),
              ('Личный портрет и первое впечатление.', 'Portret personal și prima impresie.', 'A personal portrait and a first impression.'),
              'Create a warm, confident personal portrait. She wears a modern ivory jacket over a simple opaque top and turns slightly towards the viewer. A quiet champagne backdrop meets a dark theatrical edge. Soft 4300 K light from a large softbox at camera left reveals her eyes; a restrained gold reflection adds depth. Frame from the waist up at eye level with an 85 mm portrait perspective.'),
    _template('professional', 'gloss', ('Professional: мой почерк', 'Professional: stilul meu', 'Professional: my signature'),
              ('Мастер, инструменты и внимательный взгляд.', 'Specialistă, instrumente și privire atentă.', 'The professional, her tools and her attention to detail.'),
              'Create an editorial portrait of a makeup artist at her work station. She wears a tailored black suit and holds one clean makeup brush naturally at waist height. An ivory stone surface and a softly blurred mirror suggest the workspace. Show only the tools relevant to her declared profession. Use broad diffused 4500 K light from the left and a narrow warm rim light; keep her face the main point of focus. Frame at three-quarter length with a 70 mm perspective.'),
    _template('model_intro', 'gloss', ('Model: первое впечатление', 'Model: prima impresie', 'Model: first impression'),
              ('Гламурная визитка перед показом образов.', 'Carte de vizită glam înaintea imaginilor.', 'A glamorous introduction before the image show.'),
              'Photograph her standing on a reflective black stage in a contemporary opaque satin mini dress with fine shoulder straps. Her full figure is visible, relaxed shoulders and a thoughtful direct gaze. A white spotlight forms a soft pool around her feet; two narrow rear lights trace the silhouette. The background fades seamlessly into near-black, with generous quiet space to one side for her personal introduction. Use a 55 mm lens perspective and a camera near waist height.'),
    _template('gloss_1', 'gloss', ('01 · Чёрный круг', '01 · Cercul negru', '01 · Black halo'),
              ('Сдержанная сила и зеркальная сцена.', 'Forță calmă și o scenă cu reflexii.', 'Quiet strength and a reflective stage.'),
              'She wears a sculptural fully opaque black evening outfit and stands before a large polished black circular set piece. A soft silver halo outlines the circle; the black floor carries a restrained reflection. Her face remains brighter than the background. A large frontal softbox at 5000 K and two slim rear strip lights shape the scene. Frame full length at 60 mm with calm symmetry.'),
    _template('gloss_2', 'gloss', ('02 · Портрет за стеклом', '02 · Portret prin sticlă', '02 · Portrait through glass'),
              ('Близкий портрет, отражения и характер.', 'Portret apropiat, reflexii și caracter.', 'An intimate portrait, reflections and character.'),
              'Create a close portrait behind a clear upright glass panel. Fine silver reflections stay around the edges of the face, leaving both eyes and facial proportions unobstructed. She wears a high-neck black garment. The environment is near-black; a broad 4800 K key light comes from upper left and a distant vertical white strip reflects in the glass. Use an 85 mm portrait perspective, focused eyes and natural skin detail.'),
    _template('gloss_3', 'gloss', ('03 · Архитектура белого', '03 · Arhitectura albului', '03 · White architecture'),
              ('Скульптурный белый наряд на тёмном глянце.', 'Ținută albă sculpturală pe luciu întunecat.', 'A sculptural white outfit on dark gloss.'),
              'Create a full-length fashion portrait in a structured white couture suit or opaque sculptural dress. The white fabric folds have crisp, believable construction. She stands at a slight angle on a black reflective runway, one hand resting naturally at her side. A large frontal 5200 K soft source preserves skin tone; narrow overhead lights draw reflections along the floor. Use a 55 mm perspective and keep the full outfit visible.'),
    _template('gloss_4', 'gloss', ('04 · Белое в движении', '04 · Alb în mișcare', '04 · White in motion'),
              ('Лёгкая ткань и уверенный шаг.', 'Țesătură ușoară și un pas sigur.', 'Light fabric and a confident step.'),
              'Capture one graceful step in a flowing fully lined white evening dress. The fabric moves gently behind her while her face stays sharply recognizable. A black mirrored runway stretches into darkness. Use a broad 5000 K key light and a soft side light that reveals the moving folds. A 70 mm lens perspective and a fast exposure preserve her eyes and hands; only the trailing hem has a subtle sense of motion.'),
    _template('gloss_5', 'gloss', ('05 · Couture Angel', '05 · Couture Angel', '05 · Couture Angel'),
              ('Белые крылья и сценическая бахрома.', 'Aripi albe și franjuri de scenă.', 'White wings and couture fringe.'),
              'Create a full-length couture runway appearance. She wears a fully opaque warm dark-beige stage romper matched to her natural skin tone, with a high covered bodice and dense white cascading fringe reaching mid-thigh. Large white theatrical wings curve behind her. Show realistic clothing seams and complete fabric coverage. A glossy black floor reflects a little white light. A broad 5000 K frontal source keeps her face clear and two rear spotlights define the wings. Use a 60 mm perspective and a confident upright pose.'),
    _template('qr_scene', 'gloss', ('QR · Моя Сцена', 'QR · Scena mea', 'QR · My Scene'),
              ('Личная визитка с белой карточкой.', 'Prezentare personală cu un cartonaș alb.', 'A personal introduction with a white card.'),
              'Create a full-length portrait in a contemporary ivory trouser suit. She gently holds a rigid white square invitation card at waist level with its face parallel to the camera. Her fingers touch only the edges. A large amber crescent set piece rises behind her on a softly reflective dark stage. Warm diffused 4200 K light makes the face welcoming and the square evenly white. Use an 85 mm perspective. Leave the card large enough to occupy at least one fifth of the image width.', qr=True),
    _template('qr_professional', 'gloss', ('QR · Professional', 'QR · Professional', 'QR · Professional'),
              ('Профессиональная подача с белым планшетом.', 'Prezentare profesională cu o placă albă.', 'A professional portrait with a white panel.'),
              'Create a three-quarter portrait at a makeup artist station. She wears a tailored black suit over an ivory blouse, standing beside a makeup console with warm mirror lights and a large square white presentation panel facing the camera. One hand touches the panel edge; the other holds a clean makeup brush naturally. The frame has champagne highlights and charcoal shadows. Use a broad 4500 K softbox and a 70 mm lens perspective. Keep the panel evenly lit and unobstructed.', qr=True),
    _template('qr_model', 'gloss', ('QR · Model: белый куб', 'QR · Model: cubul alb', 'QR · Model: white cube'),
              ('Полный рост, лёгкое платье и глянцевый подиум.', 'Siluetă întreagă, rochie ușoară și podium lucios.', 'Full length, a light dress and a glossy runway.'),
              'Create a full-length portrait on a glossy black runway. She wears a stylish contemporary short opaque light dress with fine shoulder straps. She holds a beautiful white cube with both hands at waist level. The visible front face of the cube is parallel to the camera and large enough to occupy at least one fifth of the frame width; her hands support the sides. A white overhead spotlight and broad 5000 K key light create a theatrical entrance while keeping the cube face evenly lit. Show both feet, natural posture and a clean floor reflection with a 55 mm lens perspective.', qr=True),
    _template('qr_booking', 'gloss', ('QR · Запись к мастеру', 'QR · Programare', 'QR · Book a session'),
              ('Тёплое приглашение выбрать услугу.', 'Invitație caldă de a alege un serviciu.', 'A warm invitation to choose a service.'),
              'Create a welcoming portrait of the professional beside a modern vanity. She wears a champagne midi dress with an ivory jacket and gestures gently towards a square white card at waist height. The card faces the viewer directly and occupies at least one fifth of the frame width. An empty makeup chair, a soft stage curtain and a few clean brushes remain softly out of focus. Use warm neutral 4300 K diffused light, a calm champagne palette and a 70 mm perspective. Her expression is friendly, assured and natural.', qr=True),
    _template('club_main', 'club', ('В центре вечера', 'În centrul serii', 'The centre of the evening'),
              ('Клубная сцена с жизнью вокруг.', 'Scenă de club cu viață în jur.', 'A club scene with life around you.'),
              'Photograph her at a stylish evening venue wearing an opaque modern fashion dress. She is sharply focused in the foreground while a small diverse adult crowd appears as softly blurred silhouettes behind her. Amber practical lights and soft magenta stage reflections create depth; a broad neutral key preserves the true colour of her skin. She looks towards the camera, standing confidently among the scene rather than isolated from it. Use a 50 mm lens perspective. Treat the setting as an imagined creative scene.'),
    _template('editorial_main', 'editorial', ('Обложка с характером', 'Copertă cu caracter', 'A cover with character'),
              ('Современная журнальная композиция.', 'Compoziție editorială contemporană.', 'A contemporary editorial composition.'),
              'Create an editorial fashion portrait against a pale stone architectural wall with a charcoal sculptural plinth. She wears an opaque tailored outfit of her choice and leans lightly against the plinth, with a calm direct gaze. A single large softbox at 4800 K from camera left creates a clear shadow geometry. Use an 85 mm portrait perspective, asymmetric composition and generous quiet space. The image is a photographic base for a personal page, with editorial tension in pose and light.'),
    _template('travel_main', 'travel', ('Город как сцена', 'Orașul ca scenă', 'The city as a stage'),
              ('Творческий образ в выбранном городе.', 'Imagine creativă în orașul ales.', 'A creative look in your chosen city.'),
              'Create an imagined editorial travel portrait in {city}. Choose one recognizable but uncluttered urban setting. She wears a contemporary opaque day-to-evening outfit, standing naturally at street level with an attentive gaze. Soft late-afternoon daylight at 4300 K reveals her face; architecture and distant pedestrians remain secondary. Use a 65 mm perspective and natural street depth. This is a creative setting, not a claim that she visited the city.'),
    _template('custom_main', 'custom', ('Мой сценарий с нуля', 'Scenariul meu de la zero', 'My scenario from scratch'),
              ('Ваш сюжет, свет, одежда и композиция.', 'Ideea, lumina, ținuta și compoziția dvs.', 'Your story, light, clothing and composition.'),
              'Describe your own scene here: location, one action, clothing, physical light sources, framing, mood and the space needed for the page interface.'),
]
BY_ID = {item['id']: item for item in TEMPLATES}


class PromptError(ValueError):
    pass


def initialize_prompts(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS prompt_projects (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, scenario_id TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    connection.execute('''CREATE TABLE IF NOT EXISTS prompt_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES prompt_projects(id),
        version INTEGER NOT NULL, template_id TEXT NOT NULL, title TEXT NOT NULL,
        body TEXT NOT NULL, pro_required INTEGER NOT NULL CHECK(pro_required IN (0,1)),
        state TEXT NOT NULL CHECK(state IN ('draft','saved')), created_at TEXT NOT NULL,
        restored_from INTEGER REFERENCES prompt_versions(id), UNIQUE(project_id,version))''')


def _connect(db_path):
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def _active(connection, now=None):
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    row = connection.execute("SELECT * FROM pro_subscriptions WHERE owner_key='master'").fetchone()
    return bool(row and row['tier'] == 'PRO' and row['status'] in ('active', 'trial')
                and datetime.fromisoformat(row['expires_at']) > current)


def scenario_catalog(locale='ru'):
    idx = {'ru': 0, 'ro': 1, 'en': 2}.get(locale, 0)
    return [{'id': key, 'name': item['name'][idx], 'description': item['description'][idx], 'pro': item['pro']}
            for key, item in SCENARIOS.items()]


def template_catalog(locale='ru'):
    idx = {'ru': 0, 'ro': 1, 'en': 2}.get(locale, 0)
    return [{'id': item['id'], 'name': item['name'][idx], 'description': item['description'][idx],
             'scenario': item['scenario'], 'pro': item['pro']} for item in TEMPLATES]


def template_text(db_path, template_id, *, name='[YOUR NAME]', city='[YOUR CHOSEN CITY]', target_url='[YOUR EXACT PUBLIC URL]', now=None):
    item = BY_ID.get(template_id)
    if not item:
        raise PromptError('Промпт не найден.')
    with _connect(db_path) as connection:
        if item['pro'] and not _active(connection, now):
            raise PromptError('Для этого сценария продлите PRO. Ваши сохранённые версии доступны для чтения.')
    identity = IDENTITY.replace('{name}', str(name)[:200])
    body = item['scene'].replace('{city}', str(city)[:200])
    result = identity + '\n\n' + body + '\n\n' + FORMAT
    if item['qr']:
        result += '\n\n' + QR_FINISH.replace('{target_url}', str(target_url)[:1000])
    return result


def list_projects(db_path):
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM prompt_projects ORDER BY updated_at DESC,id')]


def list_versions(db_path, project_id=None):
    with _connect(db_path) as connection:
        query, params = 'SELECT * FROM prompt_versions', ()
        if project_id is not None:
            query, params = query + ' WHERE project_id=?', (project_id,)
        return [dict(row) for row in connection.execute(query + ' ORDER BY created_at DESC,id DESC', params)]


def save_prompt(db_path, *, template_id, title, body, project_id=None, project_title='', now=None, state='saved', restored_from=None):
    item = BY_ID.get(template_id)
    if not item or not str(title).strip() or not str(body).strip() or len(str(title)) > 160 or len(str(body)) > 16000:
        raise PromptError('Заполните название и промпт: до 160 и 16 000 символов.')
    if state not in ('draft', 'saved'):
        raise PromptError('Неверный статус версии.')
    current = now or datetime.now(timezone.utc)
    stamp = current.isoformat(timespec='microseconds')
    with _connect(db_path) as connection:
        connection.execute('BEGIN IMMEDIATE')
        pro = _active(connection, now)
        if item['pro'] and not pro:
            raise PromptError('Для новой версии этого сценария нужен PRO.')
        if not pro:
            if project_id not in (None, 'basic-gloss') or restored_from is not None:
                raise PromptError('История PRO доступна для чтения. Для новой версии продлите PRO.')
            project_id = 'basic-gloss'
        project = connection.execute('SELECT * FROM prompt_projects WHERE id=?', (project_id,)).fetchone() if project_id else None
        if project and project['scenario_id'] != item['scenario']:
            raise PromptError('Для другого сценария создайте отдельный проект.')
        if not project:
            project_id = project_id or str(uuid.uuid4())
            connection.execute('INSERT INTO prompt_projects VALUES (?,?,?,?,?)',
                               (project_id, str(project_title or title).strip()[:160], item['scenario'], stamp, stamp))
        existing = connection.execute('SELECT * FROM prompt_versions WHERE project_id=? ORDER BY version DESC LIMIT 1', (project_id,)).fetchone()
        if project_id == 'basic-gloss' and existing:
            # FREE has one editable basic version; historical PRO rows are never touched.
            if existing['pro_required'] or existing['version'] != 1:
                raise PromptError('Эта история доступна только для чтения. Продлите PRO для новой версии.')
            connection.execute('''UPDATE prompt_versions SET template_id=?,title=?,body=?,state=?,created_at=? WHERE id=?''',
                               (template_id, str(title).strip(), str(body).strip(), state, stamp, existing['id']))
            result_id = existing['id']
        else:
            version = 1 if existing is None else existing['version'] + 1
            cursor = connection.execute('''INSERT INTO prompt_versions
                (project_id,version,template_id,title,body,pro_required,state,created_at,restored_from)
                VALUES (?,?,?,?,?,?,?,?,?)''', (project_id, version, template_id, str(title).strip(), str(body).strip(),
                int(pro and project_id != 'basic-gloss'), state, stamp, restored_from))
            result_id = cursor.lastrowid
        connection.execute('UPDATE prompt_projects SET updated_at=? WHERE id=?', (stamp, project_id))
        return dict(connection.execute('SELECT * FROM prompt_versions WHERE id=?', (result_id,)).fetchone())


def restore_version(db_path, version_id, *, now=None):
    with _connect(db_path) as connection:
        row = connection.execute('SELECT * FROM prompt_versions WHERE id=?', (version_id,)).fetchone()
        if not row:
            raise PromptError('Версия не найдена.')
        source = dict(row)
    # A restored basic version gets a new PRO project, preserving the single FREE slot.
    target_project = None if source['project_id'] == 'basic-gloss' else source['project_id']
    return save_prompt(db_path, template_id=source['template_id'], title=source['title'], body=source['body'],
                       project_id=target_project, now=now, state='draft', restored_from=source['id'])


def render_prompts(db_path, app_dir, settings, locale='ru'):
    import streamlit as st
    from scena_cabinet import get_pro_status
    idx = {'ru': 0, 'ro': 1, 'en': 2}.get(locale, 0)
    active = get_pro_status(db_path)['is_active']
    st.subheader(tr(locale, 'Промпты для вашего образа', 'Prompturi pentru imaginea dvs.', 'Prompts for your image'))
    st.write(tr(locale,
        'Выберите сюжет, добавьте свои детали и перенесите задание в свой ИИ вместе с оригинальными фотографиями. Готовое изображение сохраните в SCENA.',
        'Alegeți o idee, adăugați detaliile dvs. și trimiteți instrucțiunile în propriul AI împreună cu fotografiile originale. Salvați imaginea finală în SCENA.',
        'Choose a concept, add your details and take the brief into your own AI with your original photos. Save the finished image in SCENA.'))
    st.markdown('''<style>.scena-prompt-catalog{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:14px;margin:18px 0}.scena-prompt-card{padding:22px;border:1px solid #daceba;border-radius:18px;background:radial-gradient(ellipse at 90% 10%,#ae8b4820,transparent 65%),linear-gradient(150deg,#fffdf8,#ece8df)}.scena-prompt-card h3{font-size:20px;margin:8px 0}.scena-prompt-card p{font-size:16px;line-height:1.5}.scena-prompt-card small{letter-spacing:.1em;color:#8a6937}@media(max-width:720px){.scena-prompt-catalog{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;padding-bottom:10px}.scena-prompt-card{flex:0 0 82%;box-sizing:border-box;scroll-snap-align:start}}</style>''', unsafe_allow_html=True)
    cards = []
    for entry in scenario_catalog(locale):
        label = 'PRO' if entry['pro'] else tr(locale, 'БАЗОВЫЙ', 'DE BAZĂ', 'BASIC')
        cards.append(f'<article class="scena-prompt-card"><small>{label}</small><h3>{html.escape(entry["name"])}</h3><p>{html.escape(entry["description"])}</p></article>')
    st.markdown('<div class="scena-prompt-catalog">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    if not active:
        st.caption(tr(locale, 'FREE: один базовый проект и одна изменяемая версия. История PRO остаётся для чтения и скачивания.', 'FREE: un proiect de bază și o versiune editabilă. Istoricul PRO rămâne accesibil pentru citire și descărcare.', 'FREE: one basic project and one editable version. Your PRO history remains readable and downloadable.'))
    edit_tab, history_tab = st.tabs([tr(locale, 'Подготовить промпт', 'Pregătiți un prompt', 'Prepare a prompt'), tr(locale, 'Мои версии', 'Versiunile mele', 'My versions')])
    with edit_tab:
        options = list(SCENARIOS)
        scenario = st.selectbox(tr(locale, 'Сценарий', 'Scenariu', 'Scenario'), options, format_func=lambda key: SCENARIOS[key]['name'][idx], key='prompt_scenario')
        if SCENARIOS[scenario]['pro'] and not active:
            st.write(tr(locale, 'Этот сценарий входит в PRO. Продлите подписку, чтобы создавать новые варианты.', 'Acest scenariu este inclus în PRO. Reînnoiți abonamentul pentru a crea variante noi.', 'This scenario is part of PRO. Renew to create new variations.'))
            st.link_button(tr(locale, 'Открыть PRO', 'Deschide PRO', 'Open PRO'), f'?page=admin&admin=1&section=pro&view=subscription&lang={locale}')
        else:
            templates = [item for item in TEMPLATES if item['scenario'] == scenario]
            template_id = st.selectbox(tr(locale, 'Для какой фотографии', 'Pentru ce fotografie', 'Which photograph'), [item['id'] for item in templates], format_func=lambda key: BY_ID[key]['name'][idx], key='prompt_template')
            item = BY_ID[template_id]
            st.caption(item['description'][idx])
            from scena_i18n import localized_name
            name = localized_name(settings, 'en')
            target = '[YOUR EXACT PUBLIC URL]'
            if item['qr']:
                from urllib.parse import urlparse
                from model_landing import public_page_url
                host = urlparse(settings.get('public_base_url', '')).hostname
                pages = {'qr_scene': 'scene', 'qr_professional': 'professional', 'qr_model': 'model', 'qr_booking': 'booking'}
                default_url = public_page_url(settings, pages[template_id]) if host and host not in ('localhost', '127.0.0.1', '::1') else ''
                target = st.text_input(tr(locale, 'Ссылка для этого QR', 'Link pentru acest QR', 'Link for this QR'), value=default_url,
                                       placeholder='https://…', key=f'prompt_url_{template_id}') or target
            text = template_text(db_path, template_id, name=name, city=settings.get(f'city_{locale}') or settings.get('city', '[YOUR CHOSEN CITY]'), target_url=target)
            projects = [p for p in list_projects(db_path) if p['scenario_id'] == scenario and p['id'] != 'basic-gloss']
            project_id = None
            if active:
                choices = [''] + [p['id'] for p in projects]
                labels = {p['id']: p['title'] for p in projects}
                project_id = st.selectbox(tr(locale, 'Проект', 'Proiect', 'Project'), choices, format_func=lambda key: labels.get(key, tr(locale, 'Новый проект', 'Proiect nou', 'New project')), key='prompt_project') or None
            previous = list_versions(db_path, project_id or ('basic-gloss' if not active else '__new__'))
            prior = next((v for v in previous if v['template_id'] == template_id), None)
            if prior:
                text = prior['body']
            with st.form(f'prompt_editor_{template_id}_{project_id or "new"}'):
                title = st.text_input(tr(locale, 'Название версии', 'Numele versiunii', 'Version title'), value=prior['title'] if prior else item['name'][idx], max_chars=160)
                body = st.text_area(tr(locale, 'Задание для ИИ — можно уточнить', 'Instrucțiuni pentru AI — le puteți ajusta', 'AI brief — make it your own'), value=text, height=330, max_chars=16000)
                st.caption(tr(locale, 'Загрузите в свой ИИ 2–3 чётких оригинала лица. Проверьте сходство и кадрирование. Для QR используйте настоящий файл кода и проверьте итог сканированием.', 'Încărcați în AI 2–3 fotografii originale clare ale feței. Verificați asemănarea și încadrarea. Pentru QR folosiți fișierul real și scanați rezultatul.', 'Upload 2–3 clear original face references to your AI. Review resemblance and cropping. Use the real QR file and scan the final image.'))
                submitted = st.form_submit_button(tr(locale, 'Сохранить мою версию', 'Salvează versiunea mea', 'Save my version'), type='primary', width='stretch')
            if submitted:
                try:
                    saved = save_prompt(db_path, template_id=template_id, title=title, body=body, project_id=project_id)
                    st.success(tr(locale, 'Версия сохранена.', 'Versiunea a fost salvată.', 'Version saved.'))
                    st.code(saved['body'], language=None)
                    st.download_button(tr(locale, 'Скачать промпт', 'Descarcă promptul', 'Download prompt'), saved['body'], file_name=f'SCENA-prompt-{saved["id"]}.txt', mime='text/plain')
                except PromptError as exc:
                    st.error(str(exc) if locale == 'ru' else tr(locale, '', 'Verificați câmpurile și accesul PRO.', 'Check the fields and your PRO access.'))
            else:
                st.code(body, language=None)
                st.download_button(tr(locale, 'Скачать текущий текст', 'Descarcă textul curent', 'Download current text'), body, file_name=f'SCENA-{template_id}.txt', mime='text/plain')
    with history_tab:
        versions = list_versions(db_path)
        if not versions:
            st.write(tr(locale, 'Сохраните первый промпт — он появится здесь.', 'Salvați primul prompt și acesta va apărea aici.', 'Save your first prompt to see it here.'))
        for item in versions:
            stamp = datetime.fromisoformat(item['created_at']).strftime('%d.%m.%Y %H:%M')
            state = tr(locale, 'Черновик', 'Ciornă', 'Draft') if item['state'] == 'draft' else tr(locale, 'Сохранено', 'Salvat', 'Saved')
            with st.expander(f'{item["title"]} · v{item["version"]} · {stamp} · {state}'):
                st.code(item['body'], language=None)
                st.download_button(tr(locale, 'Скачать', 'Descarcă', 'Download'), item['body'], file_name=f'SCENA-prompt-{item["id"]}.txt', mime='text/plain', key=f'prompt_download_{item["id"]}')
                if active and st.button(tr(locale, 'Вернуть эту версию', 'Restabilește această versiune', 'Restore this version'), key=f'prompt_restore_{item["id"]}'):
                    try:
                        restore_version(db_path, item['id'])
                        st.rerun()
                    except PromptError as exc:
                        st.error(str(exc))
        if versions:
            st.caption(tr(locale, 'Восстановление создаёт новый черновик. Фотографии и опубликованная страница от этого не меняются.', 'Restabilirea creează o ciornă nouă. Fotografiile și pagina publicată rămân neschimbate.', 'Restoring creates a new draft. It does not change your photographs or published page.'))

"""SCENA stage direction and mobile workspace. Platform copy, never owner prose."""
from html import escape
from pathlib import Path
import streamlit as st
from model_landing import image_uri
from scena_i18n import tr, localized_name
from scena_design import render_stage_intro, public_model_image


def apply_workspace_styles(app_dir, settings):
    portrait = image_uri(app_dir, settings.get('professional_hero_image', 'media/scena-v13/professional-portrait.webp'))
    stage = image_uri(app_dir, public_model_image(app_dir, settings, 1))
    st.markdown('''<style>
    .scena-nav{gap:8px!important;padding:14px 0!important;align-items:center}
    .scena-nav a{display:inline-flex;align-items:center;min-height:44px;padding:8px 15px!important;border:1px solid transparent;border-radius:24px;font-size:16px!important;font-weight:550!important;transition:background .18s,border-color .18s}
    .scena-nav a:hover{background:#e9dfcd;border-color:#c3aa7b}
    .scena-nav a.active{background:#eadcc2;color:#65481b!important;border-color:#b29259;box-shadow:0 4px 12px #8d6b3020}
    .scena-locale a{min-width:42px;min-height:42px;display:grid;place-items:center}
    .scena-workspace-title{text-align:center;font-size:clamp(18px,2.2vw,23px);font-weight:600;line-height:1.25;padding-bottom:2px;color:#332e26}
    .scena-owner-name{text-align:center;font-family:Georgia,serif;font-size:20px;padding:6px 0 18px;line-height:1.3}
    .scena-pro-mark{font:600 10px/1.3 sans-serif;letter-spacing:.12em;border:1px solid #b79861;border-radius:12px;padding:3px 6px;margin-left:8px;vertical-align:middle;color:#87622c}
    .st-key-scena_admin_identity_actions{margin-top:-8px;margin-bottom:0}
    .st-key-scena_admin_identity_actions [data-testid="stHorizontalBlock"]{display:flex!important;flex-direction:row!important;flex-wrap:nowrap!important}
    .st-key-scena_admin_identity_actions [data-testid="stColumn"]{min-width:0!important}
    .st-key-scena_admin_identity_actions [data-testid="stColumn"]:first-child{flex:5 1 0!important}
    .st-key-scena_admin_identity_actions [data-testid="stColumn"]:last-child{flex:1 0 68px!important}
    .scena-owner-name{font-size:16px!important;padding:6px 0 0!important}
    [data-testid="stVerticalBlockBorderWrapper"]>div{background-image:radial-gradient(ellipse at 100% 0%,#c9b0880c,transparent 80%)}
    .st-key-scena_assistant_conversation [data-testid="stChatMessage"]{background:linear-gradient(130deg,#fffcf5,#efe4d338);border:1px solid #d5c6ad66;border-radius:18px}
    [data-testid="stChatMessage"] p{font-size:17px!important}

    .st-key-scena_admin_main_nav button,.st-key-scena_admin_subnav button{min-height:48px!important;font-size:16px!important;padding:10px 16px!important;border-radius:13px!important}
    .st-key-scena_admin_main_nav button p,.st-key-scena_admin_subnav button p{font-size:16px!important;font-weight:550}
    .st-key-scena_admin_subnav{padding:12px 0!important;border-bottom:1px solid #d9cdbb}
    .st-key-scena_admin_subnav button[aria-pressed="true"],.st-key-scena_admin_main_nav button[aria-pressed="true"]{background:#dccaab!important;border-color:#9e783c!important;box-shadow:0 4px 12px #80623a25}
    .scena-breadcrumbs{font-size:16px!important;background:#fffdf8!important;border-left:3px solid #ac8a4b!important;gap:12px!important}
    .scena-breadcrumbs strong{font-weight:550}.scena-breadcrumbs strong:last-child{font-weight:700;color:#795627}
    .st-key-scena_visibility{background:linear-gradient(140deg,#faf4e9,#ece1cc)!important;padding:20px!important}
    .st-key-scena_visibility [data-testid="stCheckbox"]{min-height:48px;display:flex;align-items:center}
    .st-key-scena_visibility label p{font-size:16px!important}.st-key-scena_visibility h3{font-size:21px!important}
    [data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{font-size:16px!important}
    .scena-dashboard-card-content{position:relative;min-height:145px;padding:8px 4px 0}
    .scena-dashboard-card-content small{font-size:12px;letter-spacing:.13em;font-weight:650;color:#8c672f}
    .scena-dashboard-card-content h3{font-family:Georgia,serif;font-size:25px!important;font-weight:400!important;margin:15px 0 10px!important}
    .scena-dashboard-card-content p{font-size:16px;max-width:85%;color:#5d554a;line-height:1.55}
    [class*="st-key-scena_card_"]{position:relative;isolation:isolate;overflow:hidden;background:#fffaf1!important;box-shadow:0 8px 25px #5b43250b;transition:box-shadow .2s,transform .2s}
    [class*="st-key-scena_card_"]::before{content:'';position:absolute;inset:0;pointer-events:none;z-index:-1;background:linear-gradient(100deg,#fffaf1 10%,#fffaf1b5 60%,#fffaf133),var(--card-photo);background-size:cover;background-position:right 27%;opacity:.22}
    [class*="st-key-scena_card_"]:hover{box-shadow:0 14px 32px #5b432514}
    [class*="st-key-scena_card_"] button{background:#ffffffa8!important;min-height:46px!important}
    .scena-model-opportunities{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 28px}
    .scena-model-opportunities article{position:relative;overflow:hidden;padding:24px 20px;border:1px solid #d4c1a3;background:radial-gradient(ellipse at 100% 0%,#d8c19940,transparent 70%),#fffaf2;border-radius:18px}
    .scena-model-opportunities article::before{content:attr(data-number);position:absolute;right:12px;top:0;font:100px Georgia;color:#b3945c12;pointer-events:none}
    .scena-model-opportunities h3{font:400 25px Georgia!important;position:relative}.scena-model-opportunities p{font-size:15px;color:#675d4e;line-height:1.6;position:relative}
    .scena-path-summary{font-size:17px;line-height:1.7;padding:22px 25px;border-left:3px solid #a5864d;background:#eae0ce65;margin-bottom:26px}
    .scena-editorial-scene .scena-cta{min-height:48px!important;font-size:16px!important;padding:13px 19px!important;border-radius:8px!important}
    @media(max-width:640px){
      .st-key-scena_admin_header [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:1fr 1.4fr!important;gap:10px 6px!important}
      .st-key-scena_admin_header [data-testid="stColumn"]{width:100%!important;min-width:0!important}
      .st-key-scena_admin_header [data-testid="stColumn"]:nth-child(1){grid-column:1;grid-row:1;align-self:center}
      .st-key-scena_admin_header [data-testid="stColumn"]:nth-child(2){grid-column:1/-1;grid-row:2;padding:6px 0}
      .st-key-scena_admin_header [data-testid="stColumn"]:nth-child(3){grid-column:2;grid-row:1}
      .st-key-scena_admin_header .scena-logo-static{font-size:19px!important}
      .st-key-scena_admin_header button{padding:4px!important;min-height:40px!important}
      .st-key-scena_admin_header button p{font-size:12px!important}
      .st-key-scena_admin_main_nav{margin-top:0!important}
      .st-key-scena_admin_subnav{padding:4px 0 10px!important}

      .block-container{padding-top:.6rem!important;padding-inline:16px!important}
      .scena-top>.scena-muted{display:none}.scena-nav a{padding:8px 13px!important;font-size:15px!important}
      .scena-owner-name{font-size:19px;padding:4px 0 8px}.scena-workspace-title{font-size:18px}
      .scena-model-opportunities{grid-template-columns:1fr;gap:12px}.scena-model-opportunities article{padding:18px 20px}.scena-model-opportunities h3{margin:0 0 8px!important}
      .scena-dashboard-card-content{min-height:120px}.scena-dashboard-card-content h3{font-size:24px!important}
      .scena-dashboard-card-content p{max-width:92%;font-size:16px}.scena-stage-intro p{font-size:16px!important}
      .st-key-scena_admin_main_nav button,.st-key-scena_admin_subnav button{min-height:48px!important;padding:10px 13px!important}
      .scena-breadcrumbs{overflow-x:auto;white-space:nowrap}.scena-path-summary{padding:18px;font-size:16px}
    }
    </style>''', unsafe_allow_html=True)
    # Validated local/data image URIs only; no editable CSS enters the page.
    if portrait or stage:
        st.markdown('<style>[class*="st-key-scena_card_"]{--card-photo:url("'+escape(portrait,quote=True)+'")}.st-key-scena_card_pages,.st-key-scena_card_prompts,.st-key-scena_card_promotion{--card-photo:url("'+escape(stage or portrait,quote=True)+'")}</style>',unsafe_allow_html=True)


def render_dashboard(db_path, app_dir, settings, locale, on_route):
    from scena_core import list_requests, list_services
    requests = list_requests(db_path)
    pending = sum(item['status'] == 'Ожидает подтверждения' for item in requests)
    cards = [
        ('requests',tr(locale,'ЗАПИСИ','PROGRAMĂRI','BOOKINGS'),tr(locale,'Кто ждёт ответа','Cine așteaptă răspuns','Who is waiting'),tr(locale,f'Новых обращений: {pending}. Подтвердите встречу или обсудите детали.',f'Cereri în așteptare: {pending}. Confirmați întâlnirea sau discutați detaliile.',f'{pending} requests awaiting your reply. Confirm a meeting or discuss the details.'),'work','requests'),
        ('services',tr(locale,'УСЛУГИ','SERVICII','SERVICES'),tr(locale,'Что вы предлагаете','Ce oferiți','What you offer'),tr(locale,'Услуги и курсы, понятные группы, цены и описания.','Servicii și cursuri, categorii clare, prețuri și descrieri.','Services and courses, clear groups, prices and descriptions.'),'work','services'),
        ('schedule',tr(locale,'ВАШЕ ВРЕМЯ','TIMPUL DVS.','YOUR TIME'),tr(locale,'Откройте удобные часы','Alegeți orele potrivite','Set your available hours'),tr(locale,'График, перерывы и выходные. Клиенты видят только свободное время.','Program, pauze și zile libere. Clienții văd doar orele disponibile.','Work hours, breaks and days off. Clients see available times.'),'work','schedule'),
        ('shop','MARKET',tr(locale,'Рекомендуйте лучшее','Recomandați ce apreciați','Recommend your favourites'),tr(locale,'Ваш магазин: товары, личные рекомендации и заказы.','Magazinul dvs.: produse, recomandări personale și comenzi.','Your shop: products, personal recommendations and orders.'),'pages','shop'),
        ('pages',tr(locale,'ВАША СЦЕНА','SCENA DVS.','YOUR STAGE'),tr(locale,'Покажите себя','Prezentați-vă','Introduce yourself'),tr(locale,'История, профессия и Model. Каждая страница — ваша сторона.','Poveste, profesie și Model. Fiecare pagină vă arată o altă latură.','Your story, profession and Model. Each page shows a different side.'),'pages','scene'),
        ('promotion',tr(locale,'ПРОДВИЖЕНИЕ','PROMOVARE','PROMOTION'),tr(locale,'Дайте повод вернуться','Oferiți un motiv să revină','Give people a reason to return'),tr(locale,'Публикации, фотообразы, промпты и QR-визитки.','Publicații, imagini, prompturi și cărți de vizită QR.','Posts, image ideas, prompts and QR cards.'),'promotion','posts'),
        ('help','SCENA',tr(locale,'Обсудим вашу идею','Discutăm ideea dvs.','Let’s explore your idea'),tr(locale,'Личный ассистент и прямая связь с командой.','Asistent personal și legătură directă cu echipa.','A personal assistant and a direct line to the team.'),'help','assistant'),
        ('pro','PRO',tr(locale,'Больше ваших возможностей','Mai multe posibilități','More possibilities for you'),tr(locale,'Сценарии Model, профессиональные промпты и личный Market.','Scenarii Model, prompturi profesionale și Market personal.','Model scenarios, professional prompts and your personal Market.'),'pro','subscription'),
    ]
    for offset in range(0,len(cards),2):
        for col,card in zip(st.columns(2),cards[offset:offset+2]):
            key,kicker,title,body,section,view=card
            with col,st.container(border=True,key='scena_card_'+key):
                st.markdown(f'<div class="scena-dashboard-card-content"><small>{escape(kicker)}</small><h3>{escape(title)}</h3><p>{escape(body)}</p></div>',unsafe_allow_html=True)
                if st.button(tr(locale,'Открыть','Deschide','Open')+' →',key='admin_home_open_'+key,width='stretch'):
                    on_route(locale,section,view); st.rerun()
    st.subheader(tr(locale,'Быстрый просмотр','Previzualizare','Quick preview'))
    for col,(label,page) in zip(st.columns(4),[(tr(locale,'Моя Сцена','Scena mea','My Scene'),'scene'),('Professional','professional'),('Model','model'),('Market','shop')]):
        col.link_button(label,f'?page={page}&lang={locale}',width='stretch')


def render_model_path(app_dir,settings,locale):
    render_stage_intro(app_dir,settings,locale,
        kicker='SCENA · A PLACE FOR YOU',
        title=tr(locale,'Ваша красота.\nВаша Сцена.','Frumusețea dvs.\nScena dvs.','Your beauty.\nYour Scene.'),
        text=tr(locale,'Попробуйте себя в новом образе — на съёмке, в beauty-проекте или на подиуме. Начать можно без опыта. Здесь есть место взрослым женщинам разного возраста и внешности.','Încercați o imagine nouă — la o ședință foto, într-un proiect beauty sau pe podium. Puteți începe fără experiență. Aici este loc pentru femei adulte de vârste și înfățișări diferite.','Try a new look — in a photo shoot, a beauty project or on the runway. You can begin without experience. Adult women of different ages and appearances are welcome.'),
        image=public_model_image(app_dir,settings,1),mobile_y=8,
        tag=tr(locale,'Знакомство начинается с вас','Cunoașterea începe cu dvs.','It begins with you'))
    cards=[
        (tr(locale,'Beauty-модель','Model beauty','Beauty model'),tr(locale,'Макияж, волосы, брови, ресницы. Мастерам, салонам и ученикам нужны модели для практики, обучения и новых образов.','Machiaj, păr, sprâncene, gene. Specialiștii, saloanele și cursanții caută modele pentru practică, instruire și imagini noi.','Makeup, hair, brows and lashes. Specialists, salons and students need models for practice, classes and new looks.')),
        (tr(locale,'Фотомодель','Fotomodel','Photo model'),tr(locale,'Портреты, beauty-съёмки и истории брендов. Важны не только параметры, но и характер, выразительность, ваш собственный образ.','Portrete, ședințe beauty și povești de brand. Contează și caracterul, expresivitatea și imaginea dvs. proprie.','Portraits, beauty shoots and brand stories. Character, expression and your individual look matter too.')),
        (tr(locale,'Показы и проекты','Prezentări și proiecte','Shows and projects'),tr(locale,'Fashion, творческие съёмки и коммерческие приглашения. Формат, требования и оплата обсуждаются до вашего согласия.','Fashion, ședințe creative și invitații comerciale. Formatul, cerințele și plata se discută înainte de acceptare.','Fashion, creative shoots and commercial invitations. Format, requirements and payment are agreed before you accept.')),
    ]
    st.markdown('<div class="scena-model-opportunities">'+''.join(f'<article data-number="0{i}"><h3>{escape(title)}</h3><p>{escape(body)}</p></article>'for i,(title,body)in enumerate(cards,1))+'</div>',unsafe_allow_html=True)
    st.markdown('<div class="scena-path-summary">'+escape(tr(locale,'На SCENA вы представляете себя и получаете возможность откликаться на приглашения. Например, прийти моделью на обучение и получить макияж или укладку бесплатно — если это указано в условиях. Другие проекты могут оплачиваться. Сначала вы узнаёте все детали, затем сами решаете.','Pe SCENA vă prezentați și puteți răspunde invitațiilor. De exemplu, să fiți model la un curs și să primiți machiaj sau coafură gratuit — dacă acest lucru este inclus în condiții. Alte proiecte pot fi plătite. Mai întâi aflați detaliile, apoi decideți.','On SCENA you introduce yourself and can respond to invitations. You might model at a class and receive free makeup or hairstyling, when this is included in the terms. Other projects may be paid. You learn all the details first, then decide.'))+'</div>',unsafe_allow_html=True)
    st.subheader(tr(locale,'Давайте познакомимся','Să ne cunoaștem','Let’s get to know you'))
    st.caption(tr(locale,'Оставьте контакты и пару слов о себе. Команда обсудит с вами оформление модельной страницы и следующий шаг.','Lăsați datele de contact și câteva cuvinte despre dvs. Echipa va discuta crearea paginii Model și următorul pas.','Leave your contact details and a few words about yourself. The team will discuss your Model page and the next step with you.'))

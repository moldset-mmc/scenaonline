"""Compact native cabinet composition; no changes to records or access rules."""
from html import escape
from urllib.parse import urlencode

from scena_i18n import tr, translate_literaltext
from scena_ui import st


def cabinet_url(locale, section, view, **extra):
    return '/?' + urlencode(dict(page='admin', lang=locale, section=section, view=view, **extra))


def navigation(locale, section, view, sections, views, owner):
    def label(value):
        return escape(translate_literaltext(locale, value))

    def link(title, destination, active=False):
        return '<a data-cabinet-nav href="'+escape(destination, quote=True)+'"'+(' aria-current="page"' if active else '')+'>'+title+'</a>'

    choices = ''.join(link(label(title), cabinet_url(locale, key, next(iter(views.get(key, {})), '')), key == section)
                      for key, title in sections.items() if key != 'home')
    languages = ''.join(link(lang.upper(), cabinet_url(lang, section, view), lang == locale) for lang in ('ru','ro','en'))
    with st.container(key='scena_cabinet_chrome'):
        st.markdown('<header class="scena-cabinet-header">'+link('SCENA', '/?'+urlencode(dict(page='scene',lang=locale)))+
            '<span class="scena-cabinet-current">'+label(sections[section])+'</span>'+
            '<details class="scena-cabinet-menu"><summary>'+escape(tr(locale,'Меню','Meniu','Menu'))+'</summary>'+
            '<div class="scena-cabinet-panel"><p>'+escape(owner)+'</p><nav aria-label="'+escape(tr(locale,'Разделы кабинета','Secțiuni','Workspace sections'))+'">'+choices+'</nav>'+
            '<nav class="scena-cabinet-languages" aria-label="'+escape(tr(locale,'Язык','Limbă','Language'))+'">'+languages+'</nav>'+
            link(label('Выйти'), '/auth/logout')+'</div></details></header>', unsafe_allow_html=True)
    if len(views.get(section, {})) > 1:
        st.markdown('<nav class="scena-cabinet-tabs" aria-label="'+escape(tr(locale,'Подразделы','Subsecțiuni','Views'))+'">'+
            ''.join(link(label(title), cabinet_url(locale,section,key), key == view) for key,title in views[section].items())+'</nav>', unsafe_allow_html=True)


def request_list(rows, locale, request_types):
    from scena_shop import dial_number
    from scena_service_telegram import request_path
    from datetime import datetime
    label = lambda value: translate_literaltext(locale, value)
    options = {'all': tr(locale,'Все заявки','Toate cererile','All requests'), **{key:label(value) for key,value in request_types.items()}}
    selected = st.selectbox(tr(locale,'Показать','Afișează','Show'), list(options), format_func=options.get, key='mobile_request_filter')
    visible = [row for row in rows if selected == 'all' or row['request_type'] == selected]
    if not visible:
        st.info(tr(locale,'Заявок пока нет.','Încă nu există cereri.','No requests yet.'))
        return
    st.caption(tr(locale,f'Заявок: {len(visible)}',f'Cereri: {len(visible)}',f'Requests: {len(visible)}'))
    with st.container(key='scena_request_list'):
        for row in visible:
            day = row['preferred_date']
            try:
                day = datetime.fromisoformat(day).strftime('%d.%m.%Y') if day else ''
            except ValueError:
                pass
            when = ' · '.join(value for value in (day, row['preferred_time']) if value)
            number = dial_number(row['phone'])
            phone = '<a href="tel:'+escape(number,quote=True)+'">'+escape(row['phone'])+'</a>' if number else escape(row['phone'])
            st.markdown('<article class="scena-inbox-card"><a class="scena-inbox-open" data-cabinet-nav href="'+escape(request_path(row['id'],locale),quote=True)+'">'+
                '<strong>'+escape(row['name'])+'</strong><span>'+escape(row['service'] or label(request_types[row['request_type']]))+'</span>'+
                ('<span>'+escape(when)+'</span>' if when else '')+'</a><div class="scena-inbox-footer">'+phone+'<span class="scena-status">'+escape(label(row['status']))+'</span></div></article>',unsafe_allow_html=True)


def dashboard(db_path, locale):
    from scena_core import list_requests
    from scena_shop import list_orders
    requests = list_requests(db_path)
    pending = sum(row['status'] in ('Новая','Ожидает подтверждения') for row in requests)
    new_orders = sum(row['status'] == 'new' for row in list_orders(db_path))
    actions = [
        (tr(locale,'Заявки','Cereri','Requests'), str(pending), 'work','requests', {}),
        (tr(locale,'Заказы','Comenzi','Orders'), str(new_orders), 'pages','shop', {'orders':'1'}),
        (tr(locale,'График','Program','Schedule'), tr(locale,'Рабочие часы','Ore de lucru','Work hours'),'work','schedule', {}),
        (tr(locale,'Услуги','Servicii','Services'), tr(locale,'Цены и запись','Prețuri și programări','Prices and booking'),'work','services', {}),
    ]
    st.markdown('<div class="scena-work-actions">'+''.join('<a data-cabinet-nav href="'+escape(cabinet_url(locale,section,view,**params),quote=True)+'"><strong>'+escape(title)+'</strong><span>'+escape(detail)+'</span></a>' for title,detail,section,view,params in actions)+'</div>',unsafe_allow_html=True)
    waiting = [row for row in requests if row['status'] in ('Новая','Ожидает подтверждения')][:5]
    if waiting:
        st.subheader(tr(locale,'Ждут ответа','Așteaptă un răspuns','Waiting for your reply'))
        from scena_service_telegram import request_path
        for row in waiting:
            st.markdown('<a class="scena-work-waiting" data-cabinet-nav href="'+escape(request_path(row['id'],locale),quote=True)+'"><strong>'+escape(row['name'])+'</strong><span>'+escape(row['service'])+'</span><span>→</span></a>',unsafe_allow_html=True)
    with st.expander(tr(locale,'Мои страницы','Paginile mele','My pages')):
        st.markdown('<nav class="scena-cabinet-tabs">'+''.join('<a href="/?'+urlencode(dict(page=page,lang=locale))+'">'+escape(title)+'</a>' for title,page in [(tr(locale,'Моя Сцена','Scena mea','My Scene'),'scene'),('Professional','professional'),('Model','model'),('Market','shop')])+'</nav>',unsafe_allow_html=True)

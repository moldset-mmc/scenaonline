"""Owner search settings and a factual readiness view, without external writes."""
from html import escape
import re
from urllib.parse import urlencode

from scena_i18n import tr
from scena_seo import public_base, public_catalog, _read_public
from scena_ui import st


def verification_token(value):
    value = str(value or '').strip()
    if value and not re.fullmatch(r'[A-Za-z0-9_-]{8,256}', value):
        raise ValueError('Invalid verification token')
    return value


def translation_gaps(settings, db_path):
    """Missing explicit owner copy, not a claim that an existing fallback is wrong."""
    groups = [
        ('scene', 'bio', 'Моя Сцена', 'Scena mea', 'My Scene'),
        ('professional', 'beauty_desc', 'Professional', 'Professional', 'Professional'),
        ('model', 'model_intro_text', 'Знакомство', 'Prezentare', 'Introduction'),
        ('shop', 'shop_description', 'shopping', 'shopping', 'shopping'),
    ]
    result = []
    for view, key, ru, ro, en in groups:
        for lang in ('ru', 'ro', 'en'):
            value = settings.get(key + '_' + lang, '') or (settings.get(key, '') if lang == 'ru' else '')
            if not str(value).strip():
                result.append((view, (ru, ro, en), lang))
    for service in _read_public(db_path)['services']:
        for lang in ('ru', 'ro', 'en'):
            if not str(service.get('name_' + lang) or (service.get('name') if lang == 'ru' else '') or '').strip():
                result.append(('services', (service.get('name', ''),)*3, lang))
    return result


def render_search_settings(db_path, settings, locale):
    def t(ru, ro, en):
        return tr(locale, ru, ro, en)
    base = public_base(settings)
    catalog = public_catalog(settings, db_path=db_path)
    st.write(t('Здесь показана готовность страниц к поиску. Фактическое появление в Google и Bing проверяется в кабинетах поисковых систем.',
               'Aici vedeți pregătirea paginilor pentru căutare. Prezența efectivă în Google și Bing se verifică în conturile motoarelor de căutare.',
               'This shows whether pages are prepared for search. Check actual Google and Bing indexing in their webmaster accounts.'))
    st.subheader(t('Публичные страницы', 'Pagini publice', 'Public pages'))
    st.caption(t(f'В карте сайта: {len(catalog)} языковых адресов.', f'În sitemap: {len(catalog)} de adrese lingvistice.', f'Sitemap: {len(catalog)} language URLs.'))
    if base:
        st.markdown('<nav class="scena-cabinet-tabs">' + ''.join(
            '<a href="' + escape(base + '/' + path, quote=True) + '" target="_blank" rel="noopener">' + label + '</a>'
            for path, label in [('sitemap.xml', 'Sitemap'), ('robots.txt', 'robots.txt'), ('llms.txt', 'llms.txt')]) + '</nav>', unsafe_allow_html=True)
    else:
        st.warning(t('Укажите публичный HTTPS-адрес ниже, чтобы сформировать поисковые ссылки.',
                     'Introduceți mai jos adresa publică HTTPS pentru a genera linkurile de căutare.',
                     'Enter the public HTTPS address below to generate search links.'))
    for area, label in [('scene', t('Моя Сцена', 'Scena mea', 'My Scene')), ('professional', 'Professional'), ('model', 'Model')]:
        prefix = 'profile' if area == 'scene' else area
        published = settings.get(prefix + '_published', '1') == '1'
        enabled = settings.get(prefix + '_indexed', '1') == '1'
        state = t('Не опубликовано', 'Nepublicată', 'Unpublished') if not published else t('Индексация разрешена', 'Indexare permisă', 'Indexing allowed') if enabled else t('Индексация выключена', 'Indexare dezactivată', 'Indexing disabled')
        url = '/?' + urlencode(dict(page='admin', lang=locale, section='pages', view=area))
        st.markdown('<p><a data-cabinet-nav href="' + escape(url, quote=True) + '">' + escape(label) + '</a> · ' + escape(state) + '</p>', unsafe_allow_html=True)
    with st.expander(t('Адрес и подтверждение владения', 'Adresă și verificarea proprietății', 'Address and ownership verification')):
        with st.form('search_settings'):
            address = st.text_input(t('Публичный HTTPS-адрес', 'Adresa publică HTTPS', 'Public HTTPS address'), value=settings.get('public_base_url', ''))
            google = st.text_input('Google Search Console · verification', value=settings.get('seo_google_verification', ''))
            bing = st.text_input('Bing Webmaster Tools · verification', value=settings.get('seo_bing_verification', ''))
            yandex = st.text_input('Яндекс Вебмастер · verification', value=settings.get('seo_yandex_verification', ''))
            counter = st.text_input('Яндекс Метрика · ID', value=settings.get('seo_yandex_counter', ''))
            st.caption(t('Вставьте только значение content из метатега подтверждения. Это не пароль. Пустое поле удаляет подтверждение.',
                         'Introduceți doar valoarea content din metaeticheta de verificare. Nu este o parolă. Un câmp gol elimină verificarea.',
                         'Enter only the content value from the verification meta tag. This is not a password. An empty field removes verification.'))
            submitted = st.form_submit_button(t('Сохранить настройки поиска', 'Salvează setările de căutare', 'Save search settings'), type='primary')
        if submitted:
            validated_base = public_base({'public_base_url': address})
            try:
                values = {'seo_google_verification': verification_token(google), 'seo_bing_verification': verification_token(bing)}
                values['seo_yandex_verification'] = verification_token(yandex)
                if counter.strip() and not re.fullmatch(r'[1-9][0-9]{4,12}', counter.strip()):
                    raise ValueError('Invalid analytics counter')
                values['seo_yandex_counter'] = counter.strip()
                if not validated_base:
                    raise ValueError('Invalid public address')
            except ValueError:
                st.error(t('Проверьте HTTPS-адрес и значения подтверждения: вставляйте код без HTML-тега.',
                           'Verificați adresa HTTPS și valorile de verificare: introduceți codul fără eticheta HTML.',
                           'Check the HTTPS address and verification values: enter the code without the HTML tag.'))
            else:
                from scena_core import save_settings
                from scena_app import rerun_admin_with_success
                save_settings(db_path, {**values, 'public_base_url': validated_base})
                rerun_admin_with_success(t('Настройки поиска сохранены.', 'Setările de căutare au fost salvate.', 'Search settings saved.'))
        st.link_button('Google Search Console', 'https://search.google.com/search-console')
        st.link_button('Bing Webmaster Tools', 'https://www.bing.com/webmasters/')
    gaps = translation_gaps(settings, db_path)
    with st.expander(t(f'Тексты для проверки · {len(gaps)}', f'Texte de verificat · {len(gaps)}', f'Texts to review · {len(gaps)}')):
        st.write(t('Проверьте смысл текстов на каждом языке. Если отдельный перевод не заполнен, страница может использовать исходный текст или готовый перевод шаблона.',
                   'Verificați sensul textelor în fiecare limbă. Dacă traducerea separată lipsește, pagina poate folosi textul original sau traducerea șablonului.',
                   'Review the meaning in every language. Without a separate translation, a page may use the original text or a template translation.'))
        for view, labels, lang in gaps:
            url = '/?' + urlencode(dict(page='admin', lang=locale, section='work' if view == 'services' else 'pages', view=view))
            st.markdown('<p><a data-cabinet-nav href="' + escape(url, quote=True) + '">' + escape(tr(locale, *labels)) + ' · ' + lang.upper() + '</a></p>', unsafe_allow_html=True)
    with st.expander(t('Город и поиск с ИИ', 'Oraș și căutare cu AI', 'City and AI search')):
        st.write(t('Город, имя и контакты задаются в «Моя Сцена». Названия, описания и цены услуг — в «Работа → Услуги». Используйте реальные данные и одинаковый смысл RU/RO/EN.',
                   'Orașul, numele și contactele se stabilesc în „Scena mea”. Denumirile, descrierile și prețurile serviciilor — în „Activitate → Servicii”. Folosiți date reale și același sens în RU/RO/EN.',
                   'Set your city, name and contacts in My Scene. Edit service names, descriptions and prices in Work → Services. Use real facts and equivalent RU/RO/EN copy.'))
        st.caption(t('llms.txt — дополнительный список публичных страниц. Он не гарантирует индексацию или упоминание в ответах ИИ.',
                     'llms.txt este o listă suplimentară de pagini publice. Nu garantează indexarea sau menționarea în răspunsurile AI.',
                     'llms.txt is an optional public page directory. It does not guarantee indexing or mentions in AI answers.'))

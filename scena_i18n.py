"""Explicit RU/RO/EN presentation helpers for the local SCENA product.

Only platform-authored literals in this catalogue are translated. User text is
never sent to a translation service or rewritten. Localized content is stored
in separate fields; the legacy value remains the fallback on old databases.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

LOCALES = ("ru", "ro", "en")
LANGUAGE_LABELS = {"ru": "RU", "ro": "RO", "en": "EN"}
CANONICAL_NAME_RU = "Мария Бараночникова"
CANONICAL_NAME_LATIN = "Maria Baranochnikova"

# Empty overrides are deliberate: migration must not put Maria's name or story
# into a customer's already customized profile.
DEFAULT_I18N_SETTINGS = {
    "master_name_ru": "", "master_name_ro": "", "master_name_en": "",
    "location_ru": "", "location_ro": "", "location_en": "",
    "bio_en": "", "beauty_title_en": "", "beauty_desc_en": "",
    "model_title_en": "", "model_desc_en": "",
    "booking_cta_ru": "Записаться на макияж",
    "booking_cta_ro": "Programare la machiaj",
    "booking_cta_en": "Book makeup",
    "booking_title_ru": "Время для себя",
    "booking_title_ro": "Timp pentru tine",
    "booking_title_en": "Time for you",
    "booking_description_ru": "Особенный повод или желание увидеть себя по-новому. Выберите образ и удобное время — начнём с вашей идеи.",
    "booking_description_ro": "O ocazie specială sau dorința de a te vedea altfel. Alege serviciul și ora potrivită — pornim de la ideea ta.",
    "booking_description_en": "A special occasion, or a wish to see yourself differently. Choose your look and a convenient time — we begin with your idea.",
}
for _index in range(1, 6):
    DEFAULT_I18N_SETTINGS[f"model_slide_{_index}_manifesto_en"] = ""
    DEFAULT_I18N_SETTINGS[f"model_slide_{_index}_alt_en"] = ""


def normalize_locale(locale: object, fallback: str = "ru") -> str:
    candidate = str(locale or "").lower().strip().replace("_", "-").split("-", 1)[0]
    return candidate if candidate in LOCALES else (fallback if fallback in LOCALES else "ru")


def localized_name(settings: Mapping[str, object], locale: str = "ru") -> str:
    """Use the owner's chosen spelling; never transliterate custom identities."""
    lang = normalize_locale(locale)
    explicit = str(settings.get(f"master_name_{lang}") or "").strip()
    if explicit:
        return explicit
    legacy = str(settings.get("master_name") or "").strip()
    if legacy:
        return CANONICAL_NAME_LATIN if lang != "ru" and legacy == CANONICAL_NAME_RU else legacy
    for fallback in ("ru", "ro", "en"):
        value = str(settings.get(f"master_name_{fallback}") or "").strip()
        if value:
            return value
    return "SCENA"


# Russian key -> (Romanian, English). The dictionary is populated below from
# explicit, reviewed copy. Exact lookup makes this safe for platform literals.
CATALOG: dict[str, tuple[str, str]] = {}


def register_copy(ru: str, ro: str, en: str) -> None:
    CATALOG[ru] = (ro, en)


def tr(locale: str, ru: str, ro: str, en: str | None = None) -> str:
    lang = normalize_locale(locale)
    if lang == "ru":
        return ru
    if lang == "ro":
        return ro
    if en is not None:
        return en
    translated = translate_literaltext("en", ru)
    return translated


def translate_literaltext(locale: str, value: object) -> object:
    """Translate an exact UI literal, preserving nonstrings and unknown values.

    Use at explicit rendering call sites, never as a global Streamlit patch.
    No fuzzy replacement of arbitrary names, customer messages or markup.
    """
    if not isinstance(value, str):
        return value
    lang = normalize_locale(locale)
    if lang == "ru" or not value:
        return value
    pair = CATALOG.get(value)
    if pair:
        return pair[0 if lang == "ro" else 1]
    # Renderers often add whitespace or bold markup around known short labels.
    stripped = value.strip()
    pair = CATALOG.get(stripped)
    if pair:
        return value[:len(value) - len(value.lstrip())] + pair[0 if lang == "ro" else 1] + value[len(value.rstrip()):]
    if stripped.startswith("**") and stripped.endswith("**") and stripped[2:-2] in CATALOG:
        return "**" + str(translate_literaltext(lang, stripped[2:-2])) + "**"
    return value


def content_text(settings: Mapping[str, object], base_key: str, locale: str, fallback: str = "") -> str:
    """Read owner-entered translation, then a safe legacy content fallback.

    Supports both ``bio/bio_ro`` and ``model_slide_1_alt_ru/_ro/_en``.
    Known starter copy has catalogue translations; unknown owner copy is kept.
    """
    lang = normalize_locale(locale)
    base = re.sub(r"_(ru|ro|en)$", "", base_key)
    explicit = str(settings.get(f"{base}_{lang}") or "").strip()
    if explicit:
        return explicit
    source = str(settings.get(base) or settings.get(f"{base}_ru") or "").strip()
    if source:
        return str(translate_literaltext(lang, source))
    for alternative in ("ro", "en"):
        value = str(settings.get(f"{base}_{alternative}") or "").strip()
        if value:
            return value
    return fallback


def service_name(item: Mapping[str, object], locale: str) -> str:
    return content_text(item, "name", locale)


def service_description(item: Mapping[str, object], locale: str) -> str:
    return content_text(item, "description", locale)


def _load_rows(rows: str) -> None:
    for line in rows.splitlines():
        if not line.strip():
            continue
        ru, ro, en = line.split("|", 2)
        register_copy(ru.replace("\\n", "\n"), ro.replace("\\n", "\n"), en.replace("\\n", "\n"))


# Existing public and cabinet copy, with an English version.
CATALOG.update(
{'Подготовьте вариант для соцсети. Материал и история отправок остаются в SCENA.': ('Pregătiți o '
                                                                                    'variantă pentru '
                                                                                    'rețeaua socială. '
                                                                                    'Materialul și '
                                                                                    'istoricul rămân în '
                                                                                    'SCENA.',
                                                                                    'Prepare a version '
                                                                                    'for social media. '
                                                                                    'Your content and '
                                                                                    'publishing history '
                                                                                    'stay in SCENA.'),
 'Площадка': ('Platformă', 'Platform'),
 'Язык публикации': ('Limba publicației', 'Post language'),
 'Фото и подпись для страницы Facebook или профессионального аккаунта Instagram.': ('O fotografie JPEG '
                                                                                    'și o descriere. '
                                                                                    'Facebook — pagină; '
                                                                                    'Instagram — cont '
                                                                                    'profesional. '
                                                                                    'Caruselele, '
                                                                                    'Stories și '
                                                                                    'videoclipurile nu '
                                                                                    'sunt incluse în '
                                                                                    'această versiune.',
                                                                                    'A photo and '
                                                                                    'caption for a '
                                                                                    'Facebook Page or '
                                                                                    'professional '
                                                                                    'Instagram '
                                                                                    'account.'),
 'Площадка подтвердила публикацию.': ('Platforma a confirmat publicarea.',
                                      'The platform confirmed publication.'),
 'Открыть публикацию': ('Deschide publicația', 'Open post'),
 'Для соцсетей используется опубликованная версия. Новые правки сначала опубликуйте в своей Сцене.': ('Pentru '
                                                                                                      'rețele '
                                                                                                      'folosim '
                                                                                                      'versiunea '
                                                                                                      'publicată. '
                                                                                                      'Publicați '
                                                                                                      'mai '
                                                                                                      'întâi '
                                                                                                      'modificările '
                                                                                                      'în '
                                                                                                      'Scena '
                                                                                                      'dvs.',
                                                                                                      'Social '
                                                                                                      'sharing '
                                                                                                      'uses '
                                                                                                      'your '
                                                                                                      'published '
                                                                                                      'version. '
                                                                                                      'Publish '
                                                                                                      'your '
                                                                                                      'latest '
                                                                                                      'changes '
                                                                                                      'on '
                                                                                                      'your '
                                                                                                      'Scene '
                                                                                                      'first.'),
 'Подпись для соцсети': ('Descriere pentru rețea', 'Social media caption'),
 'Сохранить вариант': ('Salvează varianta', 'Save version'),
 'Скачайте готовые фото и подпись. Для прямой отправки ваша Сцена должна быть доступна в интернете.': ('Descărcați '
                                                                                                       'fotografia '
                                                                                                       'și '
                                                                                                       'descrierea '
                                                                                                       'pregătite. '
                                                                                                       'Pentru '
                                                                                                       'trimitere '
                                                                                                       'directă, '
                                                                                                       'Scena '
                                                                                                       'dvs. '
                                                                                                       'trebuie '
                                                                                                       'să '
                                                                                                       'fie '
                                                                                                       'accesibilă '
                                                                                                       'pe '
                                                                                                       'internet.',
                                                                                                       'Download '
                                                                                                       'your '
                                                                                                       'photo '
                                                                                                       'and '
                                                                                                       'caption. '
                                                                                                       'Direct '
                                                                                                       'publishing '
                                                                                                       'requires '
                                                                                                       'your '
                                                                                                       'Scene '
                                                                                                       'to '
                                                                                                       'be '
                                                                                                       'online.'),
 'Скачать фото и подпись': ('Descarcă fotografia și descrierea', 'Download photo and caption'),
 'Чтобы отправлять прямо из SCENA, обратитесь в поддержку для подключения своего аккаунта.': ('Pentru a '
                                                                                              'trimite '
                                                                                              'direct '
                                                                                              'din '
                                                                                              'SCENA, '
                                                                                              'contactați '
                                                                                              'echipa '
                                                                                              'pentru '
                                                                                              'conectarea '
                                                                                              'contului '
                                                                                              'dvs.',
                                                                                              'Contact '
                                                                                              'support '
                                                                                              'to '
                                                                                              'connect '
                                                                                              'your '
                                                                                              'account '
                                                                                              'for '
                                                                                              'direct '
                                                                                              'publishing '
                                                                                              'from '
                                                                                              'SCENA.'),
 'Проверить аккаунт': ('Verifică contul', 'Verify account'),
 'Посмотреть перед отправкой': ('Previzualizează trimiterea', 'Preview before sending'),
 'Instagram обрабатывает фотографию. Продолжите отправку примерно через минуту.': ('Instagram '
                                                                                   'procesează '
                                                                                   'fotografia. '
                                                                                   'Continuați '
                                                                                   'trimiterea peste '
                                                                                   'aproximativ un '
                                                                                   'minut.',
                                                                                   'Instagram is '
                                                                                   'processing the '
                                                                                   'photo. Continue '
                                                                                   'publishing in about '
                                                                                   'a minute.'),
 'Фотография для отправки': ('Fotografia pentru trimitere', 'Photo to publish'),
 'Если фотография уже размещена в интернете, укажите её ссылку. Иначе скачайте готовый материал ниже.': ('Completați '
                                                                                                         'după '
                                                                                                         'găzduirea '
                                                                                                         'JPEG-ului '
                                                                                                         'pregătit '
                                                                                                         'pe '
                                                                                                         'un '
                                                                                                         'site '
                                                                                                         'public. '
                                                                                                         'Fișierul '
                                                                                                         'local '
                                                                                                         'nu '
                                                                                                         'este '
                                                                                                         'accesibil '
                                                                                                         'Facebook '
                                                                                                         'și '
                                                                                                         'Instagram.',
                                                                                                         'If '
                                                                                                         'your '
                                                                                                         'photo '
                                                                                                         'is '
                                                                                                         'already '
                                                                                                         'online, '
                                                                                                         'enter '
                                                                                                         'its '
                                                                                                         'link. '
                                                                                                         'Otherwise, '
                                                                                                         'download '
                                                                                                         'the '
                                                                                                         'prepared '
                                                                                                         'content '
                                                                                                         'below.'),
 'Ссылка на фотографию SCENA': ('Link HTTPS către JPEG cu eticheta SCENA', 'Link to the SCENA photo'),
 'Вариант сохранён. Он останется после закрытия кабинета.': ('Varianta a fost salvată și rămâne '
                                                             'disponibilă după închiderea cabinetului.',
                                                             'Version saved. It remains available after '
                                                             'you close your workspace.'),
 'Адрес сайта или язык изменился. Сохраните вариант заново перед отправкой.': ('Adresa site-ului sau '
                                                                               'limba s-a schimbat. '
                                                                               'Salvați din nou '
                                                                               'varianta înainte de '
                                                                               'trimitere.',
                                                                               'The website address or '
                                                                               'language has changed. '
                                                                               'Save the version again '
                                                                               'before publishing.'),
 'Для скачивания загрузите фотографию через редактор публикации — отдельная версия с лейблом SCENA появится автоматически.': ('Pentru '
                                                                                                                              'descărcare, '
                                                                                                                              'încărcați '
                                                                                                                              'fotografia '
                                                                                                                              'în '
                                                                                                                              'editor; '
                                                                                                                              'o '
                                                                                                                              'versiune '
                                                                                                                              'separată '
                                                                                                                              'cu '
                                                                                                                              'eticheta '
                                                                                                                              'SCENA '
                                                                                                                              'va '
                                                                                                                              'fi '
                                                                                                                              'creată '
                                                                                                                              'automat.',
                                                                                                                              'Upload '
                                                                                                                              'a '
                                                                                                                              'photo '
                                                                                                                              'in '
                                                                                                                              'the '
                                                                                                                              'post '
                                                                                                                              'editor '
                                                                                                                              'to '
                                                                                                                              'download '
                                                                                                                              'a '
                                                                                                                              'separate '
                                                                                                                              'version '
                                                                                                                              'with '
                                                                                                                              'the '
                                                                                                                              'SCENA '
                                                                                                                              'label.'),
 'Аккаунт для отправки: ': ('Cont pentru trimitere: ', 'Publishing account: '),
 'Перед отправкой сначала опубликуйте материал в своей Сцене.': ('Înainte de trimitere, publicați '
                                                                 'materialul în Scena dvs.',
                                                                 'Publish the content on your Scene '
                                                                 'before sharing it.'),
 'Проверка отправки': ('Verificarea trimiterii', 'Publishing check'),
 'Проверить ссылку на мою публикацию': ('Verifică linkul spre publicația mea', 'Check my post link'),
 'История отправок': ('Istoricul trimiterilor', 'Publishing history'),
 'Результат пока неизвестен. Проверьте свою страницу; автоматического повтора не будет.': ('Rezultatul '
                                                                                           'nu este '
                                                                                           'încă '
                                                                                           'cunoscut. '
                                                                                           'Verificați '
                                                                                           'pagina; nu '
                                                                                           'repetăm '
                                                                                           'automat '
                                                                                           'trimiterea.',
                                                                                           'The result '
                                                                                           'is not '
                                                                                           'confirmed '
                                                                                           'yet. Check '
                                                                                           'your page; '
                                                                                           'we will not '
                                                                                           'retry '
                                                                                           'automatically.'),
 'Аккаунт подтверждён: ': ('Cont confirmat: ', 'Verified account: '),
 'Не удалось подтвердить аккаунт. Обратитесь к оператору SCENA.': ('Contul nu a putut fi confirmat. '
                                                                   'Contactați operatorul SCENA.',
                                                                   'We could not verify this account. '
                                                                   'Contact the SCENA team.'),
 'Перед отправкой подтвердите, что подключён именно ваш аккаунт.': ('Înainte de trimitere, verificați '
                                                                    'că este conectat contul dvs.',
                                                                    'Confirm that your own account is '
                                                                    'connected before publishing.'),
 'Проверила фото, подпись, актуальность цены и аккаунт. Разрешаю публикацию.': ('Am verificat '
                                                                                'fotografia, '
                                                                                'descrierea, prețul '
                                                                                'actual și contul. '
                                                                                'Autorizez publicarea.',
                                                                                'I checked the photo, '
                                                                                'caption, current price '
                                                                                'and account. I '
                                                                                'authorize '
                                                                                'publication.'),
 'Отправка не подтверждена. Проверьте подключение и материал.': ('Trimiterea nu a fost confirmată. '
                                                                 'Verificați conexiunea și materialul.',
                                                                 'Publication was not confirmed. Check '
                                                                 'the connection and content.'),
 'Отправить в ': ('Trimite pe ', 'Publish on '),
 'Открыть': ('Deschide', 'Open'),
 'Продолжить отправку': ('Continuă trimiterea', 'Continue publishing'),
 'Проверить результат без повтора': ('Verifică rezultatul fără retrimitere',
                                     'Check result without publishing again'),
 'Предыдущая фотография': ('Fotografia precedentă', 'Previous photo'),
 'Следующая фотография': ('Fotografia următoare', 'Next photo'),
 'Выбрать фотографию': ('Alege fotografia', 'Choose photo'),
 'Выберите кадр. Посмотрите ближе.': ('Alege un cadru. Privește mai aproape.',
                                      'Choose a frame. Take a closer look.'),
 'Открыть её Сцену': ('Deschide Scena ei', 'Open her Scene'),
 'Портфолио': ('Portofoliu', 'Portfolio'),
 'Просмотр фотографий': ('Vizualizarea fotografiilor', 'Photo viewer'),
 'У каждой работы — своя история': ('Fiecare lucrare are povestea ei', 'Every work has a story'),
 'Здесь появится подборка работ. А пока познакомьтесь с автором на её Сцене.': ('Aici va apărea o '
                                                                                'selecție de lucrări. '
                                                                                'Între timp, descoperă '
                                                                                'autoarea pe Scena ei.',
                                                                                'A selection of work '
                                                                                'will appear here. '
                                                                                'Meanwhile, meet the '
                                                                                'creator on her Scene.'),
 'Цена по договорённости': ('Preț la înțelegere', 'Price on request'),
 'Проверьте вашу запись': ('Verificați programarea', 'Review your booking'),
 'Изменить услугу, дату или время': ('Schimbă serviciul, data sau ora', 'Change service, date or time'),
 '1. Выберите услугу': ('1. Alegeți serviciul', '1. Choose a service'),
 '2. Выберите день и время': ('2. Alegeți ziua și ora', '2. Choose a day and time'),
 'Точка рядом с датой — есть свободное время.': ('Un punct lângă dată indică ore disponibile.',
                                                 'A dot next to a date means appointments are '
                                                 'available.'),
 'В этот день нет свободного времени. Выберите другую дату или посмотрите ближайшую доступную.': ('În '
                                                                                                  'această '
                                                                                                  'zi '
                                                                                                  'nu '
                                                                                                  'sunt '
                                                                                                  'ore '
                                                                                                  'disponibile. '
                                                                                                  'Alegeți '
                                                                                                  'altă '
                                                                                                  'dată '
                                                                                                  'sau '
                                                                                                  'vedeți '
                                                                                                  'următoarea '
                                                                                                  'dată '
                                                                                                  'disponibilă.',
                                                                                                  'No '
                                                                                                  'appointments '
                                                                                                  'are '
                                                                                                  'available '
                                                                                                  'on '
                                                                                                  'this '
                                                                                                  'day. '
                                                                                                  'Choose '
                                                                                                  'another '
                                                                                                  'date '
                                                                                                  'or '
                                                                                                  'view '
                                                                                                  'the '
                                                                                                  'next '
                                                                                                  'available '
                                                                                                  'one.'),
 'До обеда': ('Înainte de prânz', 'Morning'),
 'После обеда': ('După prânz', 'Afternoon'),
 'Условия услуги изменились. Пожалуйста, проверьте их перед записью.': ('Condițiile serviciului s-au '
                                                                        'schimbat. Verificați-le '
                                                                        'înainte de programare.',
                                                                        'The service details have '
                                                                        'changed. Please review them '
                                                                        'before booking.'),
 'Вернуться к выбору': ('Înapoi la selecție', 'Back to selection'),
 'После заявки мастер свяжется с вами и подтвердит запись.': ('După cerere, specialistul vă va contacta '
                                                              'și va confirma programarea.',
                                                              'After your request, the specialist will '
                                                              'contact you to confirm your booking.'),
 'Как с вами связаться?': ('Cum vă contactăm?', 'How can we reach you?'),
 'Ваше имя *': ('Numele dvs. *', 'Your name *'),
 'Телефон +373 *': ('Telefon +373 *', 'Phone +373 *'),
 'Согласие на обработку контактных данных *': ('Acord pentru prelucrarea datelor de contact *',
                                               'I consent to the processing of my contact details *'),
 'Отправить заявку': ('Trimite cererea', 'Send request'),
 'Запись на встречу': ('Programare', 'Book an appointment'),
 'Запись сейчас недоступна. Загляните немного позже.': ('Programarea nu este disponibilă acum. Reveniți '
                                                        'puțin mai târziu.',
                                                        'Booking is unavailable right now. Please '
                                                        'return later.'),
 'Ваша запись': ('Programarea dvs.', 'Your booking'),
 'Познакомьтесь чуть ближе': ('Cunoaște-ne mai bine', 'Get to know her'),
 'Образы, вдохновение и история человека, которому вы доверяете свою красоту.': ('Imagini, inspirație '
                                                                                 'și povestea persoanei '
                                                                                 'căreia îi '
                                                                                 'încredințați '
                                                                                 'frumusețea.',
                                                                                 'Discover the looks, '
                                                                                 'inspiration and story '
                                                                                 'of the person you '
                                                                                 'trust with your '
                                                                                 'beauty.'),
 'Выбрать ещё одну услугу': ('Alege încă un serviciu', 'Choose another service'),
 'Новые даты и услуги появятся здесь. А пока познакомьтесь с работами мастера.': ('Servicii și date noi '
                                                                                  'vor apărea aici. '
                                                                                  'Până atunci, '
                                                                                  'descoperiți '
                                                                                  'lucrările '
                                                                                  'specialistului.',
                                                                                  'New dates and '
                                                                                  'services will appear '
                                                                                  'here. Meanwhile, '
                                                                                  'explore the '
                                                                                  "specialist's work."),
 'Посмотреть портфолио': ('Vezi portofoliul', 'View portfolio'),
 'Выберите услугу, чтобы увидеть её стоимость и свободные даты.': ('Alegeți serviciul pentru a vedea '
                                                                   'prețul și datele disponibile.',
                                                                   'Choose a service to see its price '
                                                                   'and available dates.'),
 'Продолжить': ('Continuă', 'Continue'),
 'Перейти к ближайшей дате': ('Alege următoarea dată', 'Go to the next available date'),
 'На более поздние даты свободного времени пока нет. Можно выбрать другой день в календаре.': ('Nu sunt '
                                                                                               'ore '
                                                                                               'disponibile '
                                                                                               'la date '
                                                                                               'ulterioare. '
                                                                                               'Puteți '
                                                                                               'alege '
                                                                                               'altă zi '
                                                                                               'în '
                                                                                               'calendar.',
                                                                                               'There '
                                                                                               'are no '
                                                                                               'later '
                                                                                               'appointments '
                                                                                               'available. '
                                                                                               'You can '
                                                                                               'choose '
                                                                                               'another '
                                                                                               'day in '
                                                                                               'the '
                                                                                               'calendar.'),
 'Добавить email или пожелание': ('Adaugă email sau o preferință', 'Add email or a preference'),
 'Email — необязательно': ('Email — opțional', 'Email — optional'),
 'Комментарий — необязательно': ('Comentariu — opțional', 'Comment — optional'),
 'ВАШ ОБРАЗ · ВАШ МОМЕНТ': ('IMAGINEA TA · MOMENTUL TĂU', 'YOUR LOOK · YOUR MOMENT'),
 'Время для себя': ('Timp pentru tine', 'Time for yourself'),
 'Особенный повод или желание увидеть себя по-новому. Выберите образ и удобное время — начнём с вашей идеи.': ('O '
                                                                                                               'ocazie '
                                                                                                               'specială '
                                                                                                               'sau '
                                                                                                               'dorința '
                                                                                                               'de '
                                                                                                               'a '
                                                                                                               'te '
                                                                                                               'vedea '
                                                                                                               'altfel. '
                                                                                                               'Alege '
                                                                                                               'serviciul '
                                                                                                               'și '
                                                                                                               'ora '
                                                                                                               'potrivită '
                                                                                                               '— '
                                                                                                               'pornim '
                                                                                                               'de '
                                                                                                               'la '
                                                                                                               'ideea '
                                                                                                               'ta.',
                                                                                                               'A '
                                                                                                               'special '
                                                                                                               'occasion, '
                                                                                                               'or '
                                                                                                               'a '
                                                                                                               'wish '
                                                                                                               'to '
                                                                                                               'see '
                                                                                                               'yourself '
                                                                                                               'differently. '
                                                                                                               'Choose '
                                                                                                               'your '
                                                                                                               'look '
                                                                                                               'and '
                                                                                                               'a '
                                                                                                               'convenient '
                                                                                                               'time '
                                                                                                               '— '
                                                                                                               'we '
                                                                                                               'begin '
                                                                                                               'with '
                                                                                                               'your '
                                                                                                               'idea.'),
 'мин.': ('min.', 'min.'),
 'Предыдущий месяц': ('Luna precedentă', 'Previous month'),
 'Следующий месяц': ('Luna următoare', 'Next month'),
 'есть свободное время': ('ore disponibile', 'appointments available'),
 'свободного времени нет': ('nu sunt ore disponibile', 'no appointments available'),
 'Ближайшая доступная дата: ': ('Următoarea dată disponibilă: ', 'Next available date: '),
 'Свободного времени нет': ('Nu sunt ore disponibile', 'No appointments available'),
 'Публикации': ('Publicații', 'Posts'),
 'Все публикации': ('Toate publicațiile', 'All posts'),
 'Создайте публикацию, проверьте её и покажите на своей Сцене.': ('Creează o publicație, verific-o și '
                                                                  'afișeaz-o pe Scena ta.',
                                                                  'Create a post, review it and share '
                                                                  'it on your Scene.'),
 '＋ Новая публикация': ('＋ Publicație nouă', '＋ New post'),
 '1. Материал': ('1. Conținut', '1. Content'),
 '2. Проверка и публикация': ('2. Verificare și publicare', '2. Review and publish'),
 'Предпросмотр показывает последнюю сохранённую версию.': ('Previzualizarea arată ultima versiune '
                                                           'salvată.',
                                                           'The preview shows the latest saved '
                                                           'version.'),
 'Открыть предпросмотр': ('Deschide previzualizarea', 'Open preview'),
 'Эта страница пока не опубликована.': ('Această pagină nu este încă publicată.',
                                        'This page is not published yet.'),
 'Здесь появятся фотографии, истории и новые проекты.': ('Aici vor apărea fotografii, istorii și '
                                                         'proiecte noi.',
                                                         'Photos, stories and new projects will appear '
                                                         'here.'),
 'История': ('Poveste', 'Story'),
 'Публикация недоступна': ('Publicația nu este disponibilă', 'Post unavailable'),
 'Публикация в архиве': ('Publicația este arhivată', 'Archived post'),
 'Автор сняла эту публикацию с показа.': ('Autoarea a retras această publicație.',
                                          'The author has archived this post.'),
 'Фотография': ('Fotografie', 'Photo'),
 'JPG, PNG или WEBP до 20 МБ. Короткая сторона — от 600 px, рекомендуем от 1080 px. Оригинал сохраняется; для поста создаётся отдельная копия с лейблом SCENA без обрезки.': ('JPG, '
                                                                                                                                                                              'PNG '
                                                                                                                                                                              'sau '
                                                                                                                                                                              'WEBP, '
                                                                                                                                                                              'maximum '
                                                                                                                                                                              '20 '
                                                                                                                                                                              'MB. '
                                                                                                                                                                              'Latura '
                                                                                                                                                                              'scurtă: '
                                                                                                                                                                              'minimum '
                                                                                                                                                                              '600 '
                                                                                                                                                                              'px, '
                                                                                                                                                                              'recomandat '
                                                                                                                                                                              '1080 '
                                                                                                                                                                              'px. '
                                                                                                                                                                              'Originalul '
                                                                                                                                                                              'se '
                                                                                                                                                                              'păstrează; '
                                                                                                                                                                              'copia '
                                                                                                                                                                              'pentru '
                                                                                                                                                                              'postare '
                                                                                                                                                                              'primește '
                                                                                                                                                                              'eticheta '
                                                                                                                                                                              'SCENA, '
                                                                                                                                                                              'fără '
                                                                                                                                                                              'decupare.',
                                                                                                                                                                              'JPG, '
                                                                                                                                                                              'PNG '
                                                                                                                                                                              'or '
                                                                                                                                                                              'WEBP '
                                                                                                                                                                              'up '
                                                                                                                                                                              'to '
                                                                                                                                                                              '20 '
                                                                                                                                                                              'MB. '
                                                                                                                                                                              'Short '
                                                                                                                                                                              'side: '
                                                                                                                                                                              'at '
                                                                                                                                                                              'least '
                                                                                                                                                                              '600 '
                                                                                                                                                                              'px, '
                                                                                                                                                                              'preferably '
                                                                                                                                                                              '1080 '
                                                                                                                                                                              'px. '
                                                                                                                                                                              'Your '
                                                                                                                                                                              'original '
                                                                                                                                                                              'is '
                                                                                                                                                                              'preserved; '
                                                                                                                                                                              'a '
                                                                                                                                                                              'separate '
                                                                                                                                                                              'SCENA-labeled '
                                                                                                                                                                              'copy '
                                                                                                                                                                              'is '
                                                                                                                                                                              'created '
                                                                                                                                                                              'without '
                                                                                                                                                                              'cropping.'),
 'Тип публикации': ('Tipul publicației', 'Post type'),
 'Цена — обязательна для предложения': ('Preț — obligatoriu pentru ofertă',
                                        'Price — required for an offer'),
 'Я проверила тексты RU и RO': ('Am verificat textele RU și RO', 'I checked the RU and RO texts'),
 'Сохранить черновик': ('Salvează ciorna', 'Save draft'),
 'Проверила сохранённый материал. Опубликовать на выбранных страницах.': ('Am verificat conținutul '
                                                                          'salvat. Publică pe paginile '
                                                                          'selectate.',
                                                                          'I reviewed the saved '
                                                                          'content. Publish on the '
                                                                          'selected pages.'),
 'Опубликовать на Сцене': ('Publică pe Scena mea', 'Publish on my Scene'),
 'Посмотреть опубликованную версию': ('Vezi versiunea publicată', 'View published version'),
 'История и архив': ('Istoric și arhivă', 'History and archive'),
 'Сохранённая версия': ('Versiune salvată', 'Saved version'),
 'Вернуть эту версию в черновик': ('Restabilește această versiune în ciornă',
                                   'Restore this version as a draft'),
 '3. Подготовить для Facebook или Instagram': ('3. Pregătește pentru Facebook sau Instagram',
                                               '3. Prepare for Facebook or Instagram'),
 'Подробнее': ('Detalii', 'Learn more'),
 'Публикация': ('Publicație', 'Post'),
 'Нажмите «Новая публикация», чтобы начать.': ('Apasă «Publicație nouă» pentru a începe.',
                                               'Select “New post” to begin.'),
 'Этот черновик изменён в другом окне. Скопируйте свои несохранённые правки и загрузите свежую версию.': ('Ciorna '
                                                                                                          'a '
                                                                                                          'fost '
                                                                                                          'modificată '
                                                                                                          'în '
                                                                                                          'altă '
                                                                                                          'fereastră. '
                                                                                                          'Copiază '
                                                                                                          'modificările '
                                                                                                          'nesalvate '
                                                                                                          'și '
                                                                                                          'încarcă '
                                                                                                          'versiunea '
                                                                                                          'nouă.',
                                                                                                          'This '
                                                                                                          'draft '
                                                                                                          'was '
                                                                                                          'changed '
                                                                                                          'in '
                                                                                                          'another '
                                                                                                          'window. '
                                                                                                          'Copy '
                                                                                                          'your '
                                                                                                          'unsaved '
                                                                                                          'changes '
                                                                                                          'and '
                                                                                                          'load '
                                                                                                          'the '
                                                                                                          'latest '
                                                                                                          'version.'),
 'Загрузить свежую версию': ('Încarcă versiunea nouă', 'Load latest version'),
 'Кнопка и места показа': ('Buton și pagini de afișare', 'Button and display pages'),
 'Адрес для кнопки «Подробнее»': ('Adresa butonului «Detalii»', 'Link for the “Learn more” button'),
 'Сохранённая фотография и оригинал': ('Fotografia salvată și originalul', 'Saved photo and original'),
 'Версия восстановлена в новый черновик. Проверьте её перед публикацией.': ('Versiunea a fost '
                                                                            'restabilită într-o ciornă '
                                                                            'nouă. Verific-o înainte de '
                                                                            'publicare.',
                                                                            'The version was restored '
                                                                            'as a new draft. Review it '
                                                                            'before publishing.'),
 'Снять фото и текст с показа, оставить страницу архива с моим именем': ('Retrage fotografia și textul, '
                                                                         'păstrează pagina arhivei cu '
                                                                         'numele meu',
                                                                         'Hide the photo and text, '
                                                                         'keeping an archive page with '
                                                                         'my name'),
 'Убрать в архив': ('Arhivează', 'Archive'),
 'Черновик сохранён. Теперь можно проверить и опубликовать.': ('Ciorna a fost salvată. Acum o poți '
                                                               'verifica și publica.',
                                                               'Draft saved. You can now review and '
                                                               'publish it.'),
 'Эта фотография пока не подходит для публикации. Загрузите замену.': ('Această fotografie nu este '
                                                                       'potrivită pentru publicare. '
                                                                       'Încarcă un înlocuitor.',
                                                                       'This photo is not suitable for '
                                                                       'publication yet. Upload a '
                                                                       'replacement.'),
 'Скачать оригинал': ('Descarcă originalul', 'Download original'),
 'Публикация появилась на Сцене.': ('Publicația a apărut pe Scena ta.',
                                    'Your post is now on your Scene.'),
 'Публикация в архиве. По прежней ссылке видны только имя и переход на Сцену.': ('Publicația este '
                                                                                 'arhivată. Linkul '
                                                                                 'arată doar numele și '
                                                                                 'accesul la Scena ta.',
                                                                                 'Post archived. Its '
                                                                                 'existing link shows '
                                                                                 'only your name and a '
                                                                                 'link to your Scene.'),
 'Карусель публикаций': ('Carusel de publicații', 'Post carousel'),
 'Предложение с ценой': ('Ofertă cu preț', 'Offer with a price'),
 'Следующая публикация': ('Publicația următoare', 'Next post'),
 'Предыдущая публикация': ('Publicația precedentă', 'Previous post'),
 'Истории и предложения': ('Povești și oferte', 'Stories and offers'),
 'Вас замечают.\nВас выбирают.': ('Vă remarcă.\nVă aleg.', 'Be seen.\nBe chosen.'),
 'Соберите образ, работы и предложения в одном личном пространстве. Пусть знакомство с вами продолжается записью, проектом или новым контактом.': ('Reuniți '
                                                                                                                                                   'imaginea, '
                                                                                                                                                   'lucrările '
                                                                                                                                                   'și '
                                                                                                                                                   'ofertele '
                                                                                                                                                   'într-un '
                                                                                                                                                   'singur '
                                                                                                                                                   'spațiu '
                                                                                                                                                   'personal. '
                                                                                                                                                   'O '
                                                                                                                                                   'primă '
                                                                                                                                                   'impresie '
                                                                                                                                                   'poate '
                                                                                                                                                   'deveni '
                                                                                                                                                   'o '
                                                                                                                                                   'programare, '
                                                                                                                                                   'un '
                                                                                                                                                   'proiect '
                                                                                                                                                   'sau '
                                                                                                                                                   'un '
                                                                                                                                                   'contact '
                                                                                                                                                   'nou.',
                                                                                                                                                   'Bring '
                                                                                                                                                   'your '
                                                                                                                                                   'image, '
                                                                                                                                                   'work '
                                                                                                                                                   'and '
                                                                                                                                                   'offers '
                                                                                                                                                   'together '
                                                                                                                                                   'in '
                                                                                                                                                   'one '
                                                                                                                                                   'personal '
                                                                                                                                                   'space. '
                                                                                                                                                   'Let '
                                                                                                                                                   'a '
                                                                                                                                                   'first '
                                                                                                                                                   'impression '
                                                                                                                                                   'lead '
                                                                                                                                                   'to '
                                                                                                                                                   'a '
                                                                                                                                                   'booking, '
                                                                                                                                                   'a '
                                                                                                                                                   'project '
                                                                                                                                                   'or '
                                                                                                                                                   'a '
                                                                                                                                                   'new '
                                                                                                                                                   'connection.'),
 'Созданное вами остаётся вашим': ('Ceea ce creați rămâne al dvs.', 'What you create stays yours'),
 'После окончания PRO оформленная страница сохраняется. Фотографии, тексты и кадрирование можно менять свободно. Для новых PRO-эффектов, структуры и инструментов потребуется продление, когда они станут доступны. Ваши фотографии не удаляются из-за окончания подписки; удалением управляете вы.': ('După '
                                                                                                                                                                                                                                                                                                       'încheierea '
                                                                                                                                                                                                                                                                                                       'PRO, '
                                                                                                                                                                                                                                                                                                       'pagina '
                                                                                                                                                                                                                                                                                                       'creată '
                                                                                                                                                                                                                                                                                                       'se '
                                                                                                                                                                                                                                                                                                       'păstrează. '
                                                                                                                                                                                                                                                                                                       'Puteți '
                                                                                                                                                                                                                                                                                                       'schimba '
                                                                                                                                                                                                                                                                                                       'liber '
                                                                                                                                                                                                                                                                                                       'fotografiile, '
                                                                                                                                                                                                                                                                                                       'textele '
                                                                                                                                                                                                                                                                                                       'și '
                                                                                                                                                                                                                                                                                                       'încadrarea. '
                                                                                                                                                                                                                                                                                                       'Pentru '
                                                                                                                                                                                                                                                                                                       'efecte, '
                                                                                                                                                                                                                                                                                                       'structură '
                                                                                                                                                                                                                                                                                                       'și '
                                                                                                                                                                                                                                                                                                       'instrumente '
                                                                                                                                                                                                                                                                                                       'PRO '
                                                                                                                                                                                                                                                                                                       'noi '
                                                                                                                                                                                                                                                                                                       'va '
                                                                                                                                                                                                                                                                                                       'fi '
                                                                                                                                                                                                                                                                                                       'necesară '
                                                                                                                                                                                                                                                                                                       'reînnoirea, '
                                                                                                                                                                                                                                                                                                       'când '
                                                                                                                                                                                                                                                                                                       'acestea '
                                                                                                                                                                                                                                                                                                       'vor '
                                                                                                                                                                                                                                                                                                       'deveni '
                                                                                                                                                                                                                                                                                                       'disponibile. '
                                                                                                                                                                                                                                                                                                       'Fotografiile '
                                                                                                                                                                                                                                                                                                       'nu '
                                                                                                                                                                                                                                                                                                       'sunt '
                                                                                                                                                                                                                                                                                                       'șterse '
                                                                                                                                                                                                                                                                                                       'la '
                                                                                                                                                                                                                                                                                                       'expirarea '
                                                                                                                                                                                                                                                                                                       'abonamentului; '
                                                                                                                                                                                                                                                                                                       'dvs. '
                                                                                                                                                                                                                                                                                                       'decideți '
                                                                                                                                                                                                                                                                                                       'ce '
                                                                                                                                                                                                                                                                                                       'ștergeți.',
                                                                                                                                                                                                                                                                                                       'Your '
                                                                                                                                                                                                                                                                                                       'page '
                                                                                                                                                                                                                                                                                                       'remains '
                                                                                                                                                                                                                                                                                                       'after '
                                                                                                                                                                                                                                                                                                       'PRO '
                                                                                                                                                                                                                                                                                                       'expires. '
                                                                                                                                                                                                                                                                                                       'You '
                                                                                                                                                                                                                                                                                                       'can '
                                                                                                                                                                                                                                                                                                       'freely '
                                                                                                                                                                                                                                                                                                       'change '
                                                                                                                                                                                                                                                                                                       'photos, '
                                                                                                                                                                                                                                                                                                       'text '
                                                                                                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                                                                                                       'cropping. '
                                                                                                                                                                                                                                                                                                       'Renew '
                                                                                                                                                                                                                                                                                                       'PRO '
                                                                                                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                                                                                                       'access '
                                                                                                                                                                                                                                                                                                       'new '
                                                                                                                                                                                                                                                                                                       'effects, '
                                                                                                                                                                                                                                                                                                       'layouts '
                                                                                                                                                                                                                                                                                                       'and '
                                                                                                                                                                                                                                                                                                       'tools '
                                                                                                                                                                                                                                                                                                       'when '
                                                                                                                                                                                                                                                                                                       'available. '
                                                                                                                                                                                                                                                                                                       'Your '
                                                                                                                                                                                                                                                                                                       'photos '
                                                                                                                                                                                                                                                                                                       'are '
                                                                                                                                                                                                                                                                                                       'never '
                                                                                                                                                                                                                                                                                                       'deleted '
                                                                                                                                                                                                                                                                                                       'because '
                                                                                                                                                                                                                                                                                                       'your '
                                                                                                                                                                                                                                                                                                       'subscription '
                                                                                                                                                                                                                                                                                                       'expires; '
                                                                                                                                                                                                                                                                                                       'you '
                                                                                                                                                                                                                                                                                                       'decide '
                                                                                                                                                                                                                                                                                                       'what '
                                                                                                                                                                                                                                                                                                       'to '
                                                                                                                                                                                                                                                                                                       'delete.'),
 'На рассмотрении': ('În curs de examinare', 'Under review'),
 'Одобрена': ('Aprobată', 'Approved'),
 'Отклонена': ('Respinsă', 'Declined'),
 'Дата': ('Data', 'Date'),
 'Статус': ('Stare', 'Status'),
 'Ваше сообщение': ('Mesajul dvs.', 'Your message'),
 'Ответ SCENA': ('Răspuns SCENA', 'SCENA reply'),
 'Пробный PRO · 60 дней бесплатно': ('PRO de probă · 60 de zile gratuit', 'PRO trial · 60 days free'),
 'Ваша Сцена остаётся с вами': ('Scena dvs. rămâne a dvs.', 'Your Scene stays yours'),
 'Можно продолжать менять фотографии и тексты': ('Puteți continua să schimbați fotografiile și textele',
                                                 'You can keep updating your photos and text'),
 'Начните с того, что уже доступно': ('Începeți cu ceea ce este deja disponibil',
                                      'Start with what is available'),
 'Базовые возможности доступны и в FREE: начните оформлять свою Сцену уже сейчас.': ('Funcțiile de bază '
                                                                                     'sunt disponibile '
                                                                                     'și în FREE: '
                                                                                     'începeți să vă '
                                                                                     'personalizați '
                                                                                     'Scena chiar acum.',
                                                                                     'Essential '
                                                                                     'features are also '
                                                                                     'available on '
                                                                                     'FREE. Start '
                                                                                     'creating your '
                                                                                     'Scene today.'),
 'Доступно сейчас': ('Disponibil acum', 'Available now'),
 'Следующий уровень — с PRO': ('Nivelul următor — cu PRO', 'Take the next step with PRO'),
 'Эти возможности готовятся к запуску. Пока ими нельзя воспользоваться; подключение PRO сейчас не открывает их раньше времени.': ('Aceste '
                                                                                                                                  'funcții '
                                                                                                                                  'sunt '
                                                                                                                                  'în '
                                                                                                                                  'pregătire. '
                                                                                                                                  'Încă '
                                                                                                                                  'nu '
                                                                                                                                  'sunt '
                                                                                                                                  'disponibile; '
                                                                                                                                  'activarea '
                                                                                                                                  'PRO '
                                                                                                                                  'acum '
                                                                                                                                  'nu '
                                                                                                                                  'oferă '
                                                                                                                                  'acces '
                                                                                                                                  'anticipat '
                                                                                                                                  'la '
                                                                                                                                  'ele.',
                                                                                                                                  'These '
                                                                                                                                  'features '
                                                                                                                                  'are '
                                                                                                                                  'being '
                                                                                                                                  'prepared. '
                                                                                                                                  'They '
                                                                                                                                  'are '
                                                                                                                                  'not '
                                                                                                                                  'available '
                                                                                                                                  'yet; '
                                                                                                                                  'activating '
                                                                                                                                  'PRO '
                                                                                                                                  'does '
                                                                                                                                  'not '
                                                                                                                                  'provide '
                                                                                                                                  'early '
                                                                                                                                  'access.'),
 'Скоро в PRO': ('În curând în PRO', 'Coming to PRO'),
 'Пробный PRO на 60 дней': ('PRO de probă pentru 60 de zile', '60-day PRO trial'),
 'Пробный период активирован': ('Perioada de probă a fost activată', 'Trial activated'),
 'PRO активен': ('PRO este activ', 'PRO active'),
 'Оформить мою страницу Model': ('Personalizează pagina mea Model', 'Create my Model page'),
 'PRO уже активен — новая заявка не нужна.': ('PRO este deja activ — nu este nevoie de o cerere nouă.',
                                              'PRO is already active — no new application is needed.'),
 'Произвести впечатление': ('Creați o primă impresie', 'Make an impression'),
 'Личная Сцена, выразительная страница Model и портфолио. Выберите фотографии и расскажите, чем вы отличаетесь.': ('Scena '
                                                                                                                   'personală, '
                                                                                                                   'o '
                                                                                                                   'pagină '
                                                                                                                   'Model '
                                                                                                                   'expresivă '
                                                                                                                   'și '
                                                                                                                   'un '
                                                                                                                   'portofoliu. '
                                                                                                                   'Alegeți '
                                                                                                                   'fotografiile '
                                                                                                                   'și '
                                                                                                                   'povestiți '
                                                                                                                   'ce '
                                                                                                                   'vă '
                                                                                                                   'face '
                                                                                                                   'diferită.',
                                                                                                                   'Your '
                                                                                                                   'personal '
                                                                                                                   'Scene, '
                                                                                                                   'an '
                                                                                                                   'expressive '
                                                                                                                   'Model '
                                                                                                                   'page '
                                                                                                                   'and '
                                                                                                                   'portfolio. '
                                                                                                                   'Choose '
                                                                                                                   'your '
                                                                                                                   'photos '
                                                                                                                   'and '
                                                                                                                   'show '
                                                                                                                   'what '
                                                                                                                   'makes '
                                                                                                                   'you '
                                                                                                                   'unique.'),
 'Довести интерес до заявки': ('Transformați interesul într-o cerere', 'Turn interest into a request'),
 'Услуги, открытое время и приглашение в проект — рядом с вашим образом. Клиенту понятно, какой следующий шаг сделать.': ('Serviciile, '
                                                                                                                          'orele '
                                                                                                                          'disponibile '
                                                                                                                          'și '
                                                                                                                          'invitația '
                                                                                                                          'într-un '
                                                                                                                          'proiect '
                                                                                                                          'sunt '
                                                                                                                          'alături '
                                                                                                                          'de '
                                                                                                                          'imaginea '
                                                                                                                          'dvs. '
                                                                                                                          'Clientul '
                                                                                                                          'înțelege '
                                                                                                                          'ce '
                                                                                                                          'pas '
                                                                                                                          'urmează.',
                                                                                                                          'Services, '
                                                                                                                          'available '
                                                                                                                          'appointments '
                                                                                                                          'and '
                                                                                                                          'project '
                                                                                                                          'invitations '
                                                                                                                          'sit '
                                                                                                                          'alongside '
                                                                                                                          'your '
                                                                                                                          'image. '
                                                                                                                          'Visitors '
                                                                                                                          'can '
                                                                                                                          'easily '
                                                                                                                          'see '
                                                                                                                          'their '
                                                                                                                          'next '
                                                                                                                          'step.'),
 'Дать повод вернуться': ('Oferiți un motiv să revină', 'Give people a reason to return'),
 'Публикуйте истории, готовьте материалы для соцсетей и делитесь личными страницами по QR-коду.': ('Publicați '
                                                                                                   'povești, '
                                                                                                   'pregătiți '
                                                                                                   'materiale '
                                                                                                   'pentru '
                                                                                                   'rețelele '
                                                                                                   'sociale '
                                                                                                   'și '
                                                                                                   'distribuiți '
                                                                                                   'paginile '
                                                                                                   'personale '
                                                                                                   'prin '
                                                                                                   'cod '
                                                                                                   'QR.',
                                                                                                   'Share '
                                                                                                   'stories, '
                                                                                                   'prepare '
                                                                                                   'social '
                                                                                                   'content '
                                                                                                   'and '
                                                                                                   'share '
                                                                                                   'your '
                                                                                                   'personal '
                                                                                                   'pages '
                                                                                                   'with '
                                                                                                   'a '
                                                                                                   'QR '
                                                                                                   'code.'),
 'Ваш собственный Model-сценарий': ('Un scenariu Model propriu', 'Your own Model scenario'),
 'Глянец, клубная атмосфера или ваша идея. Выбирайте сценарий или собирайте его из блоков, цветов и анимаций; проверяйте на компьютере и телефоне.': ('Luciu, '
                                                                                                                                                      'atmosferă '
                                                                                                                                                      'de '
                                                                                                                                                      'club '
                                                                                                                                                      'sau '
                                                                                                                                                      'ideea '
                                                                                                                                                      'dvs. '
                                                                                                                                                      'Alegeți '
                                                                                                                                                      'un '
                                                                                                                                                      'scenariu '
                                                                                                                                                      'sau '
                                                                                                                                                      'creați-l '
                                                                                                                                                      'din '
                                                                                                                                                      'blocuri, '
                                                                                                                                                      'culori '
                                                                                                                                                      'și '
                                                                                                                                                      'animații; '
                                                                                                                                                      'verificați-l '
                                                                                                                                                      'pe '
                                                                                                                                                      'computer '
                                                                                                                                                      'și '
                                                                                                                                                      'telefon.',
                                                                                                                                                      'Gloss, '
                                                                                                                                                      'a '
                                                                                                                                                      'club '
                                                                                                                                                      'atmosphere '
                                                                                                                                                      'or '
                                                                                                                                                      'your '
                                                                                                                                                      'own '
                                                                                                                                                      'idea. '
                                                                                                                                                      'Choose '
                                                                                                                                                      'a '
                                                                                                                                                      'scenario '
                                                                                                                                                      'or '
                                                                                                                                                      'create '
                                                                                                                                                      'one '
                                                                                                                                                      'with '
                                                                                                                                                      'blocks, '
                                                                                                                                                      'colors '
                                                                                                                                                      'and '
                                                                                                                                                      'animations; '
                                                                                                                                                      'preview '
                                                                                                                                                      'it '
                                                                                                                                                      'on '
                                                                                                                                                      'desktop '
                                                                                                                                                      'and '
                                                                                                                                                      'mobile.'),
 'Промпты для вашего образа': ('Prompturi pentru imaginea dvs.', 'Prompts for your image'),
 'Готовьте задания своему ИИ под нужную страницу. Профессиональная библиотека и история версий помогут развивать образ последовательно.': ('Pregătiți '
                                                                                                                                           'instrucțiuni '
                                                                                                                                           'pentru '
                                                                                                                                           'propriul '
                                                                                                                                           'AI, '
                                                                                                                                           'potrivite '
                                                                                                                                           'paginii. '
                                                                                                                                           'Biblioteca '
                                                                                                                                           'profesională '
                                                                                                                                           'și '
                                                                                                                                           'istoricul '
                                                                                                                                           'versiunilor '
                                                                                                                                           'vă '
                                                                                                                                           'vor '
                                                                                                                                           'ajuta '
                                                                                                                                           'să '
                                                                                                                                           'dezvoltați '
                                                                                                                                           'imaginea '
                                                                                                                                           'coerent.',
                                                                                                                                           'Prepare '
                                                                                                                                           'instructions '
                                                                                                                                           'for '
                                                                                                                                           'your '
                                                                                                                                           'own '
                                                                                                                                           'AI, '
                                                                                                                                           'tailored '
                                                                                                                                           'to '
                                                                                                                                           'each '
                                                                                                                                           'page. '
                                                                                                                                           'A '
                                                                                                                                           'professional '
                                                                                                                                           'library '
                                                                                                                                           'and '
                                                                                                                                           'version '
                                                                                                                                           'history '
                                                                                                                                           'help '
                                                                                                                                           'you '
                                                                                                                                           'develop '
                                                                                                                                           'a '
                                                                                                                                           'consistent '
                                                                                                                                           'image.'),
 'Личный Market': ('Market personal', 'Personal Market'),
 'Четвёртая вкладка вашей Сцены — магазин товаров, которые вы выбираете и рекомендуете в своей профессии. Ваш опыт станет основой подбора.': ('A '
                                                                                                                                              'patra '
                                                                                                                                              'filă '
                                                                                                                                              'a '
                                                                                                                                              'Scenei '
                                                                                                                                              'dvs. '
                                                                                                                                              '— '
                                                                                                                                              'un '
                                                                                                                                              'magazin '
                                                                                                                                              'cu '
                                                                                                                                              'produsele '
                                                                                                                                              'pe '
                                                                                                                                              'care '
                                                                                                                                              'le '
                                                                                                                                              'alegeți '
                                                                                                                                              'și '
                                                                                                                                              'le '
                                                                                                                                              'recomandați '
                                                                                                                                              'în '
                                                                                                                                              'profesie, '
                                                                                                                                              'pe '
                                                                                                                                              'baza '
                                                                                                                                              'experienței '
                                                                                                                                              'dvs.',
                                                                                                                                              'The '
                                                                                                                                              'fourth '
                                                                                                                                              'tab '
                                                                                                                                              'of '
                                                                                                                                              'your '
                                                                                                                                              'Scene: '
                                                                                                                                              'a '
                                                                                                                                              'shop '
                                                                                                                                              'of '
                                                                                                                                              'products '
                                                                                                                                              'you '
                                                                                                                                              'choose '
                                                                                                                                              'and '
                                                                                                                                              'recommend '
                                                                                                                                              'in '
                                                                                                                                              'your '
                                                                                                                                              'profession, '
                                                                                                                                              'selected '
                                                                                                                                              'through '
                                                                                                                                              'your '
                                                                                                                                              'experience.'),
 'Заявка на PRO уже на рассмотрении. Ответ появится в истории ниже.': ('Cererea pentru PRO este în curs '
                                                                       'de examinare. Răspunsul va '
                                                                       'apărea în istoricul de mai jos.',
                                                                       'Your PRO application is already '
                                                                       'under review. The reply will '
                                                                       'appear in the history below.'),
 'Обсудим ваш следующий шаг?': ('Discutăm pasul următor?', 'Shall we plan your next step?'),
 'Оставьте заявку: команда SCENA уточнит условия и поможет выбрать доступные возможности под ваши задачи.': ('Lăsați '
                                                                                                             'o '
                                                                                                             'cerere: '
                                                                                                             'echipa '
                                                                                                             'SCENA '
                                                                                                             'va '
                                                                                                             'clarifica '
                                                                                                             'condițiile '
                                                                                                             'și '
                                                                                                             'vă '
                                                                                                             'va '
                                                                                                             'ajuta '
                                                                                                             'să '
                                                                                                             'alegeți '
                                                                                                             'funcțiile '
                                                                                                             'disponibile '
                                                                                                             'pentru '
                                                                                                             'obiectivele '
                                                                                                             'dvs.',
                                                                                                             'Send '
                                                                                                             'a '
                                                                                                             'request. '
                                                                                                             'The '
                                                                                                             'SCENA '
                                                                                                             'team '
                                                                                                             'will '
                                                                                                             'explain '
                                                                                                             'the '
                                                                                                             'terms '
                                                                                                             'and '
                                                                                                             'help '
                                                                                                             'you '
                                                                                                             'choose '
                                                                                                             'the '
                                                                                                             'features '
                                                                                                             'that '
                                                                                                             'fit '
                                                                                                             'your '
                                                                                                             'goals.'),
 'Мои заявки и ответы SCENA': ('Cererile mele și răspunsurile SCENA', 'My requests and SCENA replies'),
 'Образ на личной Сцене': ('Imagine pe Scena personală', 'Image on a personal Scene'),
 'Комментарий к заявке — необязательно': ('Comentariu la cerere — opțional',
                                          'Application comment — optional'),
 'Подать заявку на PRO': ('Trimite cererea pentru PRO', 'Apply for PRO'),
 'Например: хочу развивать Model-страницу и получать приглашения в проекты.': ('De exemplu: vreau să '
                                                                               'dezvolt pagina Model și '
                                                                               'să primesc invitații în '
                                                                               'proiecte.',
                                                                               'For example: I want to '
                                                                               'develop my Model page '
                                                                               'and receive project '
                                                                               'invitations.'),
 'Моя Сцена': ('Scena mea', 'My Scene'),
 'Выбрать время': ('Alege ora', 'Choose a time'),
 '1. Услуга': ('1. Serviciu', '1. Service'),
 '2. Дата и время': ('2. Data și ora', '2. Date and time'),
 '3. Контакты': ('3. Contacte', '3. Contact details'),
 'Новый навык начинается с первого шага. Узнайте программу, формат занятий и ближайшие даты у автора курса.': ('O '
                                                                                                               'abilitate '
                                                                                                               'nouă '
                                                                                                               'începe '
                                                                                                               'cu '
                                                                                                               'primul '
                                                                                                               'pas. '
                                                                                                               'Aflați '
                                                                                                               'programul, '
                                                                                                               'formatul '
                                                                                                               'și '
                                                                                                               'datele '
                                                                                                               'apropiate '
                                                                                                               'de '
                                                                                                               'la '
                                                                                                               'autorul '
                                                                                                               'cursului.',
                                                                                                               'Every '
                                                                                                               'new '
                                                                                                               'skill '
                                                                                                               'starts '
                                                                                                               'with '
                                                                                                               'a '
                                                                                                               'first '
                                                                                                               'step. '
                                                                                                               'Ask '
                                                                                                               'the '
                                                                                                               'course '
                                                                                                               'creator '
                                                                                                               'about '
                                                                                                               'the '
                                                                                                               'program, '
                                                                                                               'class '
                                                                                                               'format '
                                                                                                               'and '
                                                                                                               'upcoming '
                                                                                                               'dates.'),
 'Хотите узнать программу и ближайшие даты? Оставьте контакты — обсудим обучение и подтвердим место лично.': ('Doriți '
                                                                                                              'să '
                                                                                                              'aflați '
                                                                                                              'programul '
                                                                                                              'și '
                                                                                                              'datele '
                                                                                                              'apropiate? '
                                                                                                              'Lăsați '
                                                                                                              'datele '
                                                                                                              'de '
                                                                                                              'contact '
                                                                                                              '— '
                                                                                                              'discutăm '
                                                                                                              'despre '
                                                                                                              'curs '
                                                                                                              'și '
                                                                                                              'confirmăm '
                                                                                                              'locul '
                                                                                                              'personal.',
                                                                                                              'Want '
                                                                                                              'to '
                                                                                                              'know '
                                                                                                              'the '
                                                                                                              'program '
                                                                                                              'and '
                                                                                                              'upcoming '
                                                                                                              'dates? '
                                                                                                              'Leave '
                                                                                                              'your '
                                                                                                              'contact '
                                                                                                              'details '
                                                                                                              '— '
                                                                                                              'we '
                                                                                                              'will '
                                                                                                              'discuss '
                                                                                                              'the '
                                                                                                              'course '
                                                                                                              'and '
                                                                                                              'confirm '
                                                                                                              'your '
                                                                                                              'place '
                                                                                                              'personally.'),
 'Услуги и курсы': ('Servicii și cursuri', 'Services and courses'),
 'Стать моделью': ('Devino model', 'Become a model'),
 'Личное пространство пока не опубликовано.': ('Spațiul personal nu este încă publicat.',
                                               'This personal space is not published yet.'),
 'Профессиональное': ('Profesional', 'Professional'),
 'Этот раздел пока не опубликован.': ('Această secțiune nu este încă publicată.',
                                      'This section is not published yet.'),
 'Описание и предзапись': ('Descriere și preînscriere', 'Details and preregistration'),
 'Отправить запрос': ('Trimite o cerere', 'Send a request'),
 'Профессиональная страница': ('Pagina profesională', 'Professional page'),
 'Страница пока не опубликована.': ('Pagina nu este încă publicată.', 'This page is not published yet.'),
 'Модельное портфолио': ('Portofoliu model', 'Model portfolio'),
 'Пригласить как модель': ('Invită ca model', 'Invite as a model'),
 'Хочу стать моделью': ('Vreau să devin model', 'I want to be a model'),
 'Твоя история достойна Сцены.': ('Povestea ta merită o Scenă.', 'Your story deserves a Scene.'),
 'Хочешь попробовать себя в съёмках и модельных проектах? Начни со знакомства. Опыт не обязателен — расскажи, что тебя вдохновляет.': ('Vrei '
                                                                                                                                       'să '
                                                                                                                                       'încerci '
                                                                                                                                       'ședințe '
                                                                                                                                       'foto '
                                                                                                                                       'și '
                                                                                                                                       'proiecte '
                                                                                                                                       'de '
                                                                                                                                       'modeling? '
                                                                                                                                       'Începem '
                                                                                                                                       'prin '
                                                                                                                                       'a '
                                                                                                                                       'ne '
                                                                                                                                       'cunoaște. '
                                                                                                                                       'Experiența '
                                                                                                                                       'nu '
                                                                                                                                       'este '
                                                                                                                                       'obligatorie '
                                                                                                                                       '— '
                                                                                                                                       'spune-ne '
                                                                                                                                       'ce '
                                                                                                                                       'te '
                                                                                                                                       'inspiră.',
                                                                                                                                       'Want '
                                                                                                                                       'to '
                                                                                                                                       'explore '
                                                                                                                                       'photo '
                                                                                                                                       'shoots '
                                                                                                                                       'and '
                                                                                                                                       'modeling '
                                                                                                                                       'projects? '
                                                                                                                                       'Start '
                                                                                                                                       'by '
                                                                                                                                       'introducing '
                                                                                                                                       'yourself. '
                                                                                                                                       'No '
                                                                                                                                       'experience '
                                                                                                                                       'needed '
                                                                                                                                       '— '
                                                                                                                                       'tell '
                                                                                                                                       'us '
                                                                                                                                       'what '
                                                                                                                                       'inspires '
                                                                                                                                       'you.'),
 'Хочу стать моделью · первый шаг': ('Vreau să devin model · primul pas',
                                     'Become a model · the first step'),
 'Без опыта': ('Fără experiență', 'No experience'),
 'Есть любительские съёмки': ('Am ședințe foto de amator', 'Amateur photo shoots'),
 'Есть профессиональный опыт': ('Am experiență profesională', 'Professional experience'),
 'Опыт *': ('Experiență *', 'Experience *'),
 'Расскажите о себе': ('Povestiți despre dvs.', 'Tell us about yourself'),
 'Модельная страница пока не опубликована.': ('Pagina de model nu este încă publicată.',
                                              'The Model page is not published yet.'),
 'У вашего проекта есть идея. Давайте найдём для неё образ. Расскажите о съёмке, показе или кампании — обсудим детали и условия участия.': ('Proiectul '
                                                                                                                                            'vostru '
                                                                                                                                            'are '
                                                                                                                                            'o '
                                                                                                                                            'idee. '
                                                                                                                                            'Să-i '
                                                                                                                                            'găsim '
                                                                                                                                            'imaginea. '
                                                                                                                                            'Povestiți '
                                                                                                                                            'despre '
                                                                                                                                            'ședința '
                                                                                                                                            'foto, '
                                                                                                                                            'prezentare '
                                                                                                                                            'sau '
                                                                                                                                            'campanie '
                                                                                                                                            '— '
                                                                                                                                            'discutăm '
                                                                                                                                            'detaliile '
                                                                                                                                            'și '
                                                                                                                                            'condițiile '
                                                                                                                                            'de '
                                                                                                                                            'participare.',
                                                                                                                                            'Your '
                                                                                                                                            'project '
                                                                                                                                            'has '
                                                                                                                                            'an '
                                                                                                                                            'idea. '
                                                                                                                                            "Let's "
                                                                                                                                            'find '
                                                                                                                                            'its '
                                                                                                                                            'image. '
                                                                                                                                            'Tell '
                                                                                                                                            'us '
                                                                                                                                            'about '
                                                                                                                                            'your '
                                                                                                                                            'shoot, '
                                                                                                                                            'show '
                                                                                                                                            'or '
                                                                                                                                            'campaign '
                                                                                                                                            '— '
                                                                                                                                            'we '
                                                                                                                                            'will '
                                                                                                                                            'discuss '
                                                                                                                                            'the '
                                                                                                                                            'details '
                                                                                                                                            'and '
                                                                                                                                            'participation '
                                                                                                                                            'terms.'),
 'Модельный проект': ('Proiect de modeling', 'Model project'),
 'Формат проекта *': ('Formatul proiectului *', 'Project format *'),
 'Предполагаемая дата *': ('Data estimată *', 'Proposed date *'),
 'Краткий бриф *': ('Brief scurt *', 'Short brief *'),
 'Отправить приглашение': ('Trimite invitația', 'Send invitation'),
 'Курс': ('Curs', 'Course'),
 'Профессиональная страница пока не опубликована.': ('Pagina profesională nu este încă publicată.',
                                                     'The professional page is not published yet.'),
 'Курс не найден или предзапись закрыта.': ('Cursul nu a fost găsit sau preînscrierea este închisă.',
                                            'The course was not found or preregistration is closed.'),
 'Предварительная запись без автоматического подтверждения места.': ('Preînscriere fără confirmarea '
                                                                     'automată a locului.',
                                                                     'Preregistration does not '
                                                                     'automatically confirm a place.'),
 'Ваш вопрос — необязательно': ('Întrebarea dvs. — opțional', 'Your question — optional'),
 'Предварительно записаться': ('Preînscrie-mă', 'Preregister'),
 'Выбрать услугу и время': ('Alege serviciul și ora', 'Choose service and time'),
 '01 · Знакомство': ('01 · Cunoaștere', '01 · Introduction'),
 'Пара слов о себе': ('Câteva cuvinte despre tine', 'A few words about you'),
 '02 · Разговор': ('02 · Discuție', '02 · Conversation'),
 'Обсудим интересы и следующий шаг': ('Discutăm interesele și pasul următor',
                                      'Discuss your interests and next step'),
 '03 · Твой путь': ('03 · Parcursul tău', '03 · Your path'),
 'Решение остаётся за тобой': ('Decizia îți aparține', 'The choice stays yours'),
 'Ваше публичное имя *': ('Numele public *', 'Your public name *'),
 'Город *': ('Oraș *', 'City *'),
 'Какой образ мечтаете примерить?': ('Ce imagine visezi să încerci?',
                                     'What look would you love to try?'),
 'Бренд / организация *': ('Brand / organizație *', 'Brand / organization *'),
 'Контактное лицо *': ('Persoană de contact *', 'Contact person *'),
 'Ваше пространство': ('Spațiul dvs.', 'Your workspace'),
 'Ваша история. Ваша Сцена.': ('Povestea ta. Scena ta.', 'Your story. Your Scene.'),
 'Вход в кабинет': ('Intrare în cabinet', 'Sign in'),
 'Моя Сцена · знакомство': ('Scena mea · cunoaște-mă', 'My Scene · meet me'),
 'История в кадрах': ('Poveste în imagini', 'A story in images'),
 'Профессиональный beauty-портрет Марии': ('Portret beauty profesional al Mariei',
                                           "Maria's professional beauty portrait"),
 'Предложения пока не опубликованы.': ('Ofertele nu sunt încă publicate.',
                                       'No offers have been published yet.'),
 'Открыть портфолио': ('Deschide portofoliul', 'Open portfolio'),
 'Ваши возможности и срок доступа': ('Posibilitățile și perioada de acces',
                                     'Your features and access period'),
 'Записаться на макияж': ('Programare la machiaj', 'Book makeup'),
 'Открыть Model': ('Deschide Model', 'Open Model')}
)

# Editor labels, navigation, validation and owner-authored content defaults.
_load_rows(r'''
Главная|Acasă|Home
Помощь|Ajutor|Help
Страницы|Pagini|Pages
Работа|Activitate|Work
Продвижение|Promovare|Promotion
Настройки|Setări|Settings
Рабочий кабинет|Spațiu de lucru|Workspace
Ваш кабинет|Cabinetul dvs.|Your workspace
SCENA Ассистент|Asistentul SCENA|SCENA Assistant
Команда SCENA|Echipa SCENA|SCENA Team
Заявки|Cereri|Requests
Услуги|Servicii|Services
График|Program|Schedule
QR-коды|Coduri QR|QR codes
Резервная копия|Copie de rezervă|Backup
Раздел кабинета|Secțiunea cabinetului|Workspace section
Что сделаем сегодня?|Ce facem astăzi?|What shall we do today?
Заявки, ваши страницы и идеи для продвижения — всё под рукой.|Cereri, paginile dvs. și idei de promovare — toate la îndemână.|Requests, your pages and promotion ideas — all within reach.
Задайте вопрос о кабинете или получите конкретные рекомендации по заполнению страниц.|Puneți o întrebare despre cabinet sau primiți recomandări concrete pentru paginile dvs.|Ask about your workspace or get practical recommendations for your pages.
Напишите запрос и следите за ответом в одной сохранённой переписке.|Scrieți o cerere și urmăriți răspunsul în aceeași conversație salvată.|Send a request and follow the reply in one saved conversation.
Подписка PRO|Abonament PRO|PRO subscription
Срок действия, возможности PRO и история заявок на активацию.|Perioada de acces, funcțiile PRO și istoricul cererilor de activare.|Access period, PRO features and activation request history.
Имя, история, главное фото и ссылки на ваши направления.|Nume, poveste, fotografie principală și linkuri către direcțiile dvs.|Name, story, main photo and links to your pages.
Название, описание и фотографии. Цены и услуги редактируются отдельно в разделе «Работа».|Titlu, descriere și fotografii. Prețurile și serviciile se editează separat în secțiunea Activitate.|Title, description and photos. Edit prices and services separately under Work.
Страница Model|Pagina Model|Model page
Знакомство, ваши образы и личные фразы.|Prezentarea, imaginile și mesajele dvs. personale.|Your introduction, images and personal messages.
Все обращения клиентов, статусы и детали — в одном месте.|Toate cererile clienților, stările și detaliile într-un singur loc.|All client requests, statuses and details in one place.
Группы и услуги|Grupuri și servicii|Groups and services
Объединяйте похожие услуги в группы, задавайте способ записи и управляйте публикацией.|Grupați serviciile similare, alegeți modul de programare și gestionați publicarea.|Group similar services, choose how clients book and manage publication.
Рабочие дни, свободное время, перерывы и исключения.|Zile lucrătoare, ore disponibile, pauze și excepții.|Working days, available times, breaks and exceptions.
Истории и новости для «Моей Сцены», Professional и Model.|Povești și noutăți pentru Scena mea, Professional și Model.|Stories and news for My Scene, Professional and Model.
Готовые QR-коды на каждую публичную страницу — без сторонних сервисов.|Coduri QR gata pentru fiecare pagină publică, fără servicii externe.|Ready-to-use QR codes for every public page, without third-party services.
Подготовленные сообщения и результаты отправки.|Mesaje pregătite și rezultatele trimiterii.|Prepared messages and delivery results.
Скачайте копию данных кабинета перед крупными изменениями.|Descărcați o copie a datelor înainte de modificări importante.|Download a backup of your workspace before major changes.
SCENA Ассистент и команда|Asistentul și echipa SCENA|SCENA Assistant and team
Понятные подсказки, ваши вопросы и ответы|Îndrumări clare, întrebările și răspunsurile dvs.|Clear guidance, your questions and answers
Заявки и услуги|Cereri și servicii|Requests and services
Ваша публичная Сцена|Scena dvs. publică|Your public Scene
Моя Сцена, Professional и Model редактируются отдельно|Scena mea, Professional și Model se editează separat|Edit My Scene, Professional and Model separately
Публикации и QR|Publicații și QR|Posts and QR
SMS и резервная копия|SMS și copie de rezervă|SMS and backup
Проверка очереди уведомлений и сохранение данных|Verificarea notificărilor și salvarea datelor|Check notifications and save your data
Быстрый просмотр|Previzualizare rapidă|Quick preview
Основное|Date principale|Basics
Что показывать|Ce afișăm|What to show
Что показать?|Ce afișăm?|What to show?
Публичное имя|Nume public|Public name
Адрес страницы|Adresa paginii|Page address
Уникальный адрес|Adresă unică|Unique address
Город|Oraș|City
Моя история|Povestea mea|My story
Моя Сцена опубликована|Scena mea este publicată|My Scene is published
«Моя Сцена» опубликована|Scena mea este publicată|My Scene is published
Разрешить поиск в интернете|Permite căutarea pe internet|Allow search engines
Разрешить индексацию «Моей Сцены»|Permite indexarea Scenei mele|Allow search engines to index My Scene
Индексация включена|Indexarea este activată|Search indexing enabled
Показывать кнопку Model|Afișează butonul Model|Show Model button
Показывать кнопку Professional|Afișează butonul Professional|Show Professional button
Показывать Model в «Моей Сцене»|Afișează Model pe Scena mea|Show Model on My Scene
Показывать профессиональную страницу в «Моей Сцене»|Afișează pagina profesională pe Scena mea|Show the professional page on My Scene
Обе языковые версии проверены|Am verificat ambele versiuni lingvistice|Both language versions checked
Обе версии страницы проверены|Am verificat ambele versiuni ale paginii|Both page versions checked
Обе версии проверены|Am verificat ambele versiuni|Both versions checked
RU и RO проверены|RU și RO verificate|RU and RO checked
RU и RO проверены — сразу опубликовать|RU și RO verificate — publică acum|RU and RO checked — publish now
Тексты RU и RO проверены|Textele RU și RO sunt verificate|RU and RO texts checked
Сохранить Мою Сцену|Salvează Scena mea|Save My Scene
Сохранить Professional|Salvează Professional|Save Professional
Сохранить профиль|Salvează profilul|Save profile
Открыть Мою Сцену|Deschide Scena mea|Open My Scene
Открыть Professional|Deschide Professional|Open Professional
Главное фото|Fotografie principală|Main photo
Сохранить выбранные фотографии|Salvează fotografiile selectate|Save selected photos
Сохранить фотографию|Salvează fotografia|Save photo
Сохранённый оригинал|Original salvat|Saved original
Фотографии|Fotografii|Photos
Фотографии портфолио|Fotografii de portofoliu|Portfolio photos
Портфолио Model|Portofoliu Model|Model portfolio
Фотография недоступна. Выберите замену.|Fotografia nu este disponibilă. Alegeți un înlocuitor.|Photo unavailable. Choose a replacement.
Сначала выберите фотографию.|Alegeți mai întâi o fotografie.|Choose a photo first.
Выберите хотя бы одну фотографию.|Alegeți cel puțin o fotografie.|Choose at least one photo.
Заменить фотографию|Înlocuiește fotografia|Replace photo
Добавить или заменить фотографию|Adaugă sau înlocuiește fotografia|Add or replace photo
Исходная фотография сохраняется. Удаление кадра из портфолио не удаляет оригинал.|Fotografia originală se păstrează. Eliminarea unui cadru din portofoliu nu șterge originalul.|Your original photo is preserved. Removing a portfolio frame does not delete the original.
Можно вернуть прежнюю фотографию или использовать её в другом кадре.|Puteți restabili fotografia precedentă sau o puteți folosi în alt cadru.|You can restore an earlier photo or use it in another frame.
Убрать кадр из портфолио|Elimină cadrul din portofoliu|Remove frame from portfolio
Место для новой фотографии.|Loc pentru o fotografie nouă.|Space for a new photo.
До 20 МБ. Для чёткого портрета рекомендуем длинную сторону от 1600 px. Оригиналы сохраняются.|Până la 20 MB. Pentru un portret clar, recomandăm latura lungă de cel puțin 1600 px. Originalele se păstrează.|Up to 20 MB. For a clear portrait, use an original at least 1600 px on the long side. Originals are preserved.
Описание изображения и кадрирование|Descrierea imaginii și încadrarea|Image description and cropping
Фокус на компьютере|Încadrare pe computer|Desktop focal point
Фокус на телефоне|Încadrare pe telefon|Mobile focal point
Положение фотографии на компьютере и телефоне|Poziția fotografiei pe computer și telefon|Photo position on desktop and mobile
JPG, PNG или WebP · до 20 МБ. Длинная сторона от 600 px, короткая от 400 px. Для чёткого большого кадра рекомендуем оригинал от 1600 px по длинной стороне.|JPG, PNG sau WebP · până la 20 MB. Latura lungă de minimum 600 px, cea scurtă de minimum 400 px. Pentru o imagine mare clară, recomandăm cel puțin 1600 px pe latura lungă.|JPG, PNG or WebP · up to 20 MB. At least 600 px on the long side and 400 px on the short side. For a clear large image, use an original at least 1600 px on the long side.
Знакомство — первая страница Model|Prezentarea — prima pagină Model|Introduction — the first Model page
Здесь можно рассказать о себе, увлечениях, поездках и идее ваших образов. Посетитель сначала знакомится с вами, затем сам открывает показ.|Aici puteți povesti despre dvs., pasiuni, călătorii și ideea imaginilor. Vizitatorul vă cunoaște mai întâi, apoi deschide prezentarea.|Tell visitors about yourself, your interests, travels and the idea behind your images. They meet you first, then choose to open the show.
Начинать Model со знакомства|Începe pagina Model cu prezentarea|Start Model with an introduction
Отдельная фотография для знакомства|Fotografie separată pentru prezentare|Separate introduction photo
Вернуть сохранённый портрет|Restabilește un portret salvat|Restore a saved portrait
Сохранить визитку|Salvează prezentarea|Save introduction
Посмотреть знакомство|Vezi prezentarea|View introduction
Обновить редактор|Actualizează editorul|Refresh editor
Образы и настройки Model|Imagini și setări Model|Model images and settings
Здесь модель управляет пятью образами, которые открываются после знакомства. Каждый кадр получает отдельный личный посыл на RU и RO.|Aici modelul gestionează cele cinci imagini afișate după prezentare. Fiecare cadru are un mesaj personal în RU și RO.|Manage the five images shown after your introduction. Each frame has its own personal message in RU and RO.
Использовать сценический лендинг|Folosește prezentarea scenică|Use the stage landing page
Автоматически менять кадры|Schimbă automat imaginile|Automatically advance images
Первый кадр|Primul cadru|First frame
Сохранить Model-лендинг|Salvează pagina Model|Save Model landing page
Сохранить настройки Model|Salvează setările Model|Save Model settings
Выберите кадр|Alegeți cadrul|Choose a frame
Показывать кадр|Afișează cadrul|Show frame
Показ, секунд|Afișare, secunde|Display duration, seconds
Порядок|Ordine|Order
Кадр публикуется только после включения видимости, заполнения обеих языковых версий и отметки «Обе версии проверены». Остальное сохраняется как черновик.|Cadrul se publică doar după activarea afișării, completarea ambelor limbi și confirmarea verificării. Restul se salvează ca ciornă.|A frame is published only when visibility is enabled, both languages are filled in and confirmed. Otherwise, it remains a draft.
Заголовок RU|Titlu RU|Title RU
Название RU|Denumire RU|Name RU
Описание RU|Descriere RU|Description RU
Текст RU|Text RU|Text RU
Личный посыл / подпись RU|Mesaj personal / descriere RU|Personal message / caption RU
Описание для доступности RU|Descriere accesibilă RU|Accessibility description RU
Здесь настраивается обязательное личное пространство «Моя Сцена» и видимость направлений.|Aici configurați spațiul personal Scena mea și vizibilitatea direcțiilor.|Set up My Scene and choose which personal directions are visible.
О человеке|Despre persoană|About the person
Где показывать услуги?|Unde afișăm serviciile?|Where should services appear?
Для публикации заполните и подтвердите версии RU/RO.|Pentru publicare, completați și confirmați versiunile RU/RO.|Complete and confirm the RU/RO versions before publishing.
Для публикации заполните название и описание на RU и RO.|Pentru publicare, completați titlul și descrierea în RU și RO.|Complete the title and description in RU and RO before publishing.
Проверьте тексты на русском и румынском перед публикацией.|Verificați textele în rusă și română înainte de publicare.|Check the Russian and Romanian text before publishing.
Сохранение не публикует незавершённый черновик. Для публикации отдельно подтвердите RU и RO.|Salvarea nu publică o ciornă incompletă. Confirmați separat RU și RO pentru publicare.|Saving does not publish an unfinished draft. Confirm RU and RO separately before publication.
Войти|Intră|Sign in
Выйти|Ieșire|Sign out
Пароль|Parolă|Password
Неверный пароль.|Parolă incorectă.|Incorrect password.
Слишком много неверных попыток. Закройте вкладку и откройте приложение заново.|Prea multe încercări greșite. Închideți fila și deschideți aplicația din nou.|Too many incorrect attempts. Close the tab and open the app again.
Пароль администратора не настроен. Запустите приложение через START-SCENA.cmd или задайте переменную SCENA_ADMIN_PASSWORD.|Parola administratorului nu este configurată. Porniți aplicația prin START-SCENA.cmd sau setați SCENA_ADMIN_PASSWORD.|The administrator password is not configured. Start the app with START-SCENA.cmd or set SCENA_ADMIN_PASSWORD.
Заявки, график и настройки доступны только после проверки пароля.|Cererile, programul și setările sunt accesibile după verificarea parolei.|Requests, schedule and settings are available after password verification.
Заявка|Cerere|Request
Список заявок|Lista cererilor|Request list
Полная таблица заявок|Tabelul complet al cererilor|Full request table
На телефоне таблица прокручивается внутри этого блока.|Pe telefon, tabelul se derulează în interiorul acestui bloc.|On mobile, scroll the table inside this panel.
В выбранной категории заявок пока нет.|Nu sunt cereri în categoria selectată.|There are no requests in the selected category yet.
Изменить статус|Schimbă starea|Change status
Сохранить статус|Salvează starea|Save status
Комментарий|Comentariu|Comment
Новая услуга|Serviciu nou|New service
Добавить услугу|Adaugă serviciu|Add service
Название услуги|Denumirea serviciului|Service name
Название услуги на RO|Denumirea serviciului în RO|Service name in RO
Описание услуги на RO|Descrierea serviciului în RO|Service description in RO
Название группы|Denumirea grupului|Group name
Название группы на RO|Denumirea grupului în RO|Group name in RO
Название группы на RO — можно заполнить позже|Denumirea grupului în RO — poate fi completată mai târziu|Group name in RO — you can add it later
Название новой группы|Denumirea grupului nou|New group name
Группа|Grup|Group
Выберите группу|Alegeți grupul|Choose a group
К какой группе относится услуга?|Cărui grup îi aparține serviciul?|Which group does this service belong to?
Короткое описание для клиента|Descriere scurtă pentru client|Short client-facing description
Короткое описание для клиента — можно заполнить позже|Descriere scurtă pentru client — poate fi completată mai târziu|Short client-facing description — you can add it later
Как клиент записывается?|Cum se programează clientul?|How does the client book?
Цена, 0 = договорная|Preț, 0 = la înțelegere|Price, 0 = on request
Продолжительность, мин.|Durată, minute|Duration, minutes
Перерыв после записи, мин.|Pauză după programare, minute|Break after appointment, minutes
Без этой отметки услуга сохранится как черновик и не будет видна клиентам.|Fără această confirmare, serviciul rămâne ciornă și nu este vizibil clienților.|Without this confirmation, the service stays a draft and is hidden from clients.
Сначала достаточно названия, группы, цены и способа записи.|Pentru început sunt suficiente denumirea, grupul, prețul și modul de programare.|Start with a name, group, price and booking method.
Укажите название новой группы.|Introduceți denumirea grupului nou.|Enter the new group name.
Укажите название услуги.|Introduceți denumirea serviciului.|Enter the service name.
Настроить группы|Configurează grupurile|Manage groups
Первая группа появится автоматически при добавлении услуги.|Primul grup apare automat când adăugați un serviciu.|Your first group is created automatically when you add a service.
Группа объединяет похожие услуги на публичной странице. Её можно переименовать или временно скрыть целиком.|Un grup reunește servicii similare pe pagina publică. Îl puteți redenumi sau ascunde temporar.|A group brings similar services together on the public page. You can rename it or temporarily hide the whole group.
Пояснение для клиента — необязательно|Explicație pentru client — opțional|Client note — optional
Пояснение на RO — необязательно|Explicație în RO — opțional|Note in RO — optional
Перевод и публикация|Traducere și publicare|Translation and publication
Сохранить группу|Salvează grupul|Save group
Сохранить услугу|Salvează serviciul|Save service
Изменить|Editează|Edit
Ещё|Mai multe|More
Показать|Afișează|Show
Отправить в архив|Arhivează|Archive
Архив убирает услугу из рабочего списка. Её можно восстановить.|Arhivarea elimină serviciul din lista activă. Îl puteți restabili.|Archiving removes a service from the active list. You can restore it later.
Восстановить|Restabilește|Restore
Удалить навсегда|Șterge definitiv|Delete permanently
Подтверждение удаления|Confirmarea ștergerii|Confirm deletion
Подтвердить удаление|Confirmă ștergerea|Confirm deletion
Сначала подтвердите удаление.|Confirmați mai întâi ștergerea.|Confirm deletion first.
Отмена|Anulează|Cancel
Закрыть редактор|Închide editorul|Close editor
Закрыть без сохранения|Închide fără salvare|Close without saving
Сохранить изменения|Salvează modificările|Save changes
Не удалось сохранить изменения. Попробуйте ещё раз через несколько секунд.|Modificările nu au fost salvate. Încercați din nou peste câteva secunde.|Changes could not be saved. Try again in a few seconds.
Рабочие дни|Zile lucrătoare|Working days
Регулярный график|Program regulat|Regular schedule
Выходные и дополнительные часы|Zile libere și ore suplimentare|Days off and extra hours
Глубина, дней|Perioada disponibilă, zile|Booking horizon, days
Минимум до записи, ч.|Timp minim înainte de programare, ore|Minimum booking notice, hours
Удержание, ч.|Rezervare temporară, ore|Temporary hold, hours
Шаг слотов, мин.|Intervalul orelor, minute|Time slot interval, minutes
Сохранить график|Salvează programul|Save schedule
Проверьте рабочие дни, начало, конец и перерыв.|Verificați zilele lucrătoare, începutul, sfârșitul și pauza.|Check working days, start, end and break times.
Добавить исключение|Adaugă excepție|Add exception
Удалить исключение|Șterge excepția|Delete exception
Удалить выбранное исключение|Șterge excepția selectată|Delete selected exception
Режим|Mod|Mode
Валюта|Monedă|Currency
Рекомендации для ваших страниц|Recomandări pentru paginile dvs.|Recommendations for your pages
Вопрос SCENA Ассистенту|Întrebare pentru Asistentul SCENA|Question for SCENA Assistant
История общения|Istoricul conversației|Conversation history
Здесь сохраняются ваши вопросы и ответы.|Aici se păstrează întrebările și răspunsurile dvs.|Your questions and answers are saved here.
Обновить ответы|Actualizează răspunsurile|Refresh replies
Сообщение команде SCENA|Mesaj pentru echipa SCENA|Message to the SCENA team
Ответы ассистента сейчас недоступны. Вы можете сохранить вопрос и воспользоваться рекомендациями выше.|Răspunsurile asistentului nu sunt disponibile acum. Puteți salva întrebarea și consulta recomandările de mai sus.|Assistant replies are unavailable right now. You can save your question and use the recommendations above.
Связь с командой пока недоступна. Обращение можно сохранить.|Legătura cu echipa nu este disponibilă acum. Puteți salva cererea.|Contact with the team is unavailable right now. You can save your request.
Публичный адрес SCENA|Adresa publică SCENA|Public SCENA address
Сохранить адрес|Salvează adresa|Save address
Покажите QR-код клиенту или сохраните для визитки. «Запись к мастеру» сразу открывает выбор услуги и времени.|Arătați codul QR clientului sau salvați-l pentru cartea de vizită. Programarea deschide direct alegerea serviciului și orei.|Show the QR code to a client or save it for your business card. Booking opens the service and time selection directly.
Сейчас ссылка открывается только на этом компьютере. Для клиентов укажите адрес, доступный с их телефона.|Linkul funcționează acum doar pe acest computer. Pentru clienți, folosiți o adresă accesibilă de pe telefon.|This link currently opens only on this computer. For clients, use an address accessible from their phones.
Скопировать ссылку можно кнопкой справа в поле выше.|Copiați linkul cu butonul din dreapta câmpului de mai sus.|Copy the link using the button on the right of the field above.
Скачать QR-код|Descarcă codul QR|Download QR code
Укажите полный адрес, начинающийся с http:// или https://.|Introduceți adresa completă, începând cu http:// sau https://.|Enter the full address beginning with http:// or https://.
SMS пока не отправляются. Подготовленные сообщения можно просмотреть ниже.|SMS-urile nu se trimit acum. Mesajele pregătite pot fi văzute mai jos.|SMS messages are not being sent yet. You can view prepared messages below.
Поиск отменён. В Telegram программа не обращалась.|Căutarea a fost anulată. Telegram nu a fost accesat.|Search cancelled. Telegram was not contacted.
Тест отменён. Ничего не отправлено.|Testul a fost anulat. Nu s-a trimis nimic.|Test cancelled. Nothing was sent.
Telegram подтвердил доставку теста. Проверьте это сообщение у себя в Telegram.|Telegram a confirmat livrarea testului. Verificați mesajul în Telegram.|Telegram confirmed test delivery. Check the message in Telegram.
Получатель не подтверждён. Подключение не сохранено.|Destinatarul nu a fost confirmat. Conexiunea nu a fost salvată.|Recipient not confirmed. The connection was not saved.
Резервная копия и перенос|Copie de rezervă și transfer|Backup and transfer
Ваши материалы остаются с вами. Выберите нужное действие.|Materialele dvs. rămân ale dvs. Alegeți acțiunea dorită.|Your materials stay yours. Choose an action.
Сохранить свою Сцену|Salvează Scena mea|Back up my Scene
Подготовить материалы для будущей платформы|Pregătește materialele pentru platformă|Prepare materials for the platform
Восстановить из резервной копии|Restabilește din copia de rezervă|Restore from backup
Резервная копия SCENA (.zip)|Copie de rezervă SCENA (.zip)|SCENA backup (.zip)
После новых изменений создайте свежую копию кнопкой выше.|După noi modificări, creați o copie actualizată cu butonul de mai sus.|After new changes, create a fresh backup using the button above.
Выберите ранее скачанную резервную копию SCENA. Восстановленная Сцена появится в отдельной папке рядом с текущей.|Alegeți o copie de rezervă SCENA descărcată anterior. Scena restabilită va apărea într-un dosar separat, lângă cel actual.|Choose a previously downloaded SCENA backup. The restored Scene will appear in a separate folder next to the current one.
Проверить архив и показать восстановление|Verifică arhiva și previzualizează restaurarea|Check archive and preview restoration
Архив проверен. Можно восстановить отдельную Сцену.|Arhiva a fost verificată. Puteți restabili o Scenă separată.|Archive verified. You can restore a separate Scene.
Будет создана новая папка:|Va fi creat un dosar nou:|A new folder will be created:
Восстановить выбранный архив в указанную новую папку|Restabilește arhiva selectată în noul dosar indicat|Restore the selected archive to the new folder shown
Восстановить отдельную Сцену|Restabilește o Scenă separată|Restore a separate Scene
Ваша Сцена восстановлена в отдельной папке.|Scena dvs. a fost restabilită într-un dosar separat.|Your Scene was restored to a separate folder.
Откройте эту папку и запустите START-SCENA.cmd.|Deschideți acest dosar și porniți START-SCENA.cmd.|Open that folder and run START-SCENA.cmd.
Текущая Сцена продолжит работать. Подключения к внешним сервисам в новой установке нужно настроить отдельно.|Scena actuală continuă să funcționeze. Conexiunile externe se configurează separat în noua instalare.|Your current Scene will continue working. Configure external connections separately in the new installation.
Не удалось проверить архив. Проверьте доступ к диску и повторите.|Arhiva nu a putut fi verificată. Verificați accesul la disc și încercați din nou.|Could not verify the archive. Check disk access and try again.
Не удалось прочитать файлы. Проверьте доступ к папке SCENA и повторите.|Fișierele nu au putut fi citite. Verificați accesul la dosarul SCENA și încercați din nou.|Could not read the files. Check access to the SCENA folder and try again.
Не удалось создать новую Сцену. Проверьте свободное место и доступ к папке, затем повторите.|Scena nouă nu a putut fi creată. Verificați spațiul liber și accesul la dosar, apoi încercați din nou.|Could not create a new Scene. Check free disk space and folder access, then try again.
Это файл для будущего переноса. Подключение и синхронизация с платформой ещё не реализованы. Ничего не отправляется автоматически.|Acesta este un fișier pentru transfer ulterior. Conectarea și sincronizarea cu platforma nu sunt implementate. Nimic nu se trimite automat.|This file is for a future transfer. Platform connection and synchronization are not implemented. Nothing is sent automatically.
''')

_load_rows(r'''
Кишинёв|Chișinău|Chișinău
Модель|Model|Model
Персональная консультация|Consultație personală|Personal consultation
Индивидуальная услуга|Serviciu individual|Individual service
Индивидуальная встреча со специалистом.|Întâlnire individuală cu specialistul.|A personal meeting with the specialist.
Формат и результат согласовываются перед подтверждением записи.|Formatul și rezultatul se stabilesc înainte de confirmarea programării.|The format and expected result are agreed before your booking is confirmed.
Авторский курс|Curs de autor|Signature course
Формат, сроки, цена и права согласовываются отдельно.|Formatul, termenii, prețul și drepturile se stabilesc separat.|Format, timing, price and usage rights are agreed separately.
Индивидуальная работа|Servicii individuale|Individual services
Персональные услуги и консультации.|Servicii și consultații individuale.|Personal services and consultations.
Обучение|Cursuri|Courses
Курсы, практикумы и обучение.|Cursuri, ateliere și instruire.|Courses, workshops and training.
Модельные проекты|Proiecte de modeling|Model projects
Съёмки, показы и предложения брендов.|Ședințe foto, prezentări și propuneri de la branduri.|Photo shoots, shows and brand offers.
Модельные форматы|Formate Model|Model formats
Основные услуги|Servicii principale|Core services
Запись по времени|Programare la oră|Timed appointment
Курс — предварительная запись|Curs — preînscriere|Course — preregistration
Обращение без календаря|Cerere fără calendar|Inquiry without calendar
Запись на услугу|Programare la serviciu|Service booking
Предзапись на курс|Preînscriere la curs|Course preregistration
Приглашение модели|Invitație pentru model|Model invitation
Новая|Nouă|New
Ожидает подтверждения|Așteaptă confirmarea|Awaiting confirmation
Связались|Contactată|Contacted
Подтверждена|Confirmată|Confirmed
Завершена|Finalizată|Completed
Отменена|Anulată|Cancelled
Срок подтверждения истёк|Termenul de confirmare a expirat|Confirmation period expired
Дневной макияж|Machiaj de zi|Day makeup
Вечерний макияж|Machiaj de seară|Evening makeup
Макияж|Machiaj|Makeup
Каталожная съёмка|Ședință foto de catalog|Catalog photo shoot
Имиджевая съёмка|Ședință foto de imagine|Editorial photo shoot
Я соединяю красоту, характер и движение — от точного макияжа до яркого выхода на сцену.|Unesc frumusețea, caracterul și mișcarea — de la machiajul precis la o apariție memorabilă pe scenă.|I bring together beauty, character and movement — from precise makeup to a memorable entrance on stage.
Премиальный макияж для событий, съёмок и выразительных персональных образов.|Machiaj premium pentru evenimente, ședințe foto și imagini personale expresive.|Premium makeup for events, photo shoots and expressive personal looks.
Портфолио и предложения для брендов, фотографов и творческих команд.|Portofoliu și oferte pentru branduri, fotografi și echipe creative.|Portfolio and opportunities for brands, photographers and creative teams.
Быть собой — мой самый смелый образ.|Să fiu eu însămi este cea mai curajoasă imagine a mea.|Being myself is my boldest look.
Красота начинается со взгляда, который не просит разрешения.|Frumusețea începe cu o privire care nu cere permisiune.|Beauty begins with a gaze that needs no permission.
Женственность — это сила, которой не нужно ничего доказывать.|Feminitatea este o forță care nu trebuie să demonstreze nimic.|Femininity is a strength with nothing to prove.
Я выбираю движение, свет и свободу.|Aleg mișcarea, lumina și libertatea.|I choose movement, light and freedom.
Мой свет не просит сцены. Он создаёт её.|Lumina mea nu cere o scenă. O creează.|My light does not ask for a stage. It creates one.
Модель в чёрном архитектурном образе на подиуме с сияющим кругом|Model într-o ținută arhitecturală neagră, pe podium, într-un cerc de lumină|Model in a black architectural outfit on a runway with a glowing circle
Крупный портрет модели среди зеркальных панелей и света софитов|Portret apropiat al modelului printre panouri de oglindă și lumini de podium|Close-up portrait among mirrored panels and runway spotlights
Модель в белом скульптурном couture-платье на чёрном подиуме|Model într-o rochie couture albă, sculpturală, pe podiumul negru|Model in a white sculptural couture dress on a black runway
Модель в летящем белом платье на глянцевом подиуме|Model într-o rochie albă fluidă, pe un podium lucios|Model in a flowing white dress on a glossy runway
Модель в телесном couture-комбинезоне с белой бахромой и крыльями|Model într-o salopetă couture nude, cu franjuri și aripi albe|Model in a tan couture playsuit with white fringe and wings
Укажите имя или название организации.|Introduceți numele sau denumirea organizației.|Enter a name or organization name.
Укажите номер телефона.|Introduceți numărul de telefon.|Enter your phone number.
Поддерживаются только номера Молдовы +373.|Sunt acceptate doar numerele din Moldova +373.|Only Moldova phone numbers beginning with +373 are supported.
Проверьте адрес электронной почты.|Verificați adresa de email.|Check your email address.
Необходимо согласие на обработку контактных данных.|Este necesar acordul pentru prelucrarea datelor de contact.|Consent to processing contact details is required.
Предложение недоступно.|Oferta nu este disponibilă.|This offer is unavailable.
Для этого предложения не используется календарь.|Această ofertă nu utilizează calendarul.|This offer does not use appointment booking.
Выбранное время уже недоступно. Выберите другое.|Ora aleasă nu mai este disponibilă. Alegeți alta.|That time is no longer available. Choose another.
Это предложение не является курсом.|Această ofertă nu este un curs.|This offer is not a course.
Укажите бренд или организацию.|Introduceți brandul sau organizația.|Enter a brand or organization.
Укажите формат модельной работы.|Indicați formatul proiectului de modeling.|Choose the model project format.
Укажите предполагаемую дату проекта.|Indicați data estimată a proiectului.|Enter a proposed project date.
Добавьте краткий бриф проекта.|Adăugați un brief scurt al proiectului.|Add a short project brief.
Укажите город.|Indicați orașul.|Enter your city.
Выберите уровень опыта.|Alegeți nivelul de experiență.|Choose your experience level.
Проверьте дату.|Verificați data.|Check the date.
Проверьте время.|Verificați ora.|Check the time.
Укажите название.|Introduceți denumirea.|Enter a name.
Укажите название группы.|Introduceți denumirea grupului.|Enter a group name.
Группа с таким названием уже существует.|Există deja un grup cu această denumire.|A group with this name already exists.
Группа не найдена.|Grupul nu a fost găsit.|Group not found.
Выберите группу из того же раздела.|Alegeți un grup din aceeași secțiune.|Choose a group from the same section.
Проверьте цену, продолжительность и перерыв.|Verificați prețul, durata și pauza.|Check the price, duration and break.
Проверьте цену и продолжительность.|Verificați prețul și durata.|Check the price and duration.
Предложение не найдено.|Oferta nu a fost găsită.|Offer not found.
Проверьте тип предложения и перерыв.|Verificați tipul ofertei și pauza.|Check the offer type and break.
Сначала верните услугу из архива.|Restabiliți mai întâi serviciul din arhivă.|Restore the service from the archive first.
Перед публикацией подтвердите названия и описания на RU и RO.|Înainte de publicare, confirmați denumirile și descrierile în RU și RO.|Confirm names and descriptions in RU and RO before publishing.
Неизвестное направление.|Direcție necunoscută.|Unknown category.
Неизвестный тип предложения.|Tip de ofertă necunoscut.|Unknown offer type.
Страница опубликована|Pagina este publicată|Page published
''')

# Complete markup literals used by legacy editor notes. Markup itself is fixed.
for _ru, _ro, _en in (
    ('Здесь настраивается только профессиональная страница. Сами группы и цены находятся в разделе «Работа → Услуги».', 'Aici se configurează doar pagina profesională. Grupurile și prețurile sunt în Activitate → Servicii.', 'Set up your professional page here. Find service groups and prices under Work → Services.'),
    ('Сначала заполните имя, короткую историю и главное фото. Вид страницы можно проверить по кнопке «Открыть Мою Сцену».', 'Completați mai întâi numele, o poveste scurtă și fotografia principală. Previzualizați cu butonul Deschide Scena mea.', 'Start with your name, a short story and main photo. Preview the page with Open My Scene.'),
):
    register_copy(f'<div class="scena-note">{_ru}</div>', f'<div class="scena-note">{_ro}</div>', f'<div class="scena-note">{_en}</div>')
register_copy(
    '<div class="scena-service-guide"><strong>Простой порядок:</strong> добавьте услугу, выберите готовую группу или создайте новую прямо в форме. Черновик можно сохранить сразу, а перевод заполнить перед публикацией.</div>',
    '<div class="scena-service-guide"><strong>Pași simpli:</strong> adăugați un serviciu, alegeți un grup sau creați unul direct în formular. Salvați ciorna acum și completați traducerea înainte de publicare.</div>',
    '<div class="scena-service-guide"><strong>Simple steps:</strong> add a service, choose a group or create one in the form. Save a draft now and add translations before publishing.</div>',
)
register_copy('Подраздел', 'Subsecțiune', 'Subsection')
# Language-specific editor labels use one translated base and a stable code.
for _lang_code in ('RU', 'RO', 'EN'):
    for _ru_base, _ro_base, _en_base in (
        ('Заголовок', 'Titlu', 'Title'), ('Название', 'Denumire', 'Name'),
        ('Описание', 'Descriere', 'Description'), ('Текст', 'Text', 'Text'),
        ('Публичное имя', 'Nume public', 'Public name'),
        ('Личный посыл / подпись', 'Mesaj personal / descriere', 'Personal message / caption'),
        ('Описание для доступности', 'Descriere accesibilă', 'Accessibility description'),
        ('Описание фотографии', 'Descrierea fotografiei', 'Photo description'),
        ('О себе и своих образах', 'Despre mine și imaginile mele', 'About me and my images'),
        ('Что ещё важно обо мне — необязательно', 'Ce mai contează despre mine — opțional', 'More about me — optional'),
        ('Текст кнопки записи', 'Textul butonului de programare', 'Booking button text'),
        ('Заголовок страницы записи', 'Titlul paginii de programare', 'Booking page title'),
        ('Описание страницы записи', 'Descrierea paginii de programare', 'Booking page description'),
    ):
        register_copy(f'{_ru_base} {_lang_code}', f'{_ro_base} {_lang_code}', f'{_en_base} {_lang_code}')

_load_rows(r'''
Обложки используют ваши фотографии автоматически. Название и описание каждого курса редактируются в «Работа → Услуги».|Copertele folosesc automat fotografiile dvs. Titlul și descrierea fiecărui curs se editează în Activitate → Servicii.|Cover images use your photos automatically. Edit each course title and description under Work → Services.
Кадр публикуется только после включения видимости, заполнения обеих языковых версий и отметки «Языковые версии проверены». Остальное сохраняется как черновик.|Cadrul se publică după activarea afișării, completarea versiunilor și confirmarea verificării. Restul se salvează ca ciornă.|A frame is published when visibility is enabled, language versions are complete and checked. Otherwise, it remains a draft.
Журнал уведомлений: статус доставки указан у каждого сообщения.|Istoricul notificărilor: starea livrării este indicată pentru fiecare mesaj.|Notification history: each message shows its delivery status.
Языковые версии проверены|Versiunile lingvistice sunt verificate|Language versions checked
Кнопка записи|Buton de programare|Booking button
Текст кнопки · RU|Textul butonului · RU|Button text · RU
Баннер страницы записи|Coperta paginii de programare|Booking page banner
Имя и фамилия · RU|Nume și prenume · RU|Full name · RU
Professional в навигации и на Сцене|Professional în navigare și pe Scena mea|Professional in navigation and on My Scene
Model в навигации и на Сцене|Model în navigare și pe Scena mea|Model in navigation and on My Scene
Сохранить баннер|Salvează coperta|Save banner
Баннер сохранён.|Coperta a fost salvată.|Banner saved.
Укажите адрес, по которому ваши страницы открываются у клиентов.|Introduceți adresa la care clienții pot deschide paginile dvs.|Enter the address clients use to open your pages.
Запись по времени — календарь; курс — предварительная запись; обращение — согласование без календаря.|Programare la oră — calendar; curs — preînscriere; cerere — stabilire fără calendar.|Timed appointment — calendar; course — preregistration; inquiry — arrange details without a calendar.
Начало|Început|Start
Конец|Sfârșit|End
Перерыв с|Pauză de la|Break from
Перерыв до|Pauză până la|Break until
Дополнительно с|Ore suplimentare de la|Extra hours from
Дополнительно до|Ore suplimentare până la|Extra hours until
Язык|Limbă|Language
Идентификатор страницы|Identificatorul paginii|Page identifier
Это короткое имя для переноса страницы на платформу. Рабочие ссылки и QR-коды находятся в разделе «Продвижение → QR-коды».|Este un nume scurt pentru transferul paginii pe platformă. Linkurile și codurile QR sunt în Promovare → Coduri QR.|This is a short name for transferring your page to the platform. Find working links and QR codes under Promotion → QR codes.
Заголовок|Titlu|Title
Описание|Descriere|Description
По горизонтали, %|Pe orizontală, %|Horizontal, %
По вертикали, %|Pe verticală, %|Vertical, %
Знакомство|Prezentare|Introduction
Ваши образы|Imaginile dvs.|Your images
Смотреть образы|Vezi imaginile|View images
Пригласить в проект|Invită în proiect|Invite to a project
За каждым образом — я.|În spatele fiecărei imagini sunt eu.|Behind every image, it's me.
Здесь начинается моя модельная история. В этой подборке — творческие образы, подготовленные для меня: настроение, характер и движение. Через них я рассказываю о себе.|Aici începe povestea mea ca model. Această selecție cuprinde imagini creative pregătite pentru mine: stare, caracter și mișcare. Prin ele povestesc despre mine.|My modeling story begins here. These creative images were prepared for me: mood, character and movement. Through them, I tell my story.
Портрет для знакомства с моделью|Portret de prezentare a modelului|Introduction portrait of the model
''')

_load_rows(r'''
Все|Toate|All
Курсы|Cursuri|Courses
Модельный путь|Parcurs Model|Model path
Все пути|Toate parcursurile|All paths
Телефон|Telefon|Phone
Организация|Organizație|Organization
Услуга / формат|Serviciu / format|Service / format
Дата и время|Data și ora|Date and time
Опыт|Experiență|Experience
Сообщение|Mesaj|Message
Удержание до|Rezervat temporar până la|Held until
Путь|Parcurs|Path
Имя|Nume|Name
Услуга|Serviciu|Service
Время|Ora|Time
Статус обновлён; соответствующее SMS добавлено в очередь, если статус требует сообщения.|Starea a fost actualizată; SMS-ul corespunzător a fost adăugat în coadă, dacă este necesar.|Status updated. A corresponding SMS was queued if this status requires a notification.
Укажите публичное имя.|Introduceți numele public.|Enter your public name.
Уникальный адрес может содержать буквы, цифры, дефис и подчёркивание.|Adresa unică poate conține litere, cifre, cratimă și subliniere.|The unique address can contain letters, numbers, hyphens and underscores.
Адрес может содержать буквы, цифры, дефис и подчёркивание.|Adresa poate conține litere, cifre, cratimă și subliniere.|The address can contain letters, numbers, hyphens and underscores.
Для публикации «Моей Сцены» нужны главное фото, тексты RU/RO и подтверждение перевода.|Pentru publicarea Scenei mele sunt necesare fotografia principală, textele RU/RO și confirmarea traducerii.|Publishing My Scene requires a main photo, RU/RO text and confirmed translations.
Для профессиональной страницы заполните и подтвердите версии RU/RO.|Completați și confirmați versiunile RU/RO ale paginii profesionale.|Complete and confirm RU/RO versions of your professional page.
Для Model заполните и подтвердите версии RU/RO.|Completați și confirmați versiunile RU/RO pentru Model.|Complete and confirm the Model RU/RO versions.
Для публикации заполните и подтвердите текст RU/RO.|Pentru publicare, completați și confirmați textul RU/RO.|Complete and confirm the RU/RO text before publishing.
Профиль сохранён.|Profilul a fost salvat.|Profile saved.
Моя Сцена сохранена.|Scena mea a fost salvată.|My Scene saved.
Профессиональная страница сохранена.|Pagina profesională a fost salvată.|Professional page saved.
Настройки Model сохранены.|Setările Model au fost salvate.|Model settings saved.
У каждого кадра должен быть уникальный номер порядка от 1 до 5.|Fiecare cadru trebuie să aibă un număr unic de la 1 la 5.|Each frame must have a unique order number from 1 to 5.
Первый кадр должен быть видимым и подтверждённым.|Primul cadru trebuie să fie vizibil și confirmat.|The first frame must be visible and approved.
Model-лендинг сохранён.|Pagina Model a fost salvată.|Model landing page saved.
Публичный адрес сохранён; QR-коды обновлены.|Adresa publică a fost salvată; codurile QR au fost actualizate.|Public address saved; QR codes updated.
Запись к мастеру|Programare la specialist|Book an appointment
В архиве|Arhivată|Archived
Скрыта группой|Ascunsă de grup|Hidden by group
Опубликована|Publicată|Published
Скрыта|Ascunsă|Hidden
Черновик|Ciornă|Draft
Клиент выбирает свободную дату и время.|Clientul alege o dată și o oră disponibile.|The client chooses an available date and time.
Клиент оставляет предварительную заявку на обучение.|Clientul trimite o cerere preliminară pentru curs.|The client submits a course preregistration request.
Клиент описывает задачу, а детали согласовываются лично.|Clientul descrie solicitarea, iar detaliile se stabilesc personal.|The client describes their needs and the details are agreed personally.
Архив услуг|Arhiva serviciilor|Service archive
Текущие услуги|Servicii curente|Current services
Ваши услуги|Serviciile dvs.|Your services
Здесь находятся услуги, которые можно восстановить или удалить навсегда.|Aici sunt serviciile care pot fi restabilite sau șterse definitiv.|Here are services you can restore or permanently delete.
Клиент видит только услуги со статусом «Опубликована».|Clientul vede doar serviciile cu starea Publicată.|Clients see only services marked Published.
Основные услуги · создастся автоматически|Servicii principale · se creează automat|Core services · created automatically
Создать новую группу|Creează un grup nou|Create a new group
Услуга сохранена и опубликована.|Serviciul a fost salvat și publicat.|Service saved and published.
Услуга сохранена как черновик.|Serviciul a fost salvat ca ciornă.|Service saved as a draft.
Архив пуст.|Arhiva este goală.|The archive is empty.
Здесь пока нет услуг. Нажмите «Добавить услугу».|Nu sunt servicii aici. Apăsați Adaugă serviciu.|No services yet. Select Add service.
Без группы|Fără grup|No group
<span>Группа скрыта от клиентов</span>|<span>Grupul este ascuns clienților</span>|<span>Group hidden from clients</span>
Услуга восстановлена как скрытая.|Serviciul a fost restabilit ca ascuns.|Service restored as hidden.
Удаление необратимо и потребует подтверждения.|Ștergerea este definitivă și necesită confirmare.|Deletion is permanent and requires confirmation.
Завершить|Finalizează|Finish
Скрыть|Ascunde|Hide
Опубликовать|Publică|Publish
Услуга скрыта от клиентов.|Serviciul este ascuns clienților.|Service hidden from clients.
Услуга опубликована.|Serviciul a fost publicat.|Service published.
Услуга отправлена в архив.|Serviciul a fost arhivat.|Service archived.
Услуга удалена навсегда.|Serviciul a fost șters definitiv.|Service permanently deleted.
Изменения сохранены.|Modificările au fost salvate.|Changes saved.
Группа сохранена.|Grupul a fost salvat.|Group saved.
Скрыть группу|Ascunde grupul|Hide group
Показать группу|Afișează grupul|Show group
Группа скрыта вместе со своими услугами.|Grupul și serviciile sale sunt ascunse.|The group and its services are hidden.
Группа снова видна клиентам.|Grupul este din nou vizibil clienților.|The group is visible to clients again.
Понедельник|Luni|Monday
Вторник|Marți|Tuesday
Среда|Miercuri|Wednesday
Четверг|Joi|Thursday
Пятница|Vineri|Friday
Суббота|Sâmbătă|Saturday
Воскресенье|Duminică|Sunday
Пн|Lu|Mon
Вт|Ma|Tue
Ср|Mi|Wed
Чт|Jo|Thu
Пт|Vi|Fri
Сб|Sâ|Sat
Вс|Du|Sun
График сохранён; кнопки времени пересчитаны автоматически.|Programul a fost salvat; orele disponibile au fost recalculate automat.|Schedule saved; available times recalculated automatically.
Добавить часы|Adaugă ore|Add hours
Закрыть весь день|Închide întreaga zi|Close the whole day
Исключение графика добавлено.|Excepția de program a fost adăugată.|Schedule exception added.
выходной|zi liberă|day off
Исключение графика удалено.|Excepția de program a fost ștearsă.|Schedule exception deleted.
Событие|Eveniment|Event
Получатель|Destinatar|Recipient
Вы|Dvs.|You
Обзор|Prezentare generală|Overview
Промпты|Prompturi|Prompts
Подключения|Conexiuni|Connections
Ваша работа сегодня|Activitatea dvs. de astăzi|Your work today
Записи, услуги и заказы — начните с важного.|Programări, servicii și comenzi — începeți cu ce contează.|Bookings, services and orders — start with what matters.
Ваш образ, ваш магазин, ваши возможности.|Imaginea dvs., magazinul dvs., posibilitățile dvs.|Your image, your shop, your possibilities.
Ваш Market|Marketul dvs.|Your Market
Товары, которые вы рекомендуете. Заказы от ваших клиентов.|Produsele pe care le recomandați. Comenzi de la clienții dvs.|Products you recommend. Orders from your clients.
Выберите сцену, добавьте свои детали и сохраните задание для ИИ.|Alegeți scena, adăugați detaliile și salvați instrucțiunile pentru AI.|Choose a scene, add your details and save your AI prompt.
Настройка ассистента и связи с командой.|Configurarea asistentului și a legăturii cu echipa.|Configure your assistant and contact with the team.
SCENA — Моя Сцена|SCENA — Scena mea|SCENA — My Scene
Неизвестное назначение изображения.|Destinație necunoscută a imaginii.|Unknown image destination.
Размер одного изображения не должен превышать 20 МБ.|O imagine nu poate depăși 20 MB.|Each image must be no larger than 20 MB.
Файл не является поддерживаемым изображением.|Fișierul nu este o imagine acceptată.|This file is not a supported image.
Неизвестное портфолио.|Portofoliu necunoscut.|Unknown portfolio.
Выберите фотографию размером до 20 МБ.|Alegeți o fotografie de până la 20 MB.|Choose a photo up to 20 MB.
Выберите фотографию JPG, PNG или WebP.|Alegeți o fotografie JPG, PNG sau WebP.|Choose a JPG, PNG or WebP photo.
Для портфолио нужна неподвижная фотография.|Portofoliul necesită o fotografie statică.|The portfolio requires a still photo.
Фотография слишком маленькая: нужна длинная сторона от 600 px и короткая от 400 px. Выберите более крупный оригинал.|Fotografia este prea mică: latura lungă trebuie să aibă cel puțin 600 px, iar cea scurtă 400 px. Alegeți un original mai mare.|This photo is too small: use at least 600 px on the long side and 400 px on the short side. Choose a larger original.
Не удалось открыть фотографию. Выберите другой JPG, PNG или WebP.|Fotografia nu a putut fi deschisă. Alegeți alt JPG, PNG sau WebP.|Could not open the photo. Choose another JPG, PNG or WebP.
Не удалось сохранить портфолио. Перезапустите SCENA и повторите попытку.|Portofoliul nu a putut fi salvat. Reporniți SCENA și încercați din nou.|Could not save the portfolio. Restart SCENA and try again.
В портфолио доступно 12 кадров.|Portofoliul permite 12 cadre.|The portfolio supports 12 frames.
Выберите фотографию или удаление кадра.|Alegeți o fotografie sau eliminarea cadrului.|Choose a photo or remove the frame.
Эта фотография недоступна. Выберите другой сохранённый оригинал.|Această fotografie nu este disponibilă. Alegeți alt original salvat.|This photo is unavailable. Choose another saved original.
Кадр убран из портфолио. Оригинал сохранён.|Cadrul a fost eliminat din portofoliu. Originalul este păstrat.|Frame removed from the portfolio. Original preserved.
Сохранённая фотография возвращена в портфолио.|Fotografia salvată a fost restabilită în portofoliu.|Saved photo restored to the portfolio.
Фотография сохранена в портфолио.|Fotografia a fost salvată în portofoliu.|Photo saved to the portfolio.
Подготовить публичный пакет|Pregătește pachetul public|Prepare public package
Создать резервную копию|Creează o copie de rezervă|Create backup
Только опубликованные страницы, услуги, посты и связанные сохранённые материалы. Клиенты, переписка и черновики сюда не входят.|Doar pagini, servicii, publicații și materiale asociate publicate. Clienții, conversațiile și ciornele nu sunt incluse.|Only published pages, services, posts and associated saved media. Clients, conversations and drafts are excluded.
Сохраните свою Сцену: настройки, услуги, записи, публикации и сохранённые фотографии. Копия содержит личные данные клиентов и переписку — храните её у себя.|Salvați Scena dvs.: setări, servicii, programări, publicații și fotografii. Copia conține date personale și conversații — păstrați-o în siguranță.|Back up your Scene: settings, services, bookings, posts and saved photos. The backup contains clients' personal details and conversations — keep it private.
Подготавливаем материалы…|Pregătim materialele…|Preparing your materials…
Скачать публичный пакет|Descarcă pachetul public|Download public package
Скачать резервную копию|Descarcă copia de rezervă|Download backup
Проверяем архив…|Verificăm arhiva…|Checking archive…
Это публичный пакет. Для восстановления нужна полная резервная копия SCENA.|Acesta este un pachet public. Pentru restaurare este necesară o copie de rezervă completă SCENA.|This is a public package. Restoration requires a complete SCENA backup.
Восстанавливаем вашу Сцену…|Restabilim Scena dvs.…|Restoring your Scene…
''')

# Platform-authored fragments for explicit f-string localization. Keep dynamic
# names, counts and customer text outside these calls.
_load_rows(r'''
Заявка №|Cererea #|Request #
 сохранена. Это запрос: решение и условия подтверждаются отдельно.| a fost salvată. Decizia și condițiile se confirmă separat.| saved. Participation and terms are confirmed separately.
 сохранена. Мастер свяжется с вами, чтобы обсудить программу и подтвердить место.| a fost salvată. Specialistul vă va contacta pentru a discuta programul și a confirma locul.| saved. The specialist will contact you to discuss the program and confirm your place.
Статус: |Stare: |Status: 
 · Создано: | · Creată: | · Created: 
Сохранено фотографий: |Fotografii salvate: |Photos saved: 
: используется фирменное изображение SCENA|: se folosește imaginea SCENA|: using the SCENA image
Кадр №|Cadrul #|Frame #
: для подтверждения нужны фотография, посыл и описание на RU/RO.|: pentru confirmare sunt necesare fotografia, mesajul și descrierea RU/RO.|: confirmation requires a photo, message and description in RU/RO.
 · скрыта| · ascunsă| · hidden
 услуг</span>| servicii</span>| services</span>
 мин.| min.| min.
Есть связанные заявки: |Cereri asociate: |Linked requests: 
. Для сохранения истории эту услугу нельзя удалить.|. Pentru a păstra istoricul, acest serviciu nu poate fi șters.|. This service cannot be deleted because its request history must be preserved.
Связанных заявок: |Cereri asociate: |Linked requests: 
. Услуга хранится в архиве для истории клиентов.|. Serviciul este păstrat în arhivă pentru istoricul clienților.|. The service stays archived to preserve client history.
» будет удалена навсегда. Восстановить её после этого невозможно.|» va fi șters definitiv și nu poate fi restabilit.|” will be permanently deleted and cannot be restored.
Да, удалить «|Da, șterge «|Yes, delete “
» навсегда|» definitiv|” permanently
Изменить: |Editează: |Edit: 
Открыть: |Deschide: |Open: 
Подготовлено сообщений: **|Mesaje pregătite: **|Prepared messages: **
Осталось |Au rămas |Remaining: 
 дней · действует до | zile · valabil până la | days · valid until 
Период завершён |Perioada s-a încheiat la |Period ended on 
 · можно подать новую заявку| · puteți trimite o cerere nouă| · you can submit a new application
Образ |Imaginea |Look 
Кадр |Cadrul |Frame 
 из | din | of 
 кадров. Посетитель выбирает миниатюру и рассматривает фотографию целиком.| cadre. Vizitatorul alege miniatura și vede fotografia completă.| frames. Visitors choose a thumbnail and view the complete photo.
Выбрать из сохранённых фотографий · |Alege din fotografiile salvate · |Choose from saved photos · 
Фотография |Fotografia |Photo 
Использовать в кадре |Folosește în cadrul |Use in frame 
Файлов: |Fișiere: |Files: 
 · Материалов: | · Materiale: | · Media files: 
 · Размер после распаковки: | · Dimensiune după dezarhivare: | · Unpacked size: 
 МБ| MB| MB
Пакет подготовлен: |Pachet pregătit: |Package prepared: 
''')
register_copy('</strong><br><small>Фото добавляется в кабинете</small></div></div>', '</strong><br><small>Fotografia se adaugă în cabinet</small></div></div>', '</strong><br><small>Add a photo in your workspace</small></div></div>')
register_copy('[← Открыть публичную страницу](', '[← Deschide pagina publică](', '[← Open public page](')
register_copy('<div class="scena-pro-banner" role="status" aria-label="Статус подписки PRO"><div><strong>SCENA · ', '<div class="scena-pro-banner" role="status" aria-label="Starea abonamentului PRO"><div><strong>SCENA · ', '<div class="scena-pro-banner" role="status" aria-label="PRO subscription status"><div><strong>SCENA · ')
register_copy('<section class="scena-conversation" aria-label="История общения">', '<section class="scena-conversation" aria-label="Istoricul conversației">', '<section class="scena-conversation" aria-label="Conversation history">')
_load_rows(r'''
Компьютер|Computer|Desktop
Горизонталь|Orizontală|Horizontal
Вертикаль|Verticală|Vertical
Фотография знакомства|Fotografie de prezentare|Introduction photo
Оставить текущую фотографию|Păstrează fotografia actuală|Keep current photo
Начальный портрет|Portret inițial|Initial portrait
Сохранённый портрет |Portret salvat |Saved portrait 
Не удалось сохранить визитку. Повторите попытку.|Prezentarea nu a fost salvată. Încercați din nou.|Could not save the introduction. Try again.
Визитка сохранена.|Prezentarea a fost salvată.|Introduction saved.
''')

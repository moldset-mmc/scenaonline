"""The platform podium: a public showcase of platform tenants.

Two groups are shown separately, because they are different products:

- sites (level 2): a tenant with its own database, accounts, booking and shop,
  deployed in the tenant's own Vercel and GitHub accounts;
- cards (level 1): a single-page card that lives in this repository and is
  mounted by host, without a database.

The data is a module constant on purpose: a JSON asset would have to be added
to the function bundle explicitly, while Python is always shipped. When the
registry grows, this moves into the platform database.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from tornado.routing import Matcher, Rule
from tornado.web import RequestHandler

ORIGIN = 'https://scena.life'


@dataclass(frozen=True)
class Tenant:
    brand: str
    name_lat: str
    name_ru: str
    city_lat: str
    city_ru: str
    host: str
    kind: str          # 'site' | 'card'
    status: str        # 'live' | 'demo'
    purpose: str       # key into COPY['purpose']

    @property
    def url(self) -> str:
        return f'https://{self.host}/'


# Tenants are separate brands; the only thing they share is the SCENA platform.
# The live makeup project belongs to its own master, the demo site shows
# fictional people, and no brand is borrowed from another site.
TENANTS = (
    Tenant('Makeup Studio Life', 'Masha Kravcenko', 'Маша Кравченко', 'Chișinău', 'Кишинёв',
           'makeup.scena.life', 'site', 'live', 'site_live'),
    Tenant('MB Studio', 'Milana Borzova', 'Милана Борзова', 'Chișinău', 'Кишинёв',
           'mbstudio.scena.life', 'site', 'demo', 'site_demo'),
    Tenant('Sofi Leroux', 'Sofia Leroux', 'София Леру', 'Chișinău', 'Кишинёв',
           'sofileroux.scena.life', 'card', 'demo', 'card_demo'),
)

COPY = {
    'ro': {
        'lang': 'ro',
        'title': 'Podiumul SCENA.LIFE — participanții platformei',
        'h1': 'Podiumul',
        'lead': 'Aici stau scenele platformei. Fiecare participant are propriul subdomeniu: '
                'un site cu bază de date ori o carte de vizită digitală.',
        'sites': 'Site-uri',
        'sites_note': 'Cu bază de date: conturi, programări și magazin.',
        'cards': 'Cărți de vizită',
        'cards_note': 'O singură pagină, fără bază de date.',
        'open': 'Deschide',
        'live': 'activ',
        'demo': 'demonstrativ',
        'cta': 'Creează-ți scena',
        'cta_line': 'Scena ta încă e liberă?',
        'back': 'Acasă',
        'nav_platform': 'Platforma',
        'nav_podium': 'Podium',
        'purpose': {
            'site_live': 'Site de lucru al maestrului: servicii, programări, magazin.',
            'site_demo': 'Demonstrație de portofoliu: cum arată un site complet.',
            'card_demo': 'Carte de vizită demonstrativă: o singură pagină.',
        },
    },
    'ru': {
        'lang': 'ru',
        'title': 'Площадка SCENA.LIFE — участники платформы',
        'h1': 'Площадка',
        'lead': 'Здесь стоят сцены платформы. У каждого участника свой субдомен: '
                'сайт с базой данных или цифровая визитка.',
        'sites': 'Сайты',
        'sites_note': 'С базой данных: аккаунты, запись и магазин.',
        'cards': 'Визитки',
        'cards_note': 'Одна страница, без базы данных.',
        'open': 'Открыть',
        'live': 'живой',
        'demo': 'демонстрационный',
        'cta': 'Создать свою сцену',
        'cta_line': 'Твоя сцена ещё свободна?',
        'back': 'На главную',
        'nav_platform': 'Платформа',
        'nav_podium': 'Площадка',
        'purpose': {
            'site_live': 'Рабочий сайт мастера: услуги, запись, магазин.',
            'site_demo': 'Демонстрация портфолио: как выглядит полный сайт.',
            'card_demo': 'Демонстрационная визитка: одна страница.',
        },
    },
}

STYLE = """
:root{--plum-1:#4a0f2e;--plum-2:#7b1440;--plum-3:#a3174d;--ink:#0f0a0d;
--paper:#f7f0ea;--pink:#f3c7d6;--accent:#ffd9e6;--muted:#c9a9b6}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
font-family:"Inter","Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.hero{position:relative;overflow:hidden;padding:28px 56px 64px;
background:radial-gradient(1100px 620px at 76% 4%,rgba(163,23,77,.5),transparent 62%),
linear-gradient(155deg,var(--plum-1),var(--plum-2) 50%,var(--plum-3))}
.hero::after{content:"SCENA";position:absolute;left:-2%;bottom:-26%;font-family:Georgia,serif;
font-size:280px;letter-spacing:-.04em;color:rgba(255,255,255,.05);white-space:nowrap;pointer-events:none}
nav{position:relative;z-index:2;display:flex;justify-content:space-between;align-items:center;
font-size:13px;letter-spacing:.06em}
.logo{font-weight:700;letter-spacing:.14em;font-size:15px}
.logo em{color:var(--pink);font-style:normal}
.nav-right{display:flex;gap:20px;align-items:center;color:#f0dae2}
.nav-right a{color:#f0dae2;text-decoration:none;border-bottom:1px solid transparent;padding-bottom:2px}
.nav-right a:hover{border-bottom-color:rgba(255,255,255,.5)}
.nav-right a.on{border-bottom-color:#fff}
.lang{border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:5px 12px;font-size:12px;
letter-spacing:.12em;color:#f0dae2;text-decoration:none}
h1{position:relative;z-index:2;font-family:Georgia,"Times New Roman",serif;font-weight:400;
font-size:66px;line-height:1;margin:56px 0 18px;letter-spacing:-.015em}
.lead{position:relative;z-index:2;max-width:620px;font-size:19px;line-height:1.55;color:#f6e6ec;margin:0}
main{max-width:1180px;margin:0 auto;padding:56px 56px 24px}
section{margin:0 0 56px}
h2{font-family:Georgia,serif;font-weight:400;font-size:32px;margin:0 0 6px}
.sub{color:var(--muted);font-size:15px;margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
.tenant{border:1px solid #2a1d23;border-radius:14px;padding:22px;background:#150d11;
display:flex;flex-direction:column;gap:8px;text-decoration:none;color:inherit}
.tenant:hover{border-color:#5a3b46;background:#1a1015}
.brand{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--pink)}
.name{font-family:Georgia,serif;font-size:24px;line-height:1.2}
.meta{font-size:13px;color:var(--muted)}
.row{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:13px}
.host{color:var(--accent);text-decoration:none;border-bottom:1px solid rgba(255,217,230,.4)}
.badge{border:1px solid #4a3540;border-radius:999px;padding:3px 10px;font-size:11px;
letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.badge.live{border-color:#4f7d63;color:#a8e0bf}
.cta{margin:8px 0 64px;padding:34px;border:1px solid #2a1d23;border-radius:16px;background:#150d11;
display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}
.cta p{margin:0;font-family:Georgia,serif;font-size:24px}
.btn{background:var(--pink);color:#3c0b23;border-radius:8px;padding:14px 24px;font-size:15px;
font-weight:600;text-decoration:none}
footer{max-width:1180px;margin:0 auto;padding:0 56px 56px;color:#9d8891;font-size:13px}
footer a{color:#e9d3db}
@media (max-width:900px){
main{padding:40px 22px 16px}.hero{padding:22px 22px 48px}h1{font-size:42px;margin-top:34px}
h2{font-size:26px}.grid{grid-template-columns:1fr}footer{padding:0 22px 40px}
.hero::after{font-size:150px}
}
"""


def _page_url(locale: str) -> str:
    return f'{ORIGIN}{"/ru/podium" if locale == "ru" else "/podium"}'


def _card(tenant: Tenant, locale: str) -> str:
    c = COPY[locale]
    ru = locale == 'ru'
    status_label = c['live'] if tenant.status == 'live' else c['demo']
    badge_class = 'badge live' if tenant.status == 'live' else 'badge'
    note = c['purpose'][tenant.purpose]
    name = tenant.name_ru if ru else tenant.name_lat
    city = tenant.city_ru if ru else tenant.city_lat
    return (
        '<a class="tenant" href="' + html.escape(tenant.url, quote=True) + '">'
        '<span class="brand">' + html.escape(tenant.brand) + '</span>'
        '<span class="name">' + html.escape(name) + '</span>'
        '<span class="meta">' + html.escape(city) + ' · ' + html.escape(note) + '</span>'
        '<span class="row"><span class="host">' + html.escape(tenant.host) + '</span>'
        '<span class="' + badge_class + '">' + html.escape(status_label) + '</span></span>'
        '</a>'
    )


def render(locale: str) -> bytes:
    locale = 'ru' if locale == 'ru' else 'ro'
    c = COPY[locale]
    sites = [t for t in TENANTS if t.kind == 'site']
    cards = [t for t in TENANTS if t.kind == 'card']

    alt_ro = f'{ORIGIN}/podium'
    alt_ru = f'{ORIGIN}/ru/podium'
    self_url = _page_url(locale)

    def group(title: str, note: str, items: list[Tenant]) -> str:
        return (
            '<section><h2>' + html.escape(title) + '</h2>'
            '<p class="sub">' + html.escape(note) + '</p>'
            '<div class="grid">' + ''.join(_card(t, locale) for t in items) + '</div></section>'
        )

    return (
        '<!doctype html><html lang="' + locale + '"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>' + html.escape(c['title']) + '</title>'
        '<meta name="description" content="' + html.escape(c['lead'], quote=True) + '">'
        '<link rel="canonical" href="' + self_url + '">'
        '<link rel="alternate" hreflang="ro" href="' + alt_ro + '">'
        '<link rel="alternate" hreflang="ru" href="' + alt_ru + '">'
        '<link rel="alternate" hreflang="x-default" href="' + alt_ro + '">'
        '<meta property="og:type" content="website">'
        '<meta property="og:title" content="' + html.escape(c['title'], quote=True) + '">'
        '<meta property="og:description" content="' + html.escape(c['lead'], quote=True) + '">'
        '<meta property="og:url" content="' + self_url + '">'
        '<style>' + STYLE + '</style></head><body>'
        '<div class="hero"><nav>'
        '<div class="logo">SCENA<span>.LIFE</span> <em>*</em></div>'
        '<div class="nav-right"><a href="/' + ('ru/' if locale == 'ru' else '') + '">' + html.escape(c['back']) + '</a>'
        '<a class="on" href="' + self_url + '">' + html.escape(c['nav_podium']) + '</a>'
        '<a class="lang" href="' + (alt_ro if locale == 'ru' else alt_ru) + '">'
        + ('RO' if locale == 'ru' else 'RU') + '</a></div></nav>'
        '<h1>' + html.escape(c['h1']) + '</h1>'
        '<p class="lead">' + html.escape(c['lead']) + '</p></div>'
        '<main>'
        + group(c['sites'], c['sites_note'], sites)
        + group(c['cards'], c['cards_note'], cards)
        + '<div class="cta"><p>' + html.escape(c['cta_line']) + '</p>'
        '<a class="btn" href="/newcard">' + html.escape(c['cta']) + '</a></div>'
        '</main>'
        '<footer>SCENA.LIFE · <a href="' + alt_ro + '">Podium</a> · '
        '<a href="' + alt_ru + '">Площадка</a></footer>'
        '</body></html>'
    ).encode('utf-8')

class PodiumMatcher(Matcher):
    """Public pages of the podium, in both platform languages."""

    PATHS = frozenset(('/podium', '/podium/', '/ru/podium', '/ru/podium/'))

    def match(self, request):
        if request.method not in ('GET', 'HEAD'):
            return None
        return {} if request.path in self.PATHS else None


class Podium(RequestHandler):
    def get(self):
        locale = 'ru' if self.request.path.startswith('/ru/') else 'ro'
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        self.set_header('X-Robots-Tag', 'index, follow, max-image-preview:large')
        self.set_header('Cache-Control', 'public, max-age=0, must-revalidate')
        self.set_header('X-Content-Type-Options', 'nosniff')
        self.finish(render(locale))

    def head(self):
        self.get()


def podium_rules():
    return [Rule(PodiumMatcher(), Podium)]


def sitemap_xml(origin: str) -> str:
    """Sitemap entries for the podium, with their own hreflang alternates."""
    pairs = [('ro', '/podium'), ('ru', '/ru/podium'), ('x-default', '/podium')]
    alternates = ''.join(
        f'<xhtml:link rel="alternate" hreflang="{lang}" href="{origin}{url}" />' for lang, url in pairs
    )
    return ''.join('<url><loc>' + origin + url + '</loc>' + alternates + '</url>'
                   for url in ('/podium', '/ru/podium'))

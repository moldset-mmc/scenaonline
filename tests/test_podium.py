"""The podium lists platform tenants in two separate groups."""
import unittest

from scena_web import podium


class PodiumRenderTest(unittest.TestCase):
    def test_render_lists_every_tenant(self):
        html = podium.render('ro').decode('utf-8')
        self.assertEqual(html.count('class="tenant"'), len(podium.TENANTS))
        for tenant in podium.TENANTS:
            self.assertIn(tenant.host, html)
            self.assertIn(f'https://{tenant.host}/', html)

    def test_groups_are_separated(self):
        html = podium.render('ro').decode('utf-8')
        sites = [t for t in podium.TENANTS if t.kind == 'site']
        cards = [t for t in podium.TENANTS if t.kind == 'card']
        self.assertEqual(html.count('class="tenant"'), len(sites) + len(cards))
        self.assertIn('Site-uri', html)
        self.assertIn('Cărți de vizită', html)

    def test_russian_page_has_own_canonical(self):
        html = podium.render('ru').decode('utf-8')
        self.assertIn('<html lang="ru">', html)
        self.assertIn('https://scena.life/ru/podium', html)
        self.assertIn('Площадка', html)

    def test_unknown_locale_falls_back_to_romanian(self):
        html = podium.render('en').decode('utf-8')
        self.assertIn('<html lang="ro">', html)

    def test_purpose_lines_differ_per_level(self):
        html = podium.render('ro').decode('utf-8')
        self.assertIn(podium.COPY['ro']['purpose']['site_live'], html)
        self.assertIn(podium.COPY['ro']['purpose']['site_demo'], html)
        self.assertIn(podium.COPY['ro']['purpose']['card_demo'], html)

    def test_sitemap_covers_both_languages(self):
        xml = podium.sitemap_xml('https://scena.life')
        self.assertIn('https://scena.life/podium', xml)
        self.assertIn('https://scena.life/ru/podium', xml)
        self.assertIn('hreflang="ru"', xml)
        self.assertIn('hreflang="x-default"', xml)

    def test_matcher_answers_only_podium_paths(self):
        class Request:
            method = 'GET'

            def __init__(self, path):
                self.path = path

        matcher = podium.PodiumMatcher()
        for path in ('/podium', '/podium/', '/ru/podium', '/ru/podium/'):
            self.assertEqual(matcher.match(Request(path)), {}, path)
        for path in ('/', '/ru/', '/newcard', '/podium/x'):
            self.assertIsNone(matcher.match(Request(path)), path)

    def test_names_follow_locale(self):
        ro = podium.render('ro').decode('utf-8')
        ru = podium.render('ru').decode('utf-8')
        self.assertIn('Masha Kravcenko', ro)
        self.assertNotIn('Маша Кравченко', ro)
        self.assertIn('Маша Кравченко', ru)
        self.assertIn('Милана Борзова', ru)
        self.assertIn('Кишинёв', ru)
        self.assertNotIn('Кишинёв', ro)

    def test_tenant_portraits_are_served_from_podium_assets(self):
        html = podium.render('ro').decode('utf-8')
        self.assertEqual(html.count('class="thumb"'), len(podium.TENANTS))
        self.assertIn('/podium/assets/milana-borzova.jpg', html)
        self.assertIn('/podium/assets/sofi-leroux.jpg', html)
        # A tenant without a portrait falls back to a monogram, not a broken image.
        self.assertIn('class="mono">M<', html)
        for tenant in podium.TENANTS:
            if tenant.photo:
                self.assertTrue((podium.ASSETS / tenant.photo).is_file(), tenant.photo)

    def test_brands_are_independent(self):
        for locale in ('ro', 'ru'):
            html = podium.render(locale).decode('utf-8')
            self.assertIn('Makeup Studio Life', html)
            self.assertIn('MB Studio', html)
            # No brand is borrowed from another site.
            self.assertNotIn('M|B', html)
            self.assertNotIn('Maria Cravcenco', html)


if __name__ == '__main__':
    unittest.main()

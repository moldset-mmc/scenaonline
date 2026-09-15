"""Language switches preserve a selected record while excluding private state."""
import unittest
from unittest.mock import patch

from scena_i18n import language_query, translate_literaltext


class LanguageNavigationTest(unittest.TestCase):
    def test_detail_context_survives_in_every_locale(self):
        cases = (
            {'page':'admin','section':'work','view':'requests','request':'42'},
            {'page':'admin','section':'pages','view':'shop','order':'fixture-order','orders':'1'},
            {'page':'admin','section':'photos','view':'library','photo':'a'*64,'target':'model_intro_image','mode':'replace','filter':'model'},
            {'page':'post','post':'42'},
            {'page':'portfolio','view':'model'},
            {'page':'booking','service':'3'},
            {'page':'course','service':'4'},
            {'page':'posts','destination':'model'},
        )
        for query in cases:
            for locale in ('ru','ro','en'):
                with self.subTest(query=query, locale=locale):
                    self.assertEqual(language_query({**query, 'lang':'ru'}, locale), {**query, 'lang':locale})

    def test_auth_post_and_unrelated_context_never_leak(self):
        query = {'page':'admin','section':'photos','view':'library','photo':'abc',
                 'token':'private','_token':'private','_action':'delete','password':'private',
                 'next':'https://untrusted.example','admin':'1','service':'9','utm_source':'private'}
        self.assertEqual(language_query(query, 'EN-us'), {'page':'admin','lang':'en','section':'photos','view':'library','photo':'abc'})
        self.assertEqual(language_query(query, 'ro', page='scene'), {'page':'scene','lang':'ro'})

    def test_missing_language_defaults_and_empty_context(self):
        self.assertEqual(language_query({}, 'unknown'), {'page':'scene','lang':'ru'})
        self.assertEqual(language_query({'page':'booking','service':None}, 'en'), {'page':'booking','lang':'en'})

    def test_confirmed_cabinet_gaps_are_translated(self):
        for label in ('Как настроить страницу','Контакты и ссылки','Сценарий, оформление и история Model','Канал ответа','Отправить','Позвонить','+ Новая публикация'):
            for locale in ('ro','en'):
                with self.subTest(label=label, locale=locale):
                    self.assertNotRegex(translate_literaltext(locale,label), '[А-Яа-яЁё]')


class TelegramSettingsLanguageTest(unittest.TestCase):
    def test_connection_states_render_in_the_selected_language(self):
        import scena_shop_telegram as telegram
        from scena_web.context import current, Query, RenderContext
        from scena_web.widgets import st as native_ui
        states = (
            {'connected':False, 'pending':{}},
            {'connected':False, 'pending':{'bot':'OwnerBot','username':'ownername','code':'SCENA-123'}},
            {'connected':True, 'pending':{}, 'username':'ownername','actions_ready':True},
            {'connected':True, 'pending':{}, 'username':'ownername','actions_ready':False},
        )
        for locale in ('ro','en'):
            for status in states:
                with self.subTest(locale=locale, status=status):
                    ctx = RenderContext(state={'scena_ui_locale':locale}, query=Query(page='admin',lang=locale), headers={})
                    ctx.reset(); token = current.set(ctx)
                    try:
                        with patch('scena_ui.st',native_ui), patch.object(telegram,'connection_status',return_value=status), patch.object(telegram.TelegramBotAdapter,'_call') as network:
                            telegram.render_settings('unused-fixture.db',locale)
                        self.assertNotRegex(ctx.root.render(), '[А-Яа-яЁё]')
                        network.assert_not_called()
                    finally:
                        current.reset(token)

    def test_error_translation_preserves_username_and_unknown_owner_text(self):
        from scena_shop_telegram import connection_error_text, ConnectionError
        message = 'Свежий код не найден в личном чате @Owner_123. Отправьте код указанному боту и нажмите ещё раз.'
        for locale in ('ro','en'):
            translated = connection_error_text(ConnectionError(message),locale)
            self.assertIn('@Owner_123',translated)
            self.assertNotRegex(translated,'[А-Яа-яЁё]')
            self.assertNotRegex(connection_error_text(ConnectionError('Вставьте полный токен вашего бота из @BotFather.'),locale),'[А-Яа-яЁё]')
        unknown = 'Текст владельца: не переводить автоматически'
        self.assertEqual(connection_error_text(ConnectionError(unknown),'en'),unknown)

    def test_native_chat_and_image_defaults_are_localized_without_rewriting_content(self):
        from scena_web.context import current, Query, RenderContext
        from scena_web.widgets import st
        for locale, send, alt in (('ro','Trimite','Fotografie'),('en','Send','Photo')):
            ctx = RenderContext(state={'scena_ui_locale':locale},query=Query(page='admin',lang=locale),headers={})
            ctx.reset(); token = current.set(ctx)
            try:
                st.chat_input(key='message')
                self.assertIn(send,[widget['label'] for widget in ctx.widgets.values()])
                with patch('scena_web.media.display_image',return_value='/fixture.png'):
                    st.image('fixture')
                    st.image('fixture',caption='Моя собственная подпись')
                markup = ctx.root.render()
                self.assertIn('alt="'+alt+'"',markup)
                self.assertIn('Моя собственная подпись',markup)
            finally:
                current.reset(token)


if __name__ == '__main__':
    unittest.main()

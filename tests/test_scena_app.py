import os
import sqlite3
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from streamlit.testing.v1 import AppTest
except ModuleNotFoundError:  # The core test suite can still run before UI deps install.
    AppTest = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "scena-master-standalone.py"


def element_with_label(elements, label):
    return next(element for element in elements if element.label == label)


def group_with_key(app, key):
    return next(group for group in app.get("button_group") if group.key == key)


def anchors_for_page(app, page):
    """Inspect rendered anchors, excluding CSS and unrelated labels."""
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attributes):
            values = dict(attributes)
            if tag == 'a' and parse_qs(urlparse(values.get('href', '')).query).get('page') == [page]:
                self.links.append(values)
    parser = Links()
    for element in app.markdown:
        parser.feed(element.value)
    return parser.links


@unittest.skipIf(AppTest is None, "Streamlit UI dependencies are not installed")
class ScenaAppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ui.db"
        self.old_db_path = os.environ.get("SCENA_DB_PATH")
        self.old_password = os.environ.get("SCENA_ADMIN_PASSWORD")
        os.environ["SCENA_DB_PATH"] = str(self.db_path)
        os.environ["SCENA_ADMIN_PASSWORD"] = "test-password"

    def tearDown(self):
        if self.old_db_path is None:
            os.environ.pop("SCENA_DB_PATH", None)
        else:
            os.environ["SCENA_DB_PATH"] = self.old_db_path
        if self.old_password is None:
            os.environ.pop("SCENA_ADMIN_PASSWORD", None)
        else:
            os.environ["SCENA_ADMIN_PASSWORD"] = self.old_password
        self.temp_dir.cleanup()

    def app(self, page="scene", **params):
        app = AppTest.from_file(str(APP_PATH), default_timeout=20)
        app.query_params["page"] = page
        app.query_params["lang"] = params.pop("lang", "ru")
        for key, value in params.items():
            app.query_params[key] = value
        return app.run()

    def test_separate_public_routes_render_without_exceptions(self):
        expected = {
            "scene": None,
            "portfolio": "Портфолио",
            "professional": None,
            "model": "Модель",
            "join-model": None,
            "invite-model": None,
        }
        for page, title in expected.items():
            for lang in ("ru", "ro", "en"):
                with self.subTest(page=page, lang=lang):
                    app = self.app(page, lang=lang)
                    self.assertEqual(len(app.exception), 0)
                    if lang == "ru" and page != "model" and title:
                        self.assertEqual(app.title[0].value, title)
                    markup = "\n".join(item.value for item in app.markdown)
                    if page == "scene":
                        self.assertIn("scena-editorial-scene", markup)
                        expected_name = "Мария Бараночникова" if lang == "ru" else "Maria Baranochnikova"
                        self.assertTrue(expected_name in markup, f"Scene must show its {lang} identity spelling")
                    if page == "professional":
                        self.assertIn("scena-professional-shell", markup)
                        self.assertIn("M | B Makeup Studio", markup)
                    if page in {"join-model", "invite-model"}:
                        self.assertIn('class="scena-stage-intro"', markup)
                        self.assertIn('<h1>', markup)

    def test_public_forms_create_four_distinct_crm_requests(self):
        from scena_core import generate_available_slots, list_available_dates, list_services

        booking = self.app("booking")
        service_id = int(list_services(self.db_path, "Professional", kind="appointment")[0]["id"])
        group_with_key(booking, "booking_service").set_value(service_id)
        booking.run()
        booking_date = list_available_dates(self.db_path, service_id, limit=1)[0]
        while booking.session_state["booking_month"][:7] < booking_date[:7]:
            booking.button(key="booking_month_next").click().run()
        booking.button(key=f"booking_day_{booking_date}").click().run()
        booking_time = generate_available_slots(self.db_path, service_id, booking_date)[0]
        booking.button(key=f"booking_slot_{booking_time}").click().run()
        self.assertEqual(len(booking.text_input), 0)
        booking.button(key="booking_continue").click().run()
        element_with_label(booking.text_input, "Ваше имя *").set_value("Анна")
        element_with_label(booking.text_input, "Телефон +373 *").set_value("060000001")
        element_with_label(booking.checkbox, "Согласие на обработку контактных данных *").set_value(True)
        element_with_label(booking.button, "Отправить заявку").click()
        booking.run()
        self.assertEqual(len(booking.exception), 0)
        self.assertEqual(len(booking.success), 1)

        application = self.app("join-model")
        element_with_label(application.text_input, "Ваше публичное имя *").set_value("Елена")
        element_with_label(application.text_input, "Телефон +373 *").set_value("060000002")
        element_with_label(application.text_input, "Город *").set_value("Кишинёв")
        element_with_label(application.checkbox, "Согласие на обработку контактных данных *").set_value(True)
        element_with_label(application.button, "Отправить заявку").click()
        application.run()
        self.assertEqual(len(application.exception), 0)
        self.assertEqual(len(application.success), 1)

        invitation = self.app("invite-model")
        element_with_label(invitation.text_input, "Бренд / организация *").set_value("Brand Studio")
        element_with_label(invitation.text_input, "Контактное лицо *").set_value("Ирина")
        element_with_label(invitation.text_input, "Телефон +373 *").set_value("060000003")
        element_with_label(invitation.text_area, "Краткий бриф *").set_value("Каталожная съёмка; бюджет и права согласуем отдельно.")
        element_with_label(invitation.checkbox, "Согласие на обработку контактных данных *").set_value(True)
        element_with_label(invitation.button, "Отправить приглашение").click()
        invitation.run()
        self.assertEqual(len(invitation.exception), 0)
        self.assertEqual(len(invitation.success), 1)

        course_id = int(list_services(self.db_path, "Professional", kind="course")[0]["id"])
        course = self.app("course", service=str(course_id))
        element_with_label(course.text_input, "Ваше имя *").set_value("Марина")
        element_with_label(course.text_input, "Телефон +373 *").set_value("060000004")
        element_with_label(course.checkbox, "Согласие на обработку контактных данных *").set_value(True)
        element_with_label(course.button, "Предварительно записаться").click()
        course.run()
        self.assertEqual(len(course.exception), 0)
        self.assertEqual(len(course.success), 1)

        with sqlite3.connect(self.db_path) as connection:
            paths = [
                row[0]
                for row in connection.execute(
                    "SELECT request_type FROM requests ORDER BY id"
                )
            ]
        self.assertEqual(
            paths,
            [
                "service_request",
                "model_application",
                "model_invitation",
                "course_preregistration",
            ],
        )

    def test_master_cabinet_requires_password_and_has_simple_service_navigation(self):
        app = self.app("admin", admin="1")

        self.assertEqual(app.title[0].value, "Вход в кабинет")
        self.assertEqual([tab.label for tab in app.tabs], [])
        element_with_label(app.text_input, "Пароль").set_value("test-password")
        element_with_label(app.button, "Войти").click()
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], [])
        markup = "\n".join(item.value for item in app.markdown)
        self.assertIsNotNone(
            group_with_key(app, "admin_section_navigation_work")
        )
        self.assertEqual(group_with_key(app, "admin_section_navigation_work").value, "work")
        self.assertEqual(group_with_key(app, "admin_view_navigation_work_overview").value, "overview")

        app.query_params["section"] = "work"
        app.query_params["view"] = "services"
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs], [])
        markup = "\n".join(item.value for item in app.markdown)
        self.assertTrue('scena-breadcrumbs' in markup)
        self.assertEqual(group_with_key(app, "admin_view_navigation_work_services").value, "services")
        self.assertIn("Ваши услуги", [item.value for item in app.subheader])
        self.assertIn("scena-service-guide", markup)
        self.assertIn("Работа", group_with_key(app, "admin_section_navigation_work").options)
        self.assertIn("PRO", group_with_key(app, "admin_section_navigation_work").options)
        self.assertIsNotNone(
            element_with_label(app.selectbox, "Где показывать услуги?")
        )
        self.assertIsNotNone(element_with_label(app.button, "Добавить услугу"))
        self.assertIsNotNone(element_with_label(app.radio, "Что показать?"))

    def test_admin_navigation_keeps_authenticated_session(self):
        app = self.app("admin", admin="1")
        element_with_label(app.text_input, "Пароль").set_value("test-password")
        element_with_label(app.button, "Войти").click()
        app.run()

        # Work overview is the intentional first screen after authentication.
        self.assertEqual(group_with_key(app, "admin_section_navigation_work").value, "work")
        self.assertEqual(group_with_key(app, "admin_view_navigation_work_overview").value, "overview")
        group_with_key(app, "admin_section_navigation_work").set_value("pages")
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertFalse(any(title.value == "Вход в кабинет" for title in app.title))
        self.assertEqual(app.query_params["section"], ["pages"])
        group_with_key(app, "admin_section_navigation_pages").set_value("work")
        app.run()
        self.assertEqual(app.query_params["section"], ["work"])

        group_with_key(
            app, "admin_view_navigation_work_overview"
        ).set_value("services")
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertFalse(any(title.value == "Вход в кабинет" for title in app.title))
        self.assertEqual(app.query_params["view"], ["services"])
        self.assertEqual([tab.label for tab in app.tabs], [])

    def test_scene_settings_persist_after_save_and_fresh_app_start(self):
        from scena_core import get_settings

        app = self.app(
            "admin", admin="1", section="pages", view="scene"
        )
        element_with_label(app.text_input, "Пароль").set_value("test-password")
        element_with_label(app.button, "Войти").click()
        app.run()

        element_with_label(app.text_input, "Имя и фамилия · RU").set_value(
            "Мария Бараночникова"
        )
        element_with_label(app.text_input, "Nume · RO").set_value("Maria Baranochnikova RO")
        element_with_label(app.text_input, "Name · EN").set_value("Maria Baranochnikova EN")
        element_with_label(app.text_input, "Город").set_value("Бельцы")
        element_with_label(app.text_area, "Текст RU").set_value(
            "Сохранённая история Марии."
        )
        element_with_label(app.button, "Сохранить Мою Сцену").click()
        app.run()

        self.assertTrue(
            any("Моя Сцена сохранена" in item.value for item in app.success)
        )
        saved = get_settings(self.db_path)
        self.assertEqual(saved["master_name"], "Мария Бараночникова")
        self.assertEqual(saved["master_name_ru"], "Мария Бараночникова")
        self.assertEqual(saved["master_name_ro"], "Maria Baranochnikova RO")
        self.assertEqual(saved["master_name_en"], "Maria Baranochnikova EN")
        self.assertEqual(saved["location"], "Бельцы")
        self.assertEqual(saved["bio"], "Сохранённая история Марии.")

        fresh = self.app(
            "admin", admin="1", section="pages", view="scene"
        )
        element_with_label(fresh.text_input, "Пароль").set_value("test-password")
        element_with_label(fresh.button, "Войти").click()
        fresh.run()

        self.assertEqual(
            element_with_label(fresh.text_input, "Имя и фамилия · RU").value,
            "Мария Бараночникова",
        )
        self.assertEqual(element_with_label(fresh.text_input, "Nume · RO").value, "Maria Baranochnikova RO")
        self.assertEqual(element_with_label(fresh.text_input, "Name · EN").value, "Maria Baranochnikova EN")
        self.assertEqual(
            element_with_label(fresh.text_input, "Город").value,
            "Бельцы",
        )
        self.assertEqual(
            element_with_label(fresh.text_area, "Текст RU").value,
            "Сохранённая история Марии.",
        )

    def test_scene_model_toggle_hides_both_navigation_and_main_action(self):
        from scena_core import get_settings
        scene = self.app('scene')
        self.assertEqual(len(anchors_for_page(scene, 'model')), 2)
        app = self.app('admin', admin='1', section='pages', view='scene')
        element_with_label(app.text_input, 'Пароль').set_value('test-password')
        element_with_label(app.button, 'Войти').click().run()
        element_with_label(app.get('toggle'), 'Model в навигации и на Сцене').set_value(False)
        element_with_label(app.button, 'Сохранить Мою Сцену').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(get_settings(self.db_path)['model_in_scene'], '0')
        self.assertEqual(get_settings(self.db_path)['model_published'], '1')
        fresh = self.app('scene')
        self.assertEqual(anchors_for_page(fresh, 'model'), [])
        self.assertTrue(anchors_for_page(fresh, 'booking'))
        # The visibility toggle affects entry points, preserving the published page.
        direct = self.app('model')
        self.assertFalse(direct.exception)
        element_with_label(app.get('toggle'), 'Model в навигации и на Сцене').set_value(True)
        element_with_label(app.button, 'Сохранить Мою Сцену').click().run()
        self.assertEqual(len(anchors_for_page(self.app('scene'), 'model')), 2)

    def test_romanian_public_validation_is_localized(self):
        app = self.app("join-model", lang="ro")
        element_with_label(app.text_input, "Numele public *").set_value("Elena")
        element_with_label(app.text_input, "Telefon +373 *").set_value("+40722123456")
        element_with_label(app.checkbox, "Acord pentru prelucrarea datelor de contact *").set_value(True)
        element_with_label(app.button, "Trimite cererea").click()
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            app.error[0].value,
            "Sunt acceptate doar numerele din Moldova +373.",
        )


if __name__ == "__main__":
    unittest.main()

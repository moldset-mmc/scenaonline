import tempfile
import unittest
from pathlib import Path


class ScenaV13ServiceOrganizationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pilot-v13.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_services_are_migrated_into_named_groups(self):
        from scena_core import init_db, list_service_groups, list_services

        init_db(self.db_path)
        groups = list_service_groups(self.db_path)
        services = list_services(self.db_path, active_only=False)

        self.assertEqual(
            [group["name_ru"] for group in groups],
            ["Индивидуальная работа", "Обучение", "Модельные проекты"],
        )
        self.assertTrue(all(service["group_id"] for service in services))
        self.assertEqual(
            {service["group_name_ru"] for service in services},
            {"Индивидуальная работа", "Обучение", "Модельные проекты"},
        )

    def test_multiple_services_can_share_one_owner_created_group(self):
        from scena_core import (
            add_service,
            add_service_group,
            init_db,
            list_services,
        )

        init_db(self.db_path)
        group_id = add_service_group(
            self.db_path,
            category="Professional",
            name_ru="Макияж",
            name_ro="Machiaj",
        )
        first_id = add_service(
            self.db_path, "Professional", "Дневной макияж", 900, 60,
            group_id=group_id,
        )
        second_id = add_service(
            self.db_path, "Professional", "Вечерний макияж", 1200, 90,
            group_id=group_id,
        )

        grouped = [
            service for service in list_services(
                self.db_path, "Professional", active_only=False
            )
            if service["group_id"] == group_id
        ]
        self.assertEqual([service["id"] for service in grouped], [first_id, second_id])
        self.assertEqual({service["group_name_ru"] for service in grouped}, {"Макияж"})

    def test_first_service_creates_a_clear_default_group_automatically(self):
        from scena_core import add_service, init_db, list_service_groups, list_services

        init_db(self.db_path)
        import sqlite3

        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM services")
            connection.execute("DELETE FROM service_groups")

        service_id = add_service(
            self.db_path,
            "Professional",
            "Первая услуга",
            900,
            60,
        )

        groups = list_service_groups(self.db_path, "Professional")
        saved = next(
            service
            for service in list_services(
                self.db_path, "Professional", active_only=False
            )
            if service["id"] == service_id
        )
        self.assertEqual([group["name_ru"] for group in groups], ["Основные услуги"])
        self.assertEqual(saved["group_id"], groups[0]["id"])

    def test_archive_restore_and_permanent_delete_are_distinct(self):
        from scena_core import (
            add_service,
            archive_service,
            delete_service,
            init_db,
            list_services,
            restore_service,
        )

        init_db(self.db_path)
        service_id = add_service(
            self.db_path, "Professional", "Тестовая услуга", 300, 30
        )
        archive_service(self.db_path, service_id)
        self.assertNotIn(
            service_id,
            [item["id"] for item in list_services(self.db_path, active_only=False)],
        )
        archived = next(
            item for item in list_services(
                self.db_path, active_only=False, include_archived=True
            )
            if item["id"] == service_id
        )
        self.assertEqual(archived["archived"], 1)

        restore_service(self.db_path, service_id)
        restored = next(
            item for item in list_services(self.db_path, active_only=False)
            if item["id"] == service_id
        )
        self.assertEqual((restored["archived"], restored["active"]), (0, 0))

        delete_service(self.db_path, service_id)
        self.assertNotIn(
            service_id,
            [item["id"] for item in list_services(
                self.db_path, active_only=False, include_archived=True
            )],
        )

    def test_service_with_request_can_only_be_archived(self):
        from scena_core import (
            RequestValidationError,
            archive_service,
            create_course_preregistration,
            delete_service,
            init_db,
            list_services,
            service_request_count,
        )

        init_db(self.db_path)
        course = list_services(
            self.db_path, "Professional", kind="course"
        )[0]
        create_course_preregistration(
            self.db_path,
            service_id=course["id"],
            name="Анна",
            phone="060000001",
            consent=True,
        )
        self.assertEqual(service_request_count(self.db_path, course["id"]), 1)
        with self.assertRaisesRegex(RequestValidationError, "только отправить в архив"):
            delete_service(self.db_path, course["id"])
        archive_service(self.db_path, course["id"])

    def test_hidden_group_hides_its_services_from_public_lists(self):
        from scena_core import (
            init_db,
            list_service_groups,
            list_services,
            set_service_group_active,
        )

        init_db(self.db_path)
        group = list_service_groups(self.db_path, "Professional")[0]
        member_ids = {
            service["id"] for service in list_services(
                self.db_path, "Professional", active_only=False
            )
            if service["group_id"] == group["id"]
        }
        set_service_group_active(self.db_path, group["id"], False)
        public_ids = {
            service["id"] for service in list_services(
                self.db_path, "Professional"
            )
        }
        self.assertTrue(member_ids)
        self.assertTrue(member_ids.isdisjoint(public_ids))

    def test_legacy_location_placeholder_is_replaced_but_real_value_is_kept(self):
        from scena_core import get_settings, init_db, save_settings

        import sqlite3

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE profile_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO profile_settings (key, value) VALUES (?, ?)",
                ("location", "Ваш город"),
            )

        init_db(self.db_path)
        self.assertEqual(get_settings(self.db_path)["location"], "Кишинёв")

        save_settings(self.db_path, {"location": "Бельцы"})
        init_db(self.db_path)
        self.assertEqual(get_settings(self.db_path)["location"], "Бельцы")

    def test_saved_profile_values_survive_every_later_restart(self):
        from scena_core import get_settings, init_db, save_settings

        init_db(self.db_path)
        save_settings(
            self.db_path,
            {
                "master_name": "Мария Бараночникова",
                "location": "Оргеев",
                "bio": "Мой сохранённый текст.",
                "beauty_title": "Новая профессиональная рубрика",
                "model_title": "Новая модельная рубрика",
                "schedule_start": "10:30",
                "public_base_url": "https://scena.example",
                "model_slide_1_manifesto_ru": "Новый личный посыл.",
            },
        )

        init_db(self.db_path)
        init_db(self.db_path)

        settings = get_settings(self.db_path)
        self.assertEqual(settings["master_name"], "Мария Бараночникова")
        self.assertEqual(settings["location"], "Оргеев")
        self.assertEqual(settings["bio"], "Мой сохранённый текст.")
        self.assertEqual(
            settings["beauty_title"], "Новая профессиональная рубрика"
        )
        self.assertEqual(settings["model_title"], "Новая модельная рубрика")
        self.assertEqual(settings["schedule_start"], "10:30")
        self.assertEqual(settings["public_base_url"], "https://scena.example")
        self.assertEqual(
            settings["model_slide_1_manifesto_ru"], "Новый личный посыл."
        )


if __name__ == "__main__":
    unittest.main()

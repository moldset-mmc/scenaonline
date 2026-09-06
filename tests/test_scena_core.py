import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class ScenaCoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pilot.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_three_public_paths_create_distinct_crm_requests(self):
        from scena_core import (
            create_request,
            create_service_request,
            init_db,
            list_requests,
            list_services,
        )

        init_db(self.db_path)
        service_id = list_services(self.db_path, "Professional", kind="appointment")[0]["id"]
        now = datetime(2026, 9, 7, 8, 0, tzinfo=ZoneInfo("Europe/Chisinau"))

        service_request_id = create_service_request(
            self.db_path,
            service_id=service_id,
            slot_date="2026-09-09",
            slot_time="10:00",
            name="Анна",
            phone="+373 60 000 001",
            consent=True,
            now=now,
        )
        invitation_id = create_request(
            self.db_path,
            request_type="model_invitation",
            name="Марка одежды",
            phone="+373 60 000 002",
            organization="Brand Studio",
            service="Каталожная съёмка",
            preferred_date="2026-09-12",
            message="Съёмка новой коллекции",
            consent=True,
        )
        application_id = create_request(
            self.db_path,
            request_type="model_application",
            name="Елена",
            phone="+373 60 000 003",
            city="Кишинёв",
            experience="Без опыта",
            message="Хочу попробовать себя в модельной роли",
            consent=True,
        )

        self.assertEqual([service_request_id, invitation_id, application_id], [1, 2, 3])
        rows = list_requests(self.db_path)
        self.assertEqual(
            [row["request_type"] for row in rows],
            ["model_application", "model_invitation", "service_request"],
        )
        self.assertEqual(
            {row["status"] for row in rows},
            {"Новая", "Ожидает подтверждения"},
        )

    def test_request_requires_contact_consent_and_path_specific_fields(self):
        from scena_core import RequestValidationError, create_request, init_db

        init_db(self.db_path)

        invalid_payloads = [
            {"request_type": "beauty_booking", "name": "", "phone": "+37360000001", "service": "Макияж", "preferred_date": "2026-09-10", "preferred_time": "14:00", "consent": True},
            {"request_type": "beauty_booking", "name": "Анна", "phone": "123", "service": "Макияж", "preferred_date": "2026-09-10", "preferred_time": "14:00", "consent": True},
            {"request_type": "beauty_booking", "name": "Анна", "phone": "call-me-37360000001", "service": "Макияж", "preferred_date": "2026-09-10", "preferred_time": "14:00", "consent": True},
            {"request_type": "beauty_booking", "name": "Анна", "phone": "+37360000001", "email": "wrong-email", "service": "Макияж", "preferred_date": "2026-09-10", "preferred_time": "14:00", "consent": True},
            {"request_type": "beauty_booking", "name": "Анна", "phone": "+37360000001", "service": "", "preferred_date": "2026-09-10", "preferred_time": "14:00", "consent": True},
            {"request_type": "beauty_booking", "name": "Анна", "phone": "+37360000001", "service": "Макияж", "preferred_date": "", "preferred_time": "", "consent": True},
            {"request_type": "model_invitation", "name": "Brand", "phone": "+37360000002", "organization": "Brand", "service": "Съёмка", "preferred_date": "", "consent": True},
            {"request_type": "model_invitation", "name": "Brand", "phone": "+37360000002", "organization": "", "service": "Съёмка", "preferred_date": "2026-09-12", "message": "Бриф", "consent": True},
            {"request_type": "model_invitation", "name": "Brand", "phone": "+37360000002", "organization": "Brand", "service": "Съёмка", "preferred_date": "2026-09-12", "message": "", "consent": True},
            {"request_type": "model_application", "name": "Елена", "phone": "+37360000003", "city": "", "experience": "Без опыта", "consent": True},
            {"request_type": "model_application", "name": "Елена", "phone": "+37360000003", "city": "Кишинёв", "experience": "Без опыта", "consent": False},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(RequestValidationError):
                    create_request(self.db_path, **payload)

    def test_admin_password_is_required_and_compared_safely(self):
        from scena_core import get_admin_password, verify_admin_password

        old_value = os.environ.pop("SCENA_ADMIN_PASSWORD", None)
        try:
            self.assertIsNone(get_admin_password())
            os.environ["SCENA_ADMIN_PASSWORD"] = "pilot-secret"
            self.assertEqual(get_admin_password(), "pilot-secret")
            self.assertTrue(verify_admin_password("pilot-secret", "pilot-secret"))
            self.assertFalse(verify_admin_password("wrong", "pilot-secret"))
            self.assertFalse(verify_admin_password("pilot-secret", None))
        finally:
            if old_value is None:
                os.environ.pop("SCENA_ADMIN_PASSWORD", None)
            else:
                os.environ["SCENA_ADMIN_PASSWORD"] = old_value

    def test_status_updates_only_to_supported_crm_states(self):
        from scena_core import (
            RequestValidationError,
            create_request,
            init_db,
            list_requests,
            update_request_status,
        )

        init_db(self.db_path)
        request_id = create_request(
            self.db_path,
            request_type="model_application",
            name="Елена",
            phone="+37360000003",
            city="Кишинёв",
            experience="Без опыта",
            consent=True,
        )

        update_request_status(self.db_path, request_id, "Связались")
        self.assertEqual(list_requests(self.db_path)[0]["status"], "Связались")
        with self.assertRaises(RequestValidationError):
            update_request_status(self.db_path, request_id, "Скрытый статус")

    def test_existing_service_can_be_edited_without_changing_its_identity(self):
        from scena_core import init_db, list_services, update_service

        init_db(self.db_path)
        original = list_services(self.db_path, "Professional")[0]

        update_service(
            self.db_path,
            original["id"],
            category="Model",
            name="Обновлённая услуга",
            price=1500,
            duration=75,
        )

        updated = next(
            item
            for item in list_services(self.db_path, active_only=False)
            if item["id"] == original["id"]
        )
        self.assertEqual(updated["category"], "Model")
        self.assertEqual(updated["name"], "Обновлённая услуга")
        self.assertEqual(updated["price"], 1500)
        self.assertEqual(updated["duration"], 75)

    def test_v0_database_is_migrated_without_losing_existing_booking(self):
        from scena_core import get_settings, init_db, list_requests, list_services

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
                """
                CREATE TABLE services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    duration INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_name TEXT NOT NULL,
                    client_phone TEXT NOT NULL,
                    role_booked TEXT NOT NULL,
                    service TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    booking_time TEXT NOT NULL,
                    status TEXT DEFAULT 'Новый',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO services (category, name, price, duration)
                VALUES ('Beauty', 'Моя сохранённая услуга', 900, 60)
                """
            )
            connection.executemany(
                "INSERT INTO profile_settings (key, value) VALUES (?, ?)",
                [
                    ("master_name", "Мария Барановская"),
                    (
                        "model_desc",
                        "Официальная модель бэкстейджей SCENA. Имею опыт работы с брендами тихой роскоши (12 STOREEZ, IDOL, YuliaWave). Мое лицо верифицировано в ИИ-галерее Face ID.",
                    ),
                    (
                        "avatar_url",
                        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=600",
                    ),
                ],
            )
            connection.execute(
                """
                INSERT INTO bookings (
                    client_name, client_phone, role_booked, service,
                    booking_date, booking_time, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Старый клиент",
                    "+37360000009",
                    "Мастер-Визажист",
                    "Моя сохранённая услуга",
                    "2026-09-20",
                    "15:00",
                    "Подтвержден",
                    "2026-08-29 12:00:00",
                ),
            )

        init_db(self.db_path)

        services = list_services(self.db_path, active_only=False)
        self.assertEqual(services[0]["name"], "Моя сохранённая услуга")
        self.assertEqual(services[0]["active"], 1)
        requests = list_requests(self.db_path)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["name"], "Старый клиент")
        self.assertEqual(requests[0]["preferred_time"], "15:00")
        self.assertEqual(requests[0]["status"], "Подтверждена")
        settings = get_settings(self.db_path)
        self.assertEqual(settings["master_name"], "Мария Бараночникова")
        self.assertEqual(settings["avatar_url"], "")
        self.assertNotIn("12 STOREEZ", settings["model_desc"])

        init_db(self.db_path)
        self.assertEqual(len(list_requests(self.db_path)), 1)

    def test_launcher_binds_to_localhost_and_uses_masked_password_input(self):
        launcher = (PROJECT_ROOT / "start_scena.py").read_text(encoding="utf-8")
        windows_entry = (PROJECT_ROOT / "START-SCENA.cmd").read_text(encoding="utf-8")

        self.assertIn("getpass.getpass", launcher)
        self.assertIn('"127.0.0.1"', launcher)
        self.assertIn("find_available_port", launcher)
        self.assertIn("Порт 8501 занят", launcher)
        self.assertNotIn("http://localhost:8501", windows_entry)
        self.assertNotIn("set /p", windows_entry.lower())
        self.assertIn("import streamlit, PIL, qrcode", windows_entry)

    def test_schema_has_no_payment_or_fake_integration_tables(self):
        from scena_core import init_db

        init_db(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        self.assertIn("requests", names)
        self.assertIn("services", names)
        self.assertNotIn("payments", names)
        self.assertNotIn("inventory", names)
        self.assertNotIn("safe_deal", names)

    def test_public_app_exposes_three_paths_without_demo_commerce_claims(self):
        app_path = PROJECT_ROOT / "scena_app.py"
        source = app_path.read_text(encoding="utf-8") + (app_path.parent / "scena_booking_ui.py").read_text(encoding="utf-8")

        for public_path in (
            "Время для себя",
            "Пригласить как модель",
            "Хочу стать моделью",
        ):
            self.assertIn(public_path, source)

        for forbidden_claim in (
            "Shop the Outfit",
            "Safe Deal",
            "Fashion Inventory API",
            "Сплит-транзакц",
            "Купить Outfit",
        ):
            self.assertNotIn(forbidden_claim, source)

        self.assertIn("SCENA_ADMIN_PASSWORD", source)
        self.assertNotIn("Режим администратора", source)

    def test_mobile_layout_and_compact_crm_contract_are_present(self):
        source = (PROJECT_ROOT / "scena_app.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("@media (max-width: 700px)", source)
        self.assertIn("flex-direction: column !important", source)
        self.assertIn("min-inline-size: 0 !important", source)
        self.assertIn("font-size: 16px !important", source)
        self.assertNotIn("overflow-x: hidden", source)
        self.assertIn('st.subheader(ui("Список заявок"))', source)
        self.assertIn('st.expander(ui("Полная таблица заявок"))', source)

    def test_public_pages_have_separate_shareable_routes(self):
        source = (PROJECT_ROOT / "scena_app.py").read_text(encoding="utf-8")

        for route in (
            '"scene"',
            '"portfolio"',
            '"professional"',
            '"model"',
            '"booking"',
            '"course"',
            '"join-model"',
            '"invite-model"',
        ):
            self.assertIn(route, source)
        self.assertIn("st.context", source)
        self.assertIn("RU", source)
        self.assertIn("RO", source)


if __name__ == "__main__":
    unittest.main()

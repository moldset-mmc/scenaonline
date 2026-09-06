import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
CHISINAU = ZoneInfo("Europe/Chisinau")


class ScenaV11ContractTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pilot-v11.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _appointment(self, duration=60, buffer_minutes=10):
        from scena_core import add_service, init_db

        init_db(self.db_path)
        return add_service(
            self.db_path,
            "Professional",
            "Персональная консультация",
            900,
            duration,
            kind="appointment",
            buffer_minutes=buffer_minutes,
            name_ro="Consultație personală",
            description_ru="Индивидуальная встреча со специалистом.",
            description_ro="Întâlnire individuală cu specialistul.",
            translations_approved=True,
        )

    def test_only_moldova_phone_numbers_are_accepted_and_normalized(self):
        from scena_core import RequestValidationError, normalize_moldova_phone

        for source in ("060 123 456", "+373 60-123-456", "37360123456"):
            with self.subTest(source=source):
                self.assertEqual(normalize_moldova_phone(source), "+37360123456")

        for source in ("+40722123456", "+373123", "call-me", ""):
            with self.subTest(source=source):
                with self.assertRaises(RequestValidationError):
                    normalize_moldova_phone(source)

    def test_slots_follow_schedule_interval_duration_buffer_and_lead_time(self):
        from scena_core import generate_available_slots, save_settings

        service_id = self._appointment(duration=60, buffer_minutes=10)
        save_settings(
            self.db_path,
            {
                "schedule_weekdays": "0,1,2,3,4",
                "schedule_start": "09:00",
                "schedule_end": "18:00",
                "schedule_break_start": "13:00",
                "schedule_break_end": "14:00",
                "slot_interval_minutes": "10",
                "minimum_lead_hours": "2",
                "booking_horizon_days": "90",
            },
        )
        now = datetime(2026, 9, 7, 8, 0, tzinfo=CHISINAU)

        slots = generate_available_slots(
            self.db_path,
            service_id,
            "2026-09-07",
            now=now,
        )

        self.assertEqual(slots[0], "10:00")
        self.assertIn("10:10", slots)
        self.assertIn("11:50", slots)
        self.assertNotIn("12:00", slots)
        self.assertIn("14:00", slots)
        self.assertEqual(slots[-1], "16:50")

    def test_pending_request_blocks_overlapping_slots_and_expires_after_24_hours(self):
        from scena_core import (
            RequestValidationError,
            create_service_request,
            expire_pending_requests,
            generate_available_slots,
            list_requests,
            update_request_status,
        )

        service_id = self._appointment(duration=60, buffer_minutes=10)
        now = datetime(2026, 9, 7, 8, 0, tzinfo=CHISINAU)
        request_id = create_service_request(
            self.db_path,
            service_id=service_id,
            slot_date="2026-09-09",
            slot_time="10:00",
            name="Анна",
            phone="060123456",
            email="anna@example.com",
            message="Тестовая заявка",
            consent=True,
            locale="ru",
            now=now,
        )

        slots = generate_available_slots(
            self.db_path,
            service_id,
            "2026-09-09",
            now=now,
        )
        self.assertNotIn("10:00", slots)
        self.assertNotIn("10:10", slots)
        self.assertIn("11:10", slots)

        with self.assertRaises(RequestValidationError):
            create_service_request(
                self.db_path,
                service_id=service_id,
                slot_date="2026-09-09",
                slot_time="10:00",
                name="Ирина",
                phone="060123457",
                consent=True,
                locale="ro",
                now=now,
            )

        update_request_status(self.db_path, request_id, "Связались")

        expired = expire_pending_requests(
            self.db_path,
            now=now + timedelta(hours=24, seconds=1),
        )
        self.assertEqual(expired, [request_id])
        self.assertEqual(list_requests(self.db_path)[0]["status"], "Срок подтверждения истёк")
        released = generate_available_slots(
            self.db_path,
            service_id,
            "2026-09-09",
            now=now + timedelta(hours=24, seconds=1),
        )
        self.assertIn("10:00", released)

    def test_course_preregistration_is_manual_and_does_not_reserve_a_slot(self):
        from scena_core import (
            add_service,
            create_course_preregistration,
            init_db,
            list_requests,
        )

        init_db(self.db_path)
        course_id = add_service(
            self.db_path,
            "Professional",
            "Авторский курс",
            0,
            60,
            kind="course",
            name_ro="Curs de autor",
            description_ru="Описание курса",
            description_ro="Descrierea cursului",
            translations_approved=True,
        )

        request_id = create_course_preregistration(
            self.db_path,
            service_id=course_id,
            name="Марина",
            phone="+373 60 123 458",
            email="",
            message="Хочу узнать дату старта",
            consent=True,
            locale="ru",
        )

        row = list_requests(self.db_path)[0]
        self.assertEqual(row["id"], request_id)
        self.assertEqual(row["request_type"], "course_preregistration")
        self.assertEqual(row["status"], "Новая")
        self.assertEqual(row["preferred_date"], "")
        self.assertEqual(row["hold_expires_at"], "")

    def test_request_creation_queues_localized_sms_events(self):
        from scena_core import create_service_request, list_sms_outbox, save_settings

        service_id = self._appointment()
        save_settings(self.db_path, {"pending_hold_hours": "12"})
        now = datetime(2026, 9, 7, 8, 0, tzinfo=CHISINAU)
        create_service_request(
            self.db_path,
            service_id=service_id,
            slot_date="2026-09-08",
            slot_time="10:00",
            name="Ana",
            phone="060123459",
            consent=True,
            locale="ro",
            now=now,
        )

        messages = list_sms_outbox(self.db_path)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["recipient"], "+37360123459")
        self.assertEqual(messages[0]["locale"], "ro")
        self.assertEqual(messages[0]["event"], "request_received")
        self.assertIn("12", messages[0]["body"])

    def test_model_request_sms_does_not_claim_a_time_hold(self):
        from scena_core import (
            create_request,
            init_db,
            list_sms_outbox,
            update_request_status,
        )

        init_db(self.db_path)
        request_id = create_request(
            self.db_path,
            request_type="model_application",
            name="Elena",
            phone="060123490",
            city="Chișinău",
            experience="Începătoare",
            consent=True,
            locale="ro",
        )

        message = list_sms_outbox(self.db_path)[0]
        self.assertEqual(message["event"], "general_request_received")
        self.assertNotIn("24", message["body"])
        self.assertNotIn("Ora ", message["body"])
        update_request_status(self.db_path, request_id, "Подтверждена")
        confirmation = list_sms_outbox(self.db_path)[1]
        self.assertEqual(confirmation["event"], "confirmed")
        self.assertEqual(
            confirmation["body"],
            f"SCENA: cererea #{request_id} a fost confirmată.",
        )

    def test_only_one_concurrent_client_can_hold_the_same_slot(self):
        from scena_core import RequestValidationError, create_service_request, list_requests

        service_id = self._appointment()
        now = datetime(2026, 9, 7, 8, 0, tzinfo=CHISINAU)
        barrier = threading.Barrier(2)
        outcomes = []
        lock = threading.Lock()

        def compete(index):
            barrier.wait()
            try:
                request_id = create_service_request(
                    self.db_path,
                    service_id=service_id,
                    slot_date="2026-09-09",
                    slot_time="10:00",
                    name=f"Клиент {index}",
                    phone=f"0601234{60 + index}",
                    consent=True,
                    locale="ru",
                    now=now,
                )
                result = ("created", request_id)
            except RequestValidationError as exc:
                result = ("rejected", str(exc))
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=compete, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sum(result[0] == "created" for result in outcomes), 1)
        self.assertEqual(sum(result[0] == "rejected" for result in outcomes), 1)
        self.assertEqual(len(list_requests(self.db_path)), 1)

    def test_expired_request_cannot_be_confirmed_over_a_new_holder(self):
        from scena_core import (
            RequestValidationError,
            create_service_request,
            expire_pending_requests,
            update_request_status,
        )

        service_id = self._appointment()
        now = datetime(2026, 9, 7, 8, 0, tzinfo=CHISINAU)
        expired_id = create_service_request(
            self.db_path, service_id=service_id, slot_date="2026-09-09",
            slot_time="10:00", name="Первый клиент", phone="060123480",
            consent=True, locale="ru", now=now,
        )
        later = now + timedelta(hours=24, seconds=1)
        expire_pending_requests(self.db_path, now=later)
        create_service_request(
            self.db_path, service_id=service_id, slot_date="2026-09-09",
            slot_time="10:00", name="Второй клиент", phone="060123481",
            consent=True, locale="ru", now=later,
        )

        with self.assertRaises(RequestValidationError):
            update_request_status(
                self.db_path, expired_id, "Подтверждена", now=later,
            )

    def test_legacy_beauty_request_is_migrated_without_data_loss(self):
        from scena_core import init_db, list_requests

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "CREATE TABLE profile_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                """
                CREATE TABLE services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    duration INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    organization TEXT NOT NULL DEFAULT '',
                    service TEXT NOT NULL DEFAULT '',
                    preferred_date TEXT NOT NULL DEFAULT '',
                    preferred_time TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    experience TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    consent INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Новая',
                    created_at TEXT NOT NULL,
                    legacy_booking_id INTEGER
                )
                """
            )
            connection.execute(
                """
                INSERT INTO requests (
                    request_type, name, phone, service, preferred_date,
                    preferred_time, consent, status, created_at
                ) VALUES ('beauty_booking', 'Сохранённый клиент', '+37360000009',
                          'Старая услуга', '2026-09-20', '15:00', 1, 'Новая',
                          '2026-08-29T12:00:00+03:00')
                """
            )

        init_db(self.db_path)

        rows = list_requests(self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["request_type"], "service_request")
        self.assertEqual(rows[0]["name"], "Сохранённый клиент")
        self.assertEqual(rows[0]["preferred_time"], "15:00")

    def test_posts_are_drafts_until_bilingual_approval_and_likes_require_verification(self):
        from scena_core import (
            RequestValidationError,
            add_post,
            init_db,
            list_posts,
            set_post_active,
            toggle_post_like,
        )

        init_db(self.db_path)
        post_id = add_post(
            self.db_path,
            title_ru="Первый пост",
            title_ro="Prima publicație",
            body_ru="Новая глава моей истории.",
            body_ro="Un nou capitol din povestea mea.",
            translations_approved=True,
        )
        self.assertEqual(list_posts(self.db_path), [])
        set_post_active(self.db_path, post_id, True)

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO members (phone, public_name, slug, phone_verified, created_at)
                VALUES ('+37360123470', 'Непроверенный', 'not-verified', 0, '2026-09-02T12:00:00+03:00')
                """
            )
            unverified_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            connection.execute(
                """
                INSERT INTO members (phone, public_name, slug, phone_verified, created_at)
                VALUES ('+37360123471', 'Проверенный', 'verified', 1, '2026-09-02T12:00:00+03:00')
                """
            )
            verified_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]

        with self.assertRaises(RequestValidationError):
            toggle_post_like(self.db_path, post_id, unverified_id)
        self.assertTrue(toggle_post_like(self.db_path, post_id, verified_id))
        self.assertEqual(list_posts(self.db_path)[0]["like_count"], 1)
        self.assertFalse(toggle_post_like(self.db_path, post_id, verified_id))
        self.assertEqual(list_posts(self.db_path)[0]["like_count"], 0)

    def test_service_stays_draft_until_both_languages_are_approved(self):
        from scena_core import (
            RequestValidationError,
            add_service,
            init_db,
            list_services,
            set_service_active,
            update_service,
        )

        init_db(self.db_path)
        service_id = add_service(
            self.db_path, "Professional", "Новая услуга", 500, 30,
            description_ru="Описание", translations_approved=False,
        )
        stored = next(
            item for item in list_services(self.db_path, active_only=False)
            if item["id"] == service_id
        )
        self.assertEqual(stored["active"], 0)
        with self.assertRaises(RequestValidationError):
            set_service_active(self.db_path, service_id, True)

        update_service(
            self.db_path, service_id, category="Professional", kind="appointment",
            name="Новая услуга", name_ro="Serviciu nou", price=500, duration=30,
            buffer_minutes=10, description_ru="Описание",
            description_ro="Descriere", translations_approved=True,
        )
        set_service_active(self.db_path, service_id, True)
        self.assertTrue(
            next(
                item for item in list_services(self.db_path)
                if item["id"] == service_id
            )["active"]
        )


if __name__ == "__main__":
    unittest.main()

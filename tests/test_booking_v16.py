"""Customer booking behavior using the real SQLite scheduler and Streamlit UI."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

from scena_core import (
    CHISINAU, add_schedule_exception, create_service_request, generate_available_slots, get_settings,
    init_db, list_requests, list_services, save_settings,
)

ROOT = Path(__file__).resolve().parents[1]


class BookingV16Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "booking.db"
        init_db(self.db)
        save_settings(self.db, {
            "schedule_weekdays": "0,1,2,3,4,5,6", "schedule_start": "08:00",
            "schedule_end": "18:00", "schedule_break_start": "12:00",
            "schedule_break_end": "13:00", "minimum_lead_hours": "0",
            "slot_interval_minutes": "30", "booking_horizon_days": "45",
        })
        self.service = list_services(self.db, "Professional", kind="appointment")[0]
        self.day = (datetime.now(CHISINAU).date() + timedelta(days=3)).isoformat()

    def tearDown(self):
        self.temp.cleanup()

    def app(self, locale="ru"):
        app = AppTest.from_string(
            "from pathlib import Path\n"
            "from scena_booking_ui import render_booking\n"
            "from scena_core import get_settings\n"
            f"db = Path({str(self.db)!r})\n"
            f"render_booking(db, Path({str(ROOT)!r}), get_settings(db), {locale!r})\n",
            default_timeout=20,
        )
        app.query_params["service"] = str(self.service["id"])
        app.session_state["booking_date"] = self.day
        app.session_state["booking_month"] = self.day[:7] + "-01"
        return app.run()

    def test_full_day_stays_selected_until_explicit_nearest_date_click(self):
        add_schedule_exception(self.db, self.day, "closed")
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["booking_date"], self.day)
        self.assertTrue(any("нет свободного времени" in item.value for item in app.info))
        app.button(key="booking_nearest_day").click().run()
        expected = (datetime.fromisoformat(self.day).date() + timedelta(days=1)).isoformat()
        self.assertEqual(app.session_state["booking_date"], expected)
        self.assertTrue(any(button.key == f"booking_day_{expected}" for button in app.button))

    def test_month_slots_confirmation_and_single_saved_request(self):
        app = self.app()
        self.assertFalse(app.exception)
        calendar_buttons = [button for button in app.button if (button.key or "").startswith("booking_day_")]
        self.assertGreaterEqual(len(calendar_buttons), 28)
        # Two visual groups remain, without the removed morning/afternoon titles.
        headings = " ".join(item.value for item in app.subheader)
        self.assertNotIn("До обеда", headings)
        self.assertNotIn("После обеда", headings)
        blocks = {block.key: block for block in app.get('flex_container') if getattr(block, 'key', None) in {'booking_morning', 'booking_afternoon'}}
        self.assertEqual(set(blocks), {'booking_morning', 'booking_afternoon'})
        for key, morning in [('booking_morning', True), ('booking_afternoon', False)]:
            times = [button.label for button in blocks[key].get('button')]
            self.assertTrue(times)
            self.assertTrue(all((int(value[:2]) < 12) == morning for value in times))
        markup = '\n'.join(item.value for item in app.markdown if 'class="scena-booking-date"' in item.value)
        weekdays = ('Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье')
        day = datetime.fromisoformat(self.day)
        self.assertIn(f'{weekdays[day.weekday()]}, {day:%d.%m.%Y}', markup)
        self.assertFalse(app.text_input)
        slot = generate_available_slots(self.db, self.service["id"], self.day)[0]
        app.button(key=f"booking_slot_{slot}").click().run()
        app.button(key="booking_continue").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(any((button.key or "").startswith("booking_day_") for button in app.button))
        app.text_input(key="booking_contact_name").set_value("Анна")
        app.text_input(key="booking_contact_phone").set_value("060000001")
        app.checkbox(key="booking_contact_consent").set_value(True)
        next(button for button in app.button if button.label == "Отправить заявку").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.success), 1)
        self.assertTrue(any("Сцену" in item.label for item in app.get("link_button")))
        self.assertEqual(len(list_requests(self.db)), 1)
        app.run()
        self.assertEqual(len(list_requests(self.db)), 1)
        self.assertNotIn(slot, generate_available_slots(self.db, self.service["id"], self.day))

    def test_month_navigation_preserves_day_and_calendar_horizon(self):
        app = self.app("ro")
        self.assertFalse(app.exception)
        before = app.session_state["booking_date"]
        if not app.button(key="booking_month_next").disabled:
            app.button(key="booking_month_next").click().run()
        self.assertEqual(app.session_state["booking_date"], before)
        today = datetime.now(CHISINAU).date()
        horizon = today + timedelta(days=int(get_settings(self.db)["booking_horizon_days"]))
        for button in app.button:
            if (button.key or "").startswith("booking_day_"):
                day = datetime.fromisoformat(button.key[len("booking_day_"):]).date()
                if day < today or day > horizon:
                    self.assertTrue(button.disabled)

    def test_slot_taken_during_confirmation_is_not_double_booked(self):
        app = self.app()
        slot = generate_available_slots(self.db, self.service["id"], self.day)[0]
        app.button(key=f"booking_slot_{slot}").click().run()
        app.button(key="booking_continue").click().run()
        create_service_request(self.db, service_id=self.service["id"], slot_date=self.day,
            slot_time=slot, name="Другой клиент", phone="060000003", consent=True, locale="ru")
        app.text_input(key="booking_contact_name").set_value("Анна")
        app.text_input(key="booking_contact_phone").set_value("060000001")
        app.checkbox(key="booking_contact_consent").set_value(True)
        next(button for button in app.button if button.label == "Отправить заявку").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.success)
        self.assertTrue(any("уже недоступно" in item.value for item in app.error))
        self.assertEqual(len(list_requests(self.db)), 1)
        app.button(key="booking_edit").click().run()
        self.assertEqual(app.session_state["booking_date"], self.day)
        self.assertFalse(any(button.key == f"booking_slot_{slot}" for button in app.button))


if __name__ == "__main__":
    unittest.main()

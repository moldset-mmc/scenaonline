"""Resend booking email acceptance without external network traffic."""
from datetime import datetime, timedelta
import sqlite3
import unittest

import test_shop_v17 as shop_tests
import scena_service_email as service_email
from scena_core import (
    CHISINAU,
    create_service_request,
    generate_available_slots,
    list_services,
    save_settings,
    update_request_status,
)


class FakeAdapter:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def send(self, payload):
        self.calls.append(payload)
        if self.error:
            raise self.error
        return {"id": "email_test_1"}


class ServiceEmailTests(unittest.TestCase):
    setUp = shop_tests.ShopTests.setUp

    def book(self, channel="email"):
        save_settings(
            self.db,
            {
                "public_base_url": "https://mbstudio.scena.life",
                "schedule_weekdays": "0,1,2,3,4,5,6",
                "schedule_start": "08:00",
                "schedule_end": "18:00",
                "minimum_lead_hours": "0",
            },
        )
        moment = datetime.now(CHISINAU).replace(microsecond=0)
        service = list_services(self.db, "Professional", kind="appointment")[0]
        day = (moment.date() + timedelta(days=3)).isoformat()
        slot = generate_available_slots(self.db, service["id"], day, now=moment)[0]
        identity = create_service_request(
            self.db,
            service_id=service["id"],
            slot_date=day,
            slot_time=slot,
            name="Email client",
            phone="060000001",
            email="client@example.com" if channel == "email" else "",
            contact_channel=channel,
            telegram="",
            consent=True,
            locale="ru",
            now=moment,
        )
        return identity, service, day, slot

    def row(self, identity):
        with sqlite3.connect(self.db) as con:
            con.row_factory = sqlite3.Row
            return dict(con.execute("SELECT * FROM requests WHERE id=?", (identity,)).fetchone())

    def test_sender_is_derived_from_one_scena_life_tenant_label(self):
        self.assertEqual(
            service_email.sender_from_public_base("https://mbstudio.scena.life"),
            "mbstudio@scena.life",
        )
        for value in (
            "https://scena.life",
            "https://a.b.scena.life",
            "https://scenaonline.vercel.app",
            "http://mbstudio.scena.life",
            "https://bad_name.scena.life",
        ):
            with self.subTest(value=value):
                self.assertEqual(service_email.sender_from_public_base(value), "")

    def test_email_choice_sends_one_localized_received_payload(self):
        identity, service, day, slot = self.book("email")
        adapter = FakeAdapter()
        self.assertEqual(
            service_email.dispatch(self.db, request_id=identity, adapter=adapter),
            "sent",
        )
        self.assertEqual(len(adapter.calls), 1)
        payload = adapter.calls[0]
        self.assertEqual(payload["from"], "mbstudio@scena.life")
        self.assertEqual(payload["to"], ["client@example.com"])
        self.assertIn(f"№{identity}", payload["subject"])
        self.assertIn("принята", payload["subject"])
        self.assertIn(service["name"], payload["text"])
        self.assertIn(slot, payload["text"])
        self.assertIn("Мастер свяжется", payload["text"])

    def test_confirmation_requires_committed_confirmed_status_and_uses_resend(self):
        identity, service, _, slot = self.book("email")
        adapter = FakeAdapter()
        self.assertEqual(
            service_email.dispatch(
                self.db, request_id=identity, event="confirmed", adapter=adapter
            ),
            "invalid_status",
        )
        self.assertEqual(adapter.calls, [])

        row = self.row(identity)
        update_request_status(
            self.db,
            identity,
            "Подтверждена",
            expected_revision=row["revision"],
        )
        self.assertEqual(
            service_email.dispatch(
                self.db, request_id=identity, event="confirmed", adapter=adapter
            ),
            "sent",
        )
        self.assertEqual(len(adapter.calls), 1)
        payload = adapter.calls[0]
        self.assertIn("подтверждена", payload["subject"].lower())
        self.assertIn("Ваша запись подтверждена", payload["text"])
        self.assertIn(service["name"], payload["text"])
        self.assertIn(slot, payload["text"])

    def test_other_reply_channel_never_sends_email(self):
        identity, _, _, _ = self.book("phone")
        adapter = FakeAdapter()
        self.assertEqual(
            service_email.dispatch(self.db, request_id=identity, adapter=adapter),
            "skipped",
        )
        self.assertEqual(adapter.calls, [])

    def test_resend_failure_never_rolls_back_committed_booking_or_exposes_secret(self):
        identity, _, _, _ = self.book("email")
        before = self.row(identity)
        update_request_status(
            self.db,
            identity,
            "Подтверждена",
            expected_revision=before["revision"],
        )
        adapter = FakeAdapter(TimeoutError("secret-api-key-must-not-surface"))
        self.assertEqual(
            service_email.dispatch(
                self.db, request_id=identity, event="confirmed", adapter=adapter
            ),
            "failed",
        )
        after = self.row(identity)
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["status"], "Подтверждена")
        self.assertEqual(after["email"], "client@example.com")


if __name__ == "__main__":
    unittest.main()

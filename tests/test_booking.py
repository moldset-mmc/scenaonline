"""Booking core: slots, requests, statuses."""
import sqlite3
import unittest

from scena_web import booking


def store():
    return booking.Store(booking.Config(local_path=':memory:'))


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.store = store()
        booking.seed_tulip(self.store)

    def test_seed_lists_masters_and_services(self):
        data = booking.services(self.store, 'tulip')
        self.assertEqual(data['salon']['name'], 'TULIP')
        self.assertEqual(len(data['masters']), 4)
        self.assertEqual(len(data['services']), 4)
        zhen = [s for s in data['services'] if s['title'] == 'Женская стрижка'][0]
        self.assertEqual(zhen['duration_min'], 60)
        self.assertIn('master-lilia', zhen['masters'])

    def test_slots_respect_hours_and_duration(self):
        # 2026-11-24 is a Tuesday and is in the future; hours 09:00-19:00
        found = booking.slots(self.store, 'tulip', 'master-lilia', 'service-zhen', '2026-11-24', now=0)
        self.assertTrue(found)
        self.assertEqual(found[0]['label'], '09:00')
        self.assertEqual(found[-1]['label'], '18:00')
        self.assertTrue(all(s['end'] - s['start'] == 3600 for s in found))

    def test_no_slots_on_closed_day(self):
        # 2026-11-23 is a Monday and is in the future; the seed has no Monday hours
        self.assertEqual(booking.slots(self.store, 'tulip', 'master-lilia', 'service-zhen', '2026-11-23', now=0), [])

    def test_request_blocks_its_slot(self):
        day = '2026-11-24'
        free = booking.slots(self.store, 'tulip', 'master-lilia', 'service-zhen', day, now=0)
        start = free[0]['start']
        created = booking.create_request(self.store, {
            'salon': 'tulip', 'master': 'master-lilia', 'service': 'service-zhen', 'start': start,
            'name': 'Анна', 'phone': '+373 69 000 000'})
        self.assertEqual(created['status'], 'new')
        self.assertEqual(created['end'] - created['start'], 3600)
        after = booking.slots(self.store, 'tulip', 'master-lilia', 'service-zhen', day, now=0)
        self.assertNotIn(start, [s['start'] for s in after])

    def test_same_slot_twice_is_busy(self):
        day = '2026-11-24'
        start = booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', day, now=0)[0]['start']
        payload = {'salon': 'tulip', 'master': 'master-lilia', 'service': 'service-muzh',
                   'start': start, 'name': 'Анна', 'phone': '+37369000000'}
        booking.create_request(self.store, payload)
        with self.assertRaises(LookupError):
            booking.create_request(self.store, payload)

    def test_cancel_frees_the_slot(self):
        day = '2026-11-24'
        start = booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', day, now=0)[0]['start']
        created = booking.create_request(self.store, {
            'salon': 'tulip', 'master': 'master-lilia', 'service': 'service-muzh',
            'start': start, 'name': 'Анна', 'phone': '+37369000000'})
        booking.set_status(self.store, 'tulip', created['id'], 'cancelled')
        again = booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', day, now=0)
        self.assertIn(start, [s['start'] for s in again])

    def test_validation_rejects_short_phone_and_bad_date(self):
        with self.assertRaises(ValueError):
            booking.create_request(self.store, {'salon': 'tulip', 'master': 'master-lilia',
                                                'service': 'service-muzh', 'start': 1,
                                                'name': 'Анна', 'phone': '12'})
        with self.assertRaises(ValueError):
            booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', '17.11.2026', now=0)

    def test_list_requests_for_day(self):
        day = '2026-11-24'
        start = booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', day, now=0)[0]['start']
        booking.create_request(self.store, {'salon': 'tulip', 'master': 'master-lilia',
                                            'service': 'service-muzh', 'start': start,
                                            'name': 'Анна', 'phone': '+37369000000'})
        rows = booking.list_requests(self.store, 'tulip', day)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], 'Анна')
        self.assertEqual(rows[0]['master_name'], 'Лилия Котеля')
        self.assertEqual(booking.list_requests(self.store, 'tulip', '2026-11-25'), [])

    def test_notification_text_names_salon_and_time(self):
        day = '2026-11-24'
        start = booking.slots(self.store, 'tulip', 'master-lilia', 'service-muzh', day, now=0)[0]['start']
        created = booking.create_request(self.store, {'salon': 'tulip', 'master': 'master-lilia',
                                                      'service': 'service-muzh', 'start': start,
                                                      'name': 'Анна', 'phone': '+37369000000'})
        text = booking.notification_text(created)
        self.assertIn('TULIP', text)
        self.assertIn('Анна', text)
        self.assertIn('09:00', text)


if __name__ == '__main__':
    unittest.main()

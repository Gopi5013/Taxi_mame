import unittest
import sqlite3

import taxi_bot.dispatch as dispatch_module
from taxi_bot.dispatch import (
    accept_offered_ride_for_driver,
    assign_next_online_driver,
    complete_ride_for_driver,
    create_ride,
    create_support_ticket,
    get_admin_dashboard_data,
    grant_driver_access,
    is_driver_allowed,
    reject_offered_ride_for_driver,
    record_booking_cancellation,
    register_driver,
    set_driver_online,
    start_ride_for_driver,
    submit_ride_feedback,
    update_driver_location,
)


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT DEFAULT '',
                online INTEGER NOT NULL DEFAULT 0,
                busy INTEGER NOT NULL DEFAULT 0,
                latitude REAL,
                longitude REAL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rides (
                ride_id TEXT PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                driver_id INTEGER,
                pickup_lat REAL NOT NULL,
                pickup_lon REAL NOT NULL,
                drop_lat REAL NOT NULL,
                drop_lon REAL NOT NULL,
                distance_km REAL NOT NULL,
                total_amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticket_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_access (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT DEFAULT '',
                created_by_admin INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_cancellations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ride_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ride_id TEXT NOT NULL,
                reviewer_id INTEGER NOT NULL,
                reviewee_id INTEGER NOT NULL,
                reviewer_role TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ride_id, reviewer_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ride_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ride_id TEXT NOT NULL,
                driver_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ride_id, driver_id)
            )
            """
        )
        self._old_dispatch_get_connection = dispatch_module.get_connection
        dispatch_module.get_connection = lambda: self.connection

    def tearDown(self) -> None:
        dispatch_module.get_connection = self._old_dispatch_get_connection
        self.connection.close()

    def test_assigns_nearest_online_driver(self) -> None:
        register_driver(101, "Near Driver", "near")
        register_driver(202, "Far Driver", "far")
        set_driver_online(101, True)
        set_driver_online(202, True)
        update_driver_location(101, 12.9716, 77.5946)
        update_driver_location(202, 13.0827, 80.2707)

        ride_id = create_ride(
            customer_id=999,
            pickup=(12.9720, 77.5950),
            drop=(12.9800, 77.6000),
            distance_km=2.0,
            total_amount=60.0,
        )
        assigned = assign_next_online_driver(ride_id)
        self.assertEqual(assigned, 101)

    def test_ride_lifecycle_start_and_complete(self) -> None:
        register_driver(303, "Lifecycle Driver", "life")
        set_driver_online(303, True)
        update_driver_location(303, 12.9716, 77.5946)

        ride_id = create_ride(
            customer_id=555,
            pickup=(12.9716, 77.5946),
            drop=(12.9900, 77.6100),
            distance_km=3.0,
            total_amount=90.0,
        )
        self.assertEqual(assign_next_online_driver(ride_id), 303)
        self.assertIsNotNone(accept_offered_ride_for_driver(303))

        started = start_ride_for_driver(303)
        self.assertIsNotNone(started)
        self.assertEqual(started["status"], "in_progress")

        completed = complete_ride_for_driver(303)
        self.assertIsNotNone(completed)
        self.assertEqual(completed["status"], "completed")

    def test_support_ticket_created(self) -> None:
        ticket_id = create_support_ticket(111, "Need help with booking issue")
        self.assertTrue(ticket_id.startswith("TKT-"))

        row = self.connection.execute(
            "SELECT user_id, message, status FROM support_tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(int(row["user_id"]), 111)
        self.assertEqual(row["message"], "Need help with booking issue")
        self.assertEqual(row["status"], "open")

    def test_ride_feedback_saved_once_per_reviewer(self) -> None:
        register_driver(303, "Lifecycle Driver", "life")
        set_driver_online(303, True)
        update_driver_location(303, 12.9716, 77.5946)
        ride_id = create_ride(
            customer_id=555,
            pickup=(12.9716, 77.5946),
            drop=(12.9900, 77.6100),
            distance_km=3.0,
            total_amount=90.0,
        )
        self.assertEqual(assign_next_online_driver(ride_id), 303)
        self.assertIsNotNone(accept_offered_ride_for_driver(303))
        self.assertIsNotNone(start_ride_for_driver(303))
        self.assertIsNotNone(complete_ride_for_driver(303))

        saved_once = submit_ride_feedback(
            ride_id=ride_id,
            reviewer_id=555,
            reviewee_id=303,
            reviewer_role="customer",
            rating=5,
            comment="Great ride",
        )
        saved_twice = submit_ride_feedback(
            ride_id=ride_id,
            reviewer_id=555,
            reviewee_id=303,
            reviewer_role="customer",
            rating=4,
            comment="Second try",
        )

        self.assertTrue(saved_once)
        self.assertFalse(saved_twice)

        row = self.connection.execute(
            """
            SELECT reviewer_id, reviewee_id, reviewer_role, rating, comment
            FROM ride_feedback
            WHERE ride_id = ? AND reviewer_id = ?
            """,
            (ride_id, 555),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(int(row["reviewer_id"]), 555)
        self.assertEqual(int(row["reviewee_id"]), 303)
        self.assertEqual(row["reviewer_role"], "customer")
        self.assertEqual(int(row["rating"]), 5)
        self.assertEqual(row["comment"], "Great ride")

    def test_admin_can_grant_driver_and_dashboard_has_counts(self) -> None:
        grant_driver_access(
            driver_user_id=7001,
            full_name="Admin Added Driver",
            username="admin_driver",
            admin_user_id=9001,
        )
        self.assertTrue(is_driver_allowed(7001))

        record_booking_cancellation(user_id=555)

        ride_id = create_ride(
            customer_id=555,
            pickup=(12.9716, 77.5946),
            drop=(12.9900, 77.6100),
            distance_km=3.0,
            total_amount=90.0,
        )
        self.connection.execute(
            "UPDATE rides SET driver_id = ?, status = 'completed' WHERE ride_id = ?",
            (7001, ride_id),
        )
        submit_ride_feedback(
            ride_id=ride_id,
            reviewer_id=555,
            reviewee_id=7001,
            reviewer_role="customer",
            rating=5,
            comment="Nice trip",
        )
        submit_ride_feedback(
            ride_id=ride_id,
            reviewer_id=7001,
            reviewee_id=555,
            reviewer_role="driver",
            rating=4,
            comment="Good rider",
        )

        dashboard = get_admin_dashboard_data()
        self.assertEqual(dashboard["completed_rides"], 1)
        self.assertEqual(dashboard["booking_cancels"], 1)
        self.assertEqual(dashboard["revenue"], 90.0)
        self.assertEqual(dashboard["customer_feedback_count"], 1)
        self.assertEqual(dashboard["driver_feedback_count"], 1)

    def test_reject_reassigns_to_next_driver(self) -> None:
        register_driver(101, "Near Driver", "near")
        register_driver(202, "Next Driver", "next")
        set_driver_online(101, True)
        set_driver_online(202, True)
        update_driver_location(101, 12.9716, 77.5946)
        update_driver_location(202, 12.9750, 77.6000)

        ride_id = create_ride(
            customer_id=999,
            pickup=(12.9720, 77.5950),
            drop=(12.9800, 77.6000),
            distance_km=2.0,
            total_amount=60.0,
        )
        self.assertEqual(assign_next_online_driver(ride_id), 101)
        result = reject_offered_ride_for_driver(101)
        self.assertIsNotNone(result)
        self.assertEqual(result["next_driver_id"], 202)


if __name__ == "__main__":
    unittest.main()

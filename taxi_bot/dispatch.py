import math
import uuid

from typing import Any

from taxi_bot.database import get_connection


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def register_driver(user_id: int, full_name: str, username: str | None) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO drivers (user_id, full_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                username=excluded.username,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, full_name, username or ""),
        )


def grant_driver_access(
    driver_user_id: int, full_name: str, username: str | None, admin_user_id: int
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO driver_access (
                user_id, full_name, username, created_by_admin, active
            )
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                username=excluded.username,
                created_by_admin=excluded.created_by_admin,
                active=1
            """,
            (driver_user_id, full_name.strip(), (username or "").strip(), admin_user_id),
        )
    register_driver(driver_user_id, full_name.strip(), (username or "").strip())


def is_driver_allowed(user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT active FROM driver_access WHERE user_id = ?", (user_id,)
        ).fetchone()
    return bool(row and int(row["active"]) == 1)


def is_registered_driver(user_id: int) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM drivers WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row is not None


def set_driver_online(user_id: int, is_online: bool) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT busy FROM drivers WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return False

        if not is_online and int(row["busy"]) == 1:
            return False

        connection.execute(
            """
            UPDATE drivers
            SET online = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (1 if is_online else 0, user_id),
        )
        return True


def update_driver_location(user_id: int, latitude: float, longitude: float) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE drivers
            SET latitude = ?, longitude = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (latitude, longitude, user_id),
        )
    return cursor.rowcount > 0


def driver_status_text(user_id: int) -> str:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT online, busy, latitude, longitude
            FROM drivers
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return "Driver not registered. Use /driver first."

    online = "Online" if int(row["online"]) == 1 else "Offline"
    busy = "Busy" if int(row["busy"]) == 1 else "Available"
    has_location = row["latitude"] is not None and row["longitude"] is not None
    location = "Location set" if has_location else "Location missing"
    return f"Status: {online}, {busy}, {location}"


def create_ride(
    customer_id: int,
    pickup: tuple[float, float],
    drop: tuple[float, float],
    distance_km: float,
    total_amount: float,
) -> str:
    ride_id = uuid.uuid4().hex[:8].upper()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO rides (
                ride_id, customer_id, driver_id,
                pickup_lat, pickup_lon,
                drop_lat, drop_lon,
                distance_km, total_amount, status
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, 'requested')
            """,
            (
                ride_id,
                customer_id,
                pickup[0],
                pickup[1],
                drop[0],
                drop[1],
                distance_km,
                total_amount,
            ),
        )
    return ride_id


def assign_next_online_driver(ride_id: str) -> int | None:
    with get_connection() as connection:
        ride = connection.execute(
            """
            SELECT pickup_lat, pickup_lon
            FROM rides
            WHERE ride_id = ? AND status = 'requested' AND driver_id IS NULL
            """,
            (ride_id,),
        ).fetchone()
        if not ride:
            return None

        pickup_lat = float(ride["pickup_lat"])
        pickup_lon = float(ride["pickup_lon"])

        driver_rows = connection.execute(
            """
            SELECT user_id, latitude, longitude
            FROM drivers
            WHERE online = 1 AND busy = 0 AND latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ).fetchall()

        if not driver_rows:
            return None

        nearest_driver_id = None
        nearest_distance = None

        for row in driver_rows:
            dist = _haversine_km(
                pickup_lat,
                pickup_lon,
                float(row["latitude"]),
                float(row["longitude"]),
            )
            if nearest_distance is None or dist < nearest_distance:
                nearest_distance = dist
                nearest_driver_id = int(row["user_id"])

        if nearest_driver_id is None:
            return None

        marked_busy = connection.execute(
            """
            UPDATE drivers
            SET busy = 1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND online = 1 AND busy = 0
            """,
            (nearest_driver_id,),
        )
        if marked_busy.rowcount == 0:
            return None

        assigned = connection.execute(
            """
            UPDATE rides
            SET driver_id = ?, status = 'assigned', updated_at = CURRENT_TIMESTAMP
            WHERE ride_id = ? AND status = 'requested' AND driver_id IS NULL
            """,
            (nearest_driver_id, ride_id),
        )
        if assigned.rowcount == 0:
            connection.execute(
                """
                UPDATE drivers
                SET busy = 0, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (nearest_driver_id,),
            )
            return None

        return nearest_driver_id


def create_support_ticket(user_id: int, message: str) -> str:
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO support_tickets (ticket_id, user_id, message)
            VALUES (?, ?, ?)
            """,
            (ticket_id, user_id, message.strip()),
        )
    return ticket_id


def record_booking_cancellation(user_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO booking_cancellations (user_id) VALUES (?)",
            (user_id,),
        )


def submit_ride_feedback(
    ride_id: str,
    reviewer_id: int,
    reviewee_id: int,
    reviewer_role: str,
    rating: int,
    comment: str,
) -> bool:
    if reviewer_role not in {"customer", "driver"}:
        return False
    if rating < 1 or rating > 5:
        return False

    with get_connection() as connection:
        ride_exists = connection.execute(
            """
            SELECT 1
            FROM rides
            WHERE ride_id = ? AND status = 'completed'
            """,
            (ride_id,),
        ).fetchone()
        if not ride_exists:
            return False

        existing = connection.execute(
            """
            SELECT 1
            FROM ride_feedback
            WHERE ride_id = ? AND reviewer_id = ?
            """,
            (ride_id, reviewer_id),
        ).fetchone()
        if existing:
            return False

        connection.execute(
            """
            INSERT INTO ride_feedback (
                ride_id, reviewer_id, reviewee_id, reviewer_role, rating, comment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ride_id, reviewer_id, reviewee_id, reviewer_role, rating, comment.strip()),
        )
        return True


def get_admin_dashboard_data() -> dict[str, Any]:
    with get_connection() as connection:
        completed_row = connection.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS revenue
            FROM rides
            WHERE status = 'completed'
            """
        ).fetchone()
        cancel_row = connection.execute(
            "SELECT COUNT(*) AS count FROM booking_cancellations"
        ).fetchone()
        customer_feedback_row = connection.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(AVG(rating), 0) AS avg_rating
            FROM ride_feedback
            WHERE reviewer_role = 'customer'
            """
        ).fetchone()
        driver_feedback_row = connection.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(AVG(rating), 0) AS avg_rating
            FROM ride_feedback
            WHERE reviewer_role = 'driver'
            """
        ).fetchone()
        recent_feedback_rows = connection.execute(
            """
            SELECT ride_id, reviewer_role, rating, comment, created_at
            FROM ride_feedback
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()

    return {
        "completed_rides": int(completed_row["count"]),
        "revenue": float(completed_row["revenue"]),
        "booking_cancels": int(cancel_row["count"]),
        "customer_feedback_count": int(customer_feedback_row["count"]),
        "customer_feedback_avg": float(customer_feedback_row["avg_rating"]),
        "driver_feedback_count": int(driver_feedback_row["count"]),
        "driver_feedback_avg": float(driver_feedback_row["avg_rating"]),
        "recent_feedback": [
            {
                "ride_id": row["ride_id"],
                "reviewer_role": row["reviewer_role"],
                "rating": int(row["rating"]),
                "comment": row["comment"] or "",
                "created_at": row["created_at"],
            }
            for row in recent_feedback_rows
        ],
    }


def get_driver_display_name(driver_id: int) -> str:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT full_name, username FROM drivers WHERE user_id = ?", (driver_id,)
        ).fetchone()

    if not row:
        return f"Driver {driver_id}"

    username = row["username"]
    if username:
        return f"{row['full_name']} (@{username})"
    return row["full_name"]


def get_active_ride_for_driver(driver_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM rides
            WHERE driver_id = ? AND status IN ('assigned', 'in_progress')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (driver_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "ride_id": row["ride_id"],
        "customer_id": row["customer_id"],
        "driver_id": row["driver_id"],
        "pickup": (float(row["pickup_lat"]), float(row["pickup_lon"])),
        "drop": (float(row["drop_lat"]), float(row["drop_lon"])),
        "distance_km": float(row["distance_km"]),
        "total_amount": float(row["total_amount"]),
        "status": row["status"],
    }


def start_ride_for_driver(driver_id: int) -> dict[str, Any] | None:
    ride = get_active_ride_for_driver(driver_id)
    if not ride or ride.get("status") != "assigned":
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE rides
            SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP
            WHERE ride_id = ?
            """,
            (ride["ride_id"],),
        )

    ride["status"] = "in_progress"
    return ride


def complete_ride_for_driver(driver_id: int) -> dict[str, Any] | None:
    ride = get_active_ride_for_driver(driver_id)
    if not ride or ride.get("status") != "in_progress":
        return None

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE rides
            SET status = 'completed', updated_at = CURRENT_TIMESTAMP
            WHERE ride_id = ?
            """,
            (ride["ride_id"],),
        )
        connection.execute(
            "UPDATE drivers SET busy = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (driver_id,),
        )

    ride["status"] = "completed"
    return ride

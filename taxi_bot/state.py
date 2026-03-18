BOOKING_STEP_KEY = "booking_step"
PICKUP_KEY = "pickup_location"
DROP_KEY = "drop_location"
DISTANCE_KEY = "trip_distance_km"
TOTAL_KEY = "trip_total_amount"
OTP_VALUE_KEY = "booking_otp_value"
OTP_TOKEN_KEY = "booking_otp_token"
FARE_STEP_KEY = "fare_step"
FARE_PICKUP_KEY = "fare_pickup_location"
SUPPORT_STEP_KEY = "support_step"
FEEDBACK_PENDING_KEY = "feedback_pending"
FEEDBACK_RIDE_KEY = "feedback_ride_id"
FEEDBACK_REVIEWEE_KEY = "feedback_reviewee_id"
FEEDBACK_ROLE_KEY = "feedback_reviewer_role"
ADMIN_AUTH_KEY = "admin_authenticated"
ADMIN_STEP_KEY = "admin_step"


def clear_booking_state(user_data: dict) -> None:
    user_data.pop(BOOKING_STEP_KEY, None)
    user_data.pop(PICKUP_KEY, None)
    user_data.pop(DROP_KEY, None)
    user_data.pop(DISTANCE_KEY, None)
    user_data.pop(TOTAL_KEY, None)
    user_data.pop(OTP_VALUE_KEY, None)
    user_data.pop(OTP_TOKEN_KEY, None)


def clear_fare_state(user_data: dict) -> None:
    user_data.pop(FARE_STEP_KEY, None)
    user_data.pop(FARE_PICKUP_KEY, None)


def clear_support_state(user_data: dict) -> None:
    user_data.pop(SUPPORT_STEP_KEY, None)


def clear_feedback_state(user_data: dict) -> None:
    user_data.pop(FEEDBACK_PENDING_KEY, None)
    user_data.pop(FEEDBACK_RIDE_KEY, None)
    user_data.pop(FEEDBACK_REVIEWEE_KEY, None)
    user_data.pop(FEEDBACK_ROLE_KEY, None)


def clear_admin_state(user_data: dict) -> None:
    user_data.pop(ADMIN_STEP_KEY, None)


def clear_all_session_state(user_data: dict) -> None:
    clear_booking_state(user_data)
    clear_fare_state(user_data)
    clear_support_state(user_data)

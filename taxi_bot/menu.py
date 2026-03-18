import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from taxi_bot.dispatch import (
    accept_offered_ride_for_driver,
    complete_ride_for_driver,
    driver_status_text,
    get_admin_dashboard_data,
    get_active_ride_for_driver,
    is_driver_allowed,
    reject_offered_ride_for_driver,
    record_booking_cancellation,
    register_driver,
    set_driver_online,
    start_ride_for_driver,
)
from taxi_bot.state import (
    ADMIN_AUTH_KEY,
    ADMIN_STEP_KEY,
    BOOKING_STEP_KEY,
    DISTANCE_KEY,
    DROP_KEY,
    FARE_STEP_KEY,
    FEEDBACK_PENDING_KEY,
    FEEDBACK_REVIEWEE_KEY,
    FEEDBACK_RIDE_KEY,
    FEEDBACK_ROLE_KEY,
    OTP_VALUE_KEY,
    PICKUP_KEY,
    SUPPORT_STEP_KEY,
    TOTAL_KEY,
    clear_all_session_state,
    clear_booking_state,
)

MAIN_MENU_TEXT = (
    "Welcome to Vinayaga Taxi\n\n"
    "1 Book Taxi\n"
    "2 Fare Estimate\n"
    "3 Contact Support"
)


def main_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("1 Book Taxi", callback_data="menu:book")],
        [InlineKeyboardButton("2 Fare Estimate", callback_data="menu:fare")],
        [InlineKeyboardButton("3 Contact Support", callback_data="menu:support")],
    ]
    return InlineKeyboardMarkup(keyboard)


def booking_action_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("Confirm Booking", callback_data="booking:confirm"),
            InlineKeyboardButton("Cancel Booking", callback_data="booking:cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def driver_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("Go Online", callback_data="driver:online"),
            InlineKeyboardButton("Go Offline", callback_data="driver:offline"),
        ],
        [
            InlineKeyboardButton("Accept Ride", callback_data="driver:accept"),
            InlineKeyboardButton("Reject Ride", callback_data="driver:reject"),
        ],
        [
            InlineKeyboardButton("My Status", callback_data="driver:status"),
            InlineKeyboardButton("Start Ride", callback_data="driver:start"),
            InlineKeyboardButton("Complete Ride", callback_data="driver:complete"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Create Driver", callback_data="admin:create_driver")],
        [InlineKeyboardButton("View Dashboard", callback_data="admin:dashboard")],
        [InlineKeyboardButton("Logout", callback_data="admin:logout")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _format_admin_dashboard() -> str:
    data = get_admin_dashboard_data()
    lines = [
        "Admin Dashboard",
        f"Completed rides: {data['completed_rides']}",
        f"Total revenue: Rs {data['revenue']:.2f}",
        f"Booking cancels: {data['booking_cancels']}",
        (
            "Rider feedback: "
            f"{data['customer_feedback_count']} entries, avg {data['customer_feedback_avg']:.2f}/5"
        ),
        (
            "Driver feedback: "
            f"{data['driver_feedback_count']} entries, avg {data['driver_feedback_avg']:.2f}/5"
        ),
        "",
        "Recent feedback:",
    ]
    recent = data.get("recent_feedback", [])
    if not recent:
        lines.append("No feedback records yet.")
    else:
        for item in recent:
            comment = item["comment"].strip()
            comment_text = f" | {comment}" if comment else ""
            lines.append(
                f"- Ride {item['ride_id']} [{item['reviewer_role']}] "
                f"{item['rating']}/5{comment_text}"
            )
    return "\n".join(lines)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    data = query.data or ""
    if data.startswith("admin:"):
        if not context.user_data.get(ADMIN_AUTH_KEY):
            await query.message.reply_text("Admin login required. Use /admin.")
            return

        if data == "admin:create_driver":
            context.user_data[ADMIN_STEP_KEY] = "create_driver"
            await query.message.reply_text(
                "Send driver details in this format:\n"
                "123456789, Driver Full Name, username_optional"
            )
            return
        if data == "admin:dashboard":
            await query.message.reply_text(
                _format_admin_dashboard(), reply_markup=admin_menu_markup()
            )
            return
        if data == "admin:logout":
            context.user_data[ADMIN_AUTH_KEY] = False
            context.user_data.pop(ADMIN_STEP_KEY, None)
            await query.message.reply_text("Admin logged out successfully.")
            return
        await query.message.reply_text("Unknown admin option.")
        return

    if data == "menu:book":
        clear_all_session_state(context.user_data)
        context.user_data[BOOKING_STEP_KEY] = "pickup"
        text = "Send your pickup location as a Telegram location or coordinates."
    elif data == "menu:fare":
        clear_all_session_state(context.user_data)
        context.user_data[FARE_STEP_KEY] = "pickup"
        text = (
            "Fare Estimate started.\n"
            "Send pickup location as Telegram location or coordinates."
        )
    elif data == "menu:support":
        clear_all_session_state(context.user_data)
        context.user_data[SUPPORT_STEP_KEY] = "awaiting_message"
        text = "Contact Support selected.\nPlease describe your issue in one message."
    elif data == "booking:confirm":
        pickup = context.user_data.get(PICKUP_KEY)
        drop = context.user_data.get(DROP_KEY)
        distance = context.user_data.get(DISTANCE_KEY)
        total = context.user_data.get(TOTAL_KEY)

        if pickup and drop and distance is not None and total is not None:
            otp_value = str(random.randint(1000, 9999))
            context.user_data[OTP_VALUE_KEY] = otp_value
            context.user_data[BOOKING_STEP_KEY] = "otp"
            text = (
                "Enter 4-digit OTP to confirm booking.\n"
                "Use received OTP or any random 4 numbers.\n"
                f"Demo OTP: {otp_value}"
            )
        else:
            text = "No active booking found. Choose Book Taxi to start again."
    elif data == "booking:cancel":
        should_count_cancel = any(
            key in context.user_data
            for key in {BOOKING_STEP_KEY, PICKUP_KEY, DROP_KEY, DISTANCE_KEY, TOTAL_KEY}
        )
        if should_count_cancel and query.from_user:
            record_booking_cancellation(query.from_user.id)
        clear_booking_state(context.user_data)
        text = "Booking canceled. Choose Book Taxi whenever you are ready."
    elif data == "driver:online":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        register_driver(user.id, user.full_name, user.username)
        set_driver_online(user.id, True)
        text = (
            "You are now online and ready to receive rides.\n"
            "Send your current Telegram location to enable nearest-driver matching."
        )
    elif data == "driver:offline":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        register_driver(user.id, user.full_name, user.username)
        changed = set_driver_online(user.id, False)
        if changed:
            text = "You are now offline."
        else:
            text = "Cannot go offline while a ride is active."
    elif data == "driver:status":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        register_driver(user.id, user.full_name, user.username)
        text = driver_status_text(user.id)
        active_ride = get_active_ride_for_driver(user.id)
        if active_ride:
            text += (
                f"\nActive ride: {active_ride['ride_id']} ({active_ride['status']})"
            )
    elif data == "driver:start":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        ride = start_ride_for_driver(user.id)
        if not ride:
            text = "No assigned ride ready to start."
        else:
            text = f"Ride {ride['ride_id']} started."
            await context.bot.send_message(
                chat_id=ride["customer_id"],
                text=f"Driver started your ride. Ride ID: {ride['ride_id']}",
            )
    elif data == "driver:accept":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        ride = accept_offered_ride_for_driver(user.id)
        if not ride:
            text = "No offered ride to accept."
        else:
            text = f"Ride {ride['ride_id']} accepted."
            await context.bot.send_message(
                chat_id=ride["customer_id"],
                text=f"Driver accepted your ride. Ride ID: {ride['ride_id']}",
            )
    elif data == "driver:reject":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        result = reject_offered_ride_for_driver(user.id)
        if not result:
            text = "No offered ride to reject."
        else:
            text = "Ride rejected. Searching for another driver."
            next_driver_id = result.get("next_driver_id")
            ride_id = result["ride_id"]
            customer_id = result["customer_id"]

            if next_driver_id is None:
                await context.bot.send_message(
                    chat_id=customer_id,
                    text="A driver rejected your ride. We are still searching for available drivers.",
                )
            else:
                await context.bot.send_message(
                    chat_id=next_driver_id,
                    text=(
                        "New ride request for you.\n"
                        f"Ride ID: {ride_id}\n"
                        "Please Accept or Reject from Driver panel."
                    ),
                    reply_markup=driver_menu_markup(),
                )
    elif data == "driver:complete":
        user = query.from_user
        if not is_driver_allowed(user.id):
            text = "Driver access denied. Ask admin to create your driver account."
            await query.message.reply_text(text)
            return
        ride = complete_ride_for_driver(user.id)
        if not ride:
            text = "No in-progress ride to complete."
        else:
            text = f"Ride {ride['ride_id']} completed."
            context.user_data[FEEDBACK_PENDING_KEY] = True
            context.user_data[FEEDBACK_RIDE_KEY] = ride["ride_id"]
            context.user_data[FEEDBACK_REVIEWEE_KEY] = int(ride["customer_id"])
            context.user_data[FEEDBACK_ROLE_KEY] = "driver"

            customer_data = context.application.user_data.setdefault(
                int(ride["customer_id"]), {}
            )
            customer_data[FEEDBACK_PENDING_KEY] = True
            customer_data[FEEDBACK_RIDE_KEY] = ride["ride_id"]
            customer_data[FEEDBACK_REVIEWEE_KEY] = int(user.id)
            customer_data[FEEDBACK_ROLE_KEY] = "customer"

            await context.bot.send_message(
                chat_id=ride["customer_id"],
                text=(
                    f"Ride completed successfully. Ride ID: {ride['ride_id']}\n"
                    "Please rate your driver from 1-5 and optional comment.\n"
                    "Example: 5 Smooth and safe ride\n"
                    "Type 'skip' to skip."
                ),
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"Ride completed successfully. Ride ID: {ride['ride_id']}\n"
                    "Please rate the customer (1-5) and optional comment.\n"
                    "Example: 5 On-time pickup\n"
                    "Type 'skip' to skip."
                ),
            )
    else:
        text = "Unknown option."

    await query.message.reply_text(text)


def menu_text_reply(message_text: str) -> str | None:
    text = (message_text or "").strip().lower()
    if text in {"1 book taxi", "book taxi"}:
        return "Send your pickup location as a Telegram location or coordinates."
    if text in {"2 fare estimate", "fare estimate"}:
        return "Fare Estimate selected. Send pickup location first."
    if text in {"3 contact support", "contact support"}:
        return "Contact Support selected. Describe your issue in one message."
    return None


def is_book_taxi_text(message_text: str) -> bool:
    text = (message_text or "").strip().lower()
    return text in {"1 book taxi", "book taxi"}


def is_fare_estimate_text(message_text: str) -> bool:
    text = (message_text or "").strip().lower()
    return text in {"2 fare estimate", "fare estimate"}


def is_contact_support_text(message_text: str) -> bool:
    text = (message_text or "").strip().lower()
    return text in {"3 contact support", "contact support"}

import asyncio
import re
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from taxi_bot.config import ADMIN_PASSWORD, CONFIRM_DELAY_SECONDS, RATE_PER_KM
from taxi_bot.dispatch import (
    assign_next_online_driver,
    create_support_ticket,
    create_ride,
    get_driver_display_name,
    grant_driver_access,
    is_driver_allowed,
    is_registered_driver,
    register_driver,
    submit_ride_feedback,
    update_driver_location,
)
from taxi_bot.menu import (
    MAIN_MENU_TEXT,
    admin_menu_markup,
    booking_action_markup,
    is_contact_support_text,
    is_fare_estimate_text,
    driver_menu_markup,
    is_book_taxi_text,
    main_menu_markup,
    menu_text_reply,
)
from taxi_bot.geocode import format_place_label
from taxi_bot.state import (
    ADMIN_AUTH_KEY,
    ADMIN_STEP_KEY,
    BOOKING_STEP_KEY,
    DISTANCE_KEY,
    DROP_KEY,
    FARE_PICKUP_KEY,
    FARE_STEP_KEY,
    FEEDBACK_PENDING_KEY,
    FEEDBACK_REVIEWEE_KEY,
    FEEDBACK_RIDE_KEY,
    FEEDBACK_ROLE_KEY,
    OTP_TOKEN_KEY,
    OTP_VALUE_KEY,
    PICKUP_KEY,
    SUPPORT_STEP_KEY,
    TOTAL_KEY,
    clear_all_session_state,
    clear_admin_state,
    clear_booking_state,
    clear_feedback_state,
    clear_fare_state,
    clear_support_state,
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

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


def _coords_from_message(update: Update) -> tuple[float, float] | None:
    message = update.message
    if not message:
        return None

    if message.location:
        return (float(message.location.latitude), float(message.location.longitude))

    text = (message.text or "").strip()
    if not text or "," not in text:
        return None

    left, right = text.split(",", 1)
    try:
        lat = float(left.strip())
        lon = float(right.strip())
    except ValueError:
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    return (lat, lon)


async def _send_delayed_booking_success(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, token: str
) -> None:
    await asyncio.sleep(CONFIRM_DELAY_SECONDS)

    if context.user_data.get(OTP_TOKEN_KEY) != token:
        return

    pickup = context.user_data.get(PICKUP_KEY)
    drop = context.user_data.get(DROP_KEY)
    distance = context.user_data.get(DISTANCE_KEY)
    total = context.user_data.get(TOTAL_KEY)

    if pickup and drop and distance is not None and total is not None:
        pickup_label = await asyncio.to_thread(
            format_place_label, float(pickup[0]), float(pickup[1])
        )
        drop_label = await asyncio.to_thread(
            format_place_label, float(drop[0]), float(drop[1])
        )
        ride_id = create_ride(chat_id, pickup, drop, distance, total)
        driver_id = assign_next_online_driver(ride_id)

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Congrats! Vinayaga Taxi booking confirmed.\n"
                f"Ride ID: {ride_id}\n"
                f"Pickup: {pickup_label}\n"
                f"Drop: {drop_label}\n"
                f"Distance: {distance:.2f} km\n"
                f"Total: Rs {total:.2f}"
            ),
        )

        if driver_id is None:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No drivers are online right now. We will assign one soon.",
            )
        else:
            driver_name = get_driver_display_name(driver_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Driver assigned: {driver_name}.",
            )
            await context.bot.send_message(
                chat_id=driver_id,
                text=(
                    "New ride assigned.\n"
                    f"Ride ID: {ride_id}\n"
                    f"Pickup: {pickup_label}\n"
                    f"Drop: {drop_label}\n"
                    f"Distance: {distance:.2f} km\n"
                    f"Estimated fare: Rs {total:.2f}\n\n"
                    "Use Driver panel and tap Start Ride when pickup begins."
                ),
                reply_markup=driver_menu_markup(),
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Booking session expired. Please choose Book Taxi again.",
        )

    clear_booking_state(context.user_data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=main_menu_markup())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        await update.message.reply_text("Unable to read your Telegram user id.")
        return
    await update.message.reply_text(
        f"Your Telegram user id is: {user.id}\n"
        "Share this id with admin to create your driver access."
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_PASSWORD:
        await update.message.reply_text(
            "Admin password is not configured. Set ADMIN_PASSWORD in .env."
        )
        return

    if context.user_data.get(ADMIN_AUTH_KEY):
        clear_admin_state(context.user_data)
        await update.message.reply_text(
            "Admin panel:", reply_markup=admin_menu_markup()
        )
        return

    context.user_data[ADMIN_STEP_KEY] = "login"
    await update.message.reply_text("Enter admin password:")


async def driver_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if not is_driver_allowed(user.id):
        await update.message.reply_text(
            "Driver access denied. Ask admin to create your driver account first."
        )
        return

    register_driver(user.id, user.full_name, user.username)
    await update.message.reply_text(
        "Driver panel:\nUse the buttons below to manage your availability and rides.",
        reply_markup=driver_menu_markup(),
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = (message.text or "") if message else ""
    booking_step = context.user_data.get(BOOKING_STEP_KEY)
    fare_step = context.user_data.get(FARE_STEP_KEY)
    support_step = context.user_data.get(SUPPORT_STEP_KEY)
    feedback_pending = context.user_data.get(FEEDBACK_PENDING_KEY)
    admin_step = context.user_data.get(ADMIN_STEP_KEY)

    if admin_step == "login":
        entered = text.strip()
        if entered == ADMIN_PASSWORD and ADMIN_PASSWORD:
            context.user_data[ADMIN_AUTH_KEY] = True
            clear_admin_state(context.user_data)
            await update.message.reply_text(
                "Admin login successful.", reply_markup=admin_menu_markup()
            )
            return
        clear_admin_state(context.user_data)
        await update.message.reply_text("Invalid password. Use /admin and try again.")
        return

    if admin_step == "create_driver":
        if not context.user_data.get(ADMIN_AUTH_KEY):
            clear_admin_state(context.user_data)
            await update.message.reply_text("Admin login required. Use /admin.")
            return

        raw = text.strip()
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 2:
            await update.message.reply_text(
                "Invalid format.\nUse: 123456789, Driver Full Name, username_optional"
            )
            return

        try:
            driver_user_id = int(parts[0])
        except ValueError:
            await update.message.reply_text("Driver Telegram user id must be numeric.")
            return

        full_name = parts[1]
        username = parts[2].lstrip("@") if len(parts) >= 3 and parts[2] else ""
        if not full_name:
            await update.message.reply_text("Driver full name is required.")
            return
        if not update.effective_user:
            await update.message.reply_text("Unable to identify admin account.")
            return

        grant_driver_access(
            driver_user_id=driver_user_id,
            full_name=full_name,
            username=username,
            admin_user_id=update.effective_user.id,
        )
        clear_admin_state(context.user_data)
        await update.message.reply_text(
            "Driver created successfully.\n"
            f"Driver ID: {driver_user_id}\n"
            f"Name: {full_name}\n"
            "They can now access /driver.",
            reply_markup=admin_menu_markup(),
        )
        return

    if feedback_pending:
        lowered = text.strip().lower()
        if lowered == "skip":
            clear_feedback_state(context.user_data)
            await update.message.reply_text("Feedback skipped. Thanks for riding with us.")
            return

        match = re.fullmatch(r"([1-5])(?:\s+(.+))?", text.strip())
        if not match:
            await update.message.reply_text(
                "Please send feedback as:\n"
                "5 Great ride\n"
                "or type 'skip' to skip."
            )
            return

        rating = int(match.group(1))
        comment = (match.group(2) or "").strip()
        ride_id = context.user_data.get(FEEDBACK_RIDE_KEY)
        reviewee_id = context.user_data.get(FEEDBACK_REVIEWEE_KEY)
        reviewer_role = context.user_data.get(FEEDBACK_ROLE_KEY)

        if (
            not isinstance(ride_id, str)
            or not isinstance(reviewee_id, int)
            or reviewer_role not in {"customer", "driver"}
            or not update.effective_user
        ):
            clear_feedback_state(context.user_data)
            await update.message.reply_text(
                "Feedback session expired. Thanks for your time."
            )
            return

        saved = submit_ride_feedback(
            ride_id=ride_id,
            reviewer_id=update.effective_user.id,
            reviewee_id=reviewee_id,
            reviewer_role=reviewer_role,
            rating=rating,
            comment=comment,
        )
        clear_feedback_state(context.user_data)

        if not saved:
            await update.message.reply_text(
                "Feedback could not be saved (already submitted or ride not found)."
            )
            return

        await update.message.reply_text("Thanks! Your feedback has been recorded.")
        return

    if support_step == "awaiting_message":
        support_message = text.strip()
        if not support_message:
            await update.message.reply_text(
                "Please type your support issue as a text message."
            )
            return

        ticket_id = create_support_ticket(update.effective_user.id, support_message)
        clear_support_state(context.user_data)
        await update.message.reply_text(
            "Thanks for contacting support.\n"
            f"Ticket ID: {ticket_id}\n"
            "Our team will follow up shortly."
        )
        return

    if booking_step == "otp":
        otp_text = text.strip()
        if not re.fullmatch(r"\d{4}", otp_text):
            await update.message.reply_text("Enter a valid 4-digit OTP.")
            return

        context.user_data[OTP_VALUE_KEY] = otp_text
        context.user_data[BOOKING_STEP_KEY] = "otp_pending"
        token = uuid.uuid4().hex
        context.user_data[OTP_TOKEN_KEY] = token

        await update.message.reply_text(
            f"OTP accepted. Booking will be confirmed in {CONFIRM_DELAY_SECONDS} seconds."
        )
        context.application.create_task(
            _send_delayed_booking_success(context, update.effective_chat.id, token)
        )
        return

    if booking_step == "otp_pending":
        await update.message.reply_text(
            "Booking confirmation is in progress. Please wait a few seconds."
        )
        return

    if booking_step == "pickup":
        pickup_coords = _coords_from_message(update)
        if pickup_coords is None:
            await update.message.reply_text(
                "Send your pickup location as a Telegram location or coordinates like:\n"
                "12.9716, 77.5946"
            )
            return

        context.user_data[PICKUP_KEY] = pickup_coords
        context.user_data[BOOKING_STEP_KEY] = "drop"
        await update.message.reply_text(
            "Send your drop location as a Telegram location or coordinates like:\n"
            "12.9716, 77.5946"
        )
        return

    if booking_step == "drop":
        drop_coords = _coords_from_message(update)
        if drop_coords is None:
            await update.message.reply_text(
                "Send your drop location as a Telegram location or coordinates like:\n"
                "12.9716, 77.5946"
            )
            return

        pickup_coords = context.user_data.get(PICKUP_KEY)
        if not isinstance(pickup_coords, tuple) or len(pickup_coords) != 2:
            context.user_data[BOOKING_STEP_KEY] = "pickup"
            await update.message.reply_text(
                "Pickup location missing. Send your pickup location again."
            )
            return

        context.user_data[DROP_KEY] = drop_coords
        context.user_data.pop(BOOKING_STEP_KEY, None)

        distance_km = _haversine_km(
            pickup_coords[0], pickup_coords[1], drop_coords[0], drop_coords[1]
        )
        total_amount = distance_km * RATE_PER_KM
        context.user_data[DISTANCE_KEY] = distance_km
        context.user_data[TOTAL_KEY] = total_amount
        pickup_label = await asyncio.to_thread(
            format_place_label, float(pickup_coords[0]), float(pickup_coords[1])
        )
        drop_label = await asyncio.to_thread(
            format_place_label, float(drop_coords[0]), float(drop_coords[1])
        )

        await update.message.reply_text(
            "Booking details:\n"
            f"Pickup: {pickup_label}\n"
            f"Drop: {drop_label}\n\n"
            f"Distance: {distance_km:.2f} km\n"
            f"Rate: Rs {RATE_PER_KM}/km\n"
            f"Total: Rs {total_amount:.2f}\n\n"
            "Confirm or cancel this booking:",
            reply_markup=booking_action_markup(),
        )
        return

    if fare_step == "pickup":
        pickup_coords = _coords_from_message(update)
        if pickup_coords is None:
            await update.message.reply_text(
                "Send pickup location as Telegram location or coordinates like:\n"
                "12.9716, 77.5946"
            )
            return

        context.user_data[FARE_PICKUP_KEY] = pickup_coords
        context.user_data[FARE_STEP_KEY] = "drop"
        await update.message.reply_text(
            "Now send drop location as Telegram location or coordinates."
        )
        return

    if fare_step == "drop":
        drop_coords = _coords_from_message(update)
        if drop_coords is None:
            await update.message.reply_text(
                "Send drop location as Telegram location or coordinates like:\n"
                "12.9716, 77.5946"
            )
            return

        pickup_coords = context.user_data.get(FARE_PICKUP_KEY)
        if not isinstance(pickup_coords, tuple) or len(pickup_coords) != 2:
            context.user_data[FARE_STEP_KEY] = "pickup"
            await update.message.reply_text(
                "Pickup location missing. Please send pickup location again."
            )
            return

        distance_km = _haversine_km(
            pickup_coords[0], pickup_coords[1], drop_coords[0], drop_coords[1]
        )
        total_amount = distance_km * RATE_PER_KM
        clear_fare_state(context.user_data)
        pickup_label = await asyncio.to_thread(
            format_place_label, float(pickup_coords[0]), float(pickup_coords[1])
        )
        drop_label = await asyncio.to_thread(
            format_place_label, float(drop_coords[0]), float(drop_coords[1])
        )
        await update.message.reply_text(
            "Estimated fare details:\n"
            f"Pickup: {pickup_label}\n"
            f"Drop: {drop_label}\n"
            f"Distance: {distance_km:.2f} km\n"
            f"Rate: Rs {RATE_PER_KM}/km\n"
            f"Estimated Total: Rs {total_amount:.2f}"
        )
        return

    if is_book_taxi_text(text):
        clear_all_session_state(context.user_data)
        context.user_data[BOOKING_STEP_KEY] = "pickup"
        await update.message.reply_text(
            "Send your pickup location as a Telegram location or coordinates like:\n"
            "12.9716, 77.5946"
        )
        return

    if is_fare_estimate_text(text):
        clear_all_session_state(context.user_data)
        context.user_data[FARE_STEP_KEY] = "pickup"
        await update.message.reply_text(
            "Fare Estimate started.\n"
            "Send pickup location as Telegram location or coordinates."
        )
        return

    if is_contact_support_text(text):
        clear_all_session_state(context.user_data)
        context.user_data[SUPPORT_STEP_KEY] = "awaiting_message"
        await update.message.reply_text(
            "Contact Support selected.\nPlease describe your issue in one message."
        )
        return

    if message and message.location and update.effective_user:
        user_id = update.effective_user.id
        if is_registered_driver(user_id):
            updated = update_driver_location(
                user_id,
                float(message.location.latitude),
                float(message.location.longitude),
            )
            if updated:
                await update.message.reply_text(
                    "Driver location updated. Nearest-ride matching is active."
                )
                return

    menu_reply = menu_text_reply(text)
    if menu_reply is not None:
        await update.message.reply_text(menu_reply)
        return

    lowered = text.lower()
    if "hello" in lowered:
        reply = "Hello!"
    elif "how are you" in lowered:
        reply = "I'm fine! What about you?"
    elif "bye" in lowered:
        reply = "Goodbye!"
    elif "what is your name" in lowered:
        reply = "I'm Vinayaga Taxi bot."
    else:
        reply = "I don't understand."

    await update.message.reply_text(reply)

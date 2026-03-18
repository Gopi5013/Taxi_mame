# Vinayaga Taxi Bot (Polling)

Telegram taxi booking bot using long polling.

## Project Structure

```text
d:\Sample
|-- main.py
|-- requirements.txt
|-- .env
|-- data/
|-- tests/
`-- taxi_bot
    |-- __init__.py
    |-- app.py
    |-- config.py
    |-- database.py
    |-- dispatch.py
    |-- handlers.py
    |-- menu.py
    `-- state.py
```

## Setup

1. Create and activate virtual environment:

```powershell
python -m venv myenv
.\myenv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Set bot token in `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_PASSWORD=your_admin_password
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

## Run

```powershell
python main.py
```

## Driver Flow (MVP)

- Admin must create the driver account first from `/admin`
- Open driver panel with `/driver`
- Tap `Go Online` to receive ride assignments
- Send current Telegram location after going online
- When assigned, tap `Start Ride` and then `Complete Ride`
- Driver must accept the offered ride before `Start Ride`
- Driver can reject an offered ride; system reassigns to next available driver
- Driver assignment uses nearest online driver by distance to pickup
- After completion, both customer and driver are prompted for feedback (`1-5` + optional comment)

## Customer Flows

- `Book Taxi`: pickup -> drop -> fare summary -> confirm -> OTP -> delayed confirmation
- `Fare Estimate`: pickup -> drop -> estimated distance and amount
- `Contact Support`: creates a support ticket ID and confirms submission
- Pickup/drop coordinates are reverse-geocoded to place names when network is available (falls back to coordinates)
- Booking confirmation delay is `10` seconds

## Admin Flow

- Send `/admin` and login with `ADMIN_PASSWORD`
- Drivers can send `/myid` to get their Telegram numeric user id
- `Create Driver`: add authorized drivers using:
  - `123456789, Driver Full Name, username_optional`
- `View Dashboard` shows:
  - completed rides
  - total revenue
  - booking cancel count
  - rider feedback summary
  - driver feedback summary
  - recent feedback records

## Testing

```powershell
python -m unittest discover -s tests -v
```

## Notes

- No Docker.
- No webhook.
- Bot runs only in polling mode.
- Supports Neon Postgres using `DATABASE_URL`.
- If `DATABASE_URL` is not set, falls back to SQLite at `data/taxi_bot.sqlite3`.

## Neon + Render Deployment

1. Create a Neon project and database.
2. Copy Neon connection string and ensure it includes `sslmode=require`.
3. In Render, create a **Background Worker** from this repo.
4. Set build/start commands:
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`
5. Add Render environment variables:
   - `BOT_TOKEN`
   - `ADMIN_PASSWORD`
   - `DATABASE_URL` (Neon connection string)
6. Deploy and verify via `/start`, `/admin`, `/myid`, `/driver`.

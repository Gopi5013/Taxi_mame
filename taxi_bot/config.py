import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
RATE_PER_KM = 30
CONFIRM_DELAY_SECONDS = 10
DRIVER_SEARCH_RADIUS_KM = 5.0

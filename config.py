import os
from pytz import timezone, UTC
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

BOT_TOKEN = os.getenv("BOT_TOKEN")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/telegram/webhook"

LOCAL_TZ = timezone("Europe/Kyiv")
UTC_TZ = UTC

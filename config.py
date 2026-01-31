import os
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
THREAD_ID = int(os.getenv("THREAD_ID"))

MONTHS_UA = ["січень","лютий","березень","квітень","травень","червень",
             "липень","серпень","вересень","жовтень","листопад","грудень"]

now = datetime.now(ZoneInfo("Europe/Kiev"))
CURRENT_MONTH = MONTHS_UA[now.month - 1]

PAYMENT_CARD = "5168745148819912"
PAYMENT_AMOUNT = 170
PAYMENT_DEADLINE = 10  # до 10 числа

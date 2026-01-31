import json, datetime, schedule, time, threading
from config import TOKEN, CHAT_ID, THREAD_ID, CURRENT_MONTH, PAYMENT_CARD, PAYMENT_AMOUNT, PAYMENT_DEADLINE
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, Updater, CallbackContext
from zoneinfo import ZoneInfo

# --- Завантаження JSON ---
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

history = load_json("history.json")
templates = load_json("messages_template.json")
active_apts = load_json("active_apartments.json")

bot = Bot(TOKEN)
updater = Updater(TOKEN, use_context=True)
dispatcher = updater.dispatcher

# --- Функції парсингу повідомлень ---
def parse_payment(message):
    message = message.lower()
    if "кв" not in message or "оплачено" not in message:
        return None
    try:
        parts = message.split("кв")[1].split("–")[0].strip()
        apt_num = int(parts)
    except:
        return None
    months = []
    for m in ["січень","лютий","березень","квітень","травень","червень",
              "липень","серпень","вересень","жовтень","листопад","грудень"]:
        if m in message:
            months.append(m)
    if not months:
        months = [CURRENT_MONTH]
    return apt_num, months

def update_history(message):
    parsed = parse_payment(message)
    if not parsed:
        return
    apt, months = parsed
    if str(apt) not in history:
        history[str(apt)] = {}
    for m in months:
        history[str(apt)][m] = True
    save_json("history.json", history)

def handle_updates():
    updates = bot.get_updates(timeout=10)
    for u in updates:
        if u.message and hasattr(u.message, 'message_thread_id') and u.message.message_thread_id == THREAD_ID:
            text = u.message.text
            update_history(text)

def get_waiting_list(month):
    waiting = []
    for apt in active_apts:
        if str(apt) not in history or history[str(apt)].get(month) != True:
            waiting.append(f"Кв.{apt} ⏳")
    return "\n".join(waiting) if waiting else "✅ Всі оплатили!"

# --- Повідомлення ---
def send_welcome():
    text = templates["welcome"].format(
        month=CURRENT_MONTH,
        card=PAYMENT_CARD,
        amount=PAYMENT_AMOUNT,
        deadline=PAYMENT_DEADLINE
    )
    msg = bot.send_message(CHAT_ID, text, parse_mode=ParseMode.MARKDOWN)
    bot.pin_chat_message(CHAT_ID, msg.message_id)
    print("[INFO] Вітальне повідомлення відправлено і закріплено.")

def send_report():
    text = templates["report"].format(waiting_list=get_waiting_list(CURRENT_MONTH))
    bot.send_message(CHAT_ID, text, parse_mode=ParseMode.MARKDOWN)
    print("[INFO] Звіт по оплатах відправлено.")

def send_reminder():
    text = templates["reminder"].format(waiting_list=get_waiting_list(CURRENT_MONTH))
    bot.send_message(CHAT_ID, text, parse_mode=ParseMode.MARKDOWN)
    print("[INFO] Нагадування відправлено.")

# --- Команда /send_now ---
def send_now(update: Update, context: CallbackContext):
    handle_updates()  # оновлюємо історію перед повідомленнями
    send_welcome()
    send_report()
    send_reminder()
    update.message.reply_text("✅ Всі тестові повідомлення відправлені!")

dispatcher.add_handler(CommandHandler("send_now", send_now))

# --- Планування щоденного оновлення і повідомлень ---
def schedule_jobs():
    tz = ZoneInfo("Europe/Kiev")
    schedule.every().day.at("23:00").do(handle_updates)
    schedule.every().day.at("09:00").do(lambda: send_welcome() if datetime.datetime.now(tz).day==1 else None)
    schedule.every().day.at("12:00").do(lambda: send_report() if datetime.datetime.now(tz).day==11 else None)
    schedule.every().day.at("12:00").do(lambda: send_reminder() if datetime.datetime.now(tz).day==19 else None)
    while True:
        schedule.run_pending()
        time.sleep(10)

threading.Thread(target=schedule_jobs, daemon=True).start()

# --- Основний цикл ---
print("[INFO] SusidBot-Cleaning запущено...")
updater.start_polling()
while True:
    handle_updates()
    time.sleep(5)

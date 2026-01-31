import os
import json
import re
from datetime import datetime
import telebot
import pytz

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

ACTIVE_APARTMENTS = [6, 7, 11, 14, 17, 18, 19, 20, 22, 23, 26, 33, 34, 36, 39, 42, 43, 44, 46]

bot = telebot.TeleBot(TOKEN)

def get_month_ukr(month_idx):
    months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень",
              7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    return months.get(month_idx, "місяць")

def load_history():
    if os.path.exists('history.json'):
        with open('history.json', 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {"01-2026": [], "02-2026": []}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_messages():
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    curr_key = now_dt.strftime('%m-%Y')
    if curr_key not in history: history[curr_key] = []

    # Бот бере повідомлення за останні 24 години
    updates = bot.get_updates(limit=100, timeout=10)
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            text = u.message.text.lower() if u.message.text else ""
            numbers = re.findall(r'(\d+)', text)
            keywords = ['оплат', 'сплач', 'ок', 'готово', 'є', '+', '✅']
            if any(k in text for k in keywords):
                for num in numbers:
                    if int(num) in ACTIVE_APARTMENTS and num not in history[curr_key]:
                        history[curr_key].append(num)
    save_history(history)
    return history[curr_key]

def run_logic():
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    paid = scan_messages()
    unpaid = sorted([str(a) for a in ACTIVE_APARTMENTS if str(a) not in paid], key=int)
    month_name = get_month_ukr(now.month)

    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

    # ТЕКСТИ ПОВІДОМЛЕНЬ
    msg_start = (f"🌿 Почався {month_name} — дякуємо за підтримку чистоти 💚\n\n"
                 f"💳 **5168 7451 4881 9912**\n💰 170 грн/міс\n"
                 f"✅ Після оплати: «кв. [номер] – оплачено»")
    
    msg_report = f"📊 **Звіт по оплатах ({month_name}):**\n\n✅ Оплатили: " + \
                 (", ".join(sorted(paid, key=int)) if paid else "поки що ніхто") + \
                 (f"\n\n⏳ Очікуємо: {', '.join(unpaid)}" if unpaid else "\n\n🎉 Всі оплатили!")

    msg_remind = f"✨ Нагадуємо про оплату прибирання! Кв: {', '.join(unpaid)} 💚"

    # ЛОГІКА ВІДПРАВКИ
    if is_manual:
        bot.send_message(CHAT_ID, "🧪 **ТЕСТОВИЙ ЗАПУСК (показую всі типи повідомлень):**", message_thread_id=THREAD_ID)
        m1 = bot.send_message(CHAT_ID, msg_start, message_thread_id=THREAD_ID, parse_mode='Markdown')
        bot.pin_chat_message(CHAT_ID, m1.message_id)
        bot.send_message(CHAT_ID, msg_report, message_thread_id=THREAD_ID, parse_mode='Markdown')
        bot.send_message(CHAT_ID, msg_remind, message_thread_id=THREAD_ID)
    else:
        # Автоматичний режим по датах
        if day == 1 and hour == 9:
            m = bot.send_message(CHAT_ID, msg_start, message_thread_id=THREAD_ID, parse_mode='Markdown')
            try: bot.pin_chat_message(CHAT_ID, m.message_id)
            except: pass
        elif day == 11 and hour == 12:
            bot.send_message(CHAT_ID, msg_report, message_thread_id=THREAD_ID, parse_mode='Markdown')
        elif day == 19 and hour == 12:
            if unpaid:
                bot.send_message(CHAT_ID, msg_remind, message_thread_id=THREAD_ID)

    # Щодня о 23:00 - знімаємо закріп в кінці місяця
    if day >= 28 and hour == 23:
        try: bot.unpin_all_chat_messages(CHAT_ID)
        except: pass

if __name__ == "__main__":
    run_logic()

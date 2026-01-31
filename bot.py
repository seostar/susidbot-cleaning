import os
import json
import re
from datetime import datetime
import telebot
import pytz

# Налаштування
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

# Список активних квартир
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
    return {}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_messages():
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    curr_key = now_dt.strftime('%m-%Y')
    
    if curr_key not in history: history[curr_key] = []

    # Отримуємо повідомлення
    updates = bot.get_updates(limit=100, timeout=10)
    
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            # Перевірка на thread_id або General гілку
            u_thread = str(u.message.message_thread_id) if u.message.message_thread_id else "None"
            if u_thread == str(THREAD_ID) or THREAD_ID is None:
                text = u.message.text.lower() if u.message.text else ""
                match = re.search(r'(\d+)', text)
                
                if match:
                    num = str(match.group(1))
                    keywords = ['оплат', 'сплач', 'ок', 'готово', 'є', '+']
                    if any(k in text for k in keywords) and int(num) in ACTIVE_APARTMENTS:
                        if num not in history[curr_key]:
                            history[curr_key].append(num)
    
    save_history(history)
    return history[curr_key]

def run_logic():
    now = datetime.now(TIMEZONE)
    day = now.day
    hour = now.hour
    paid = scan_messages()
    unpaid = [str(a) for a in ACTIVE_APARTMENTS if str(a) not in paid]
    month_name = get_month_ukr(now.month)

    # Перевірка на ручний запуск
    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    send_text = ""

    # 1 ЧИСЛО - 09:00
    if day == 1 and hour == 9:
        send_text = (f"🌿 Почався {month_name} — дякуємо за підтримку чистоти 💚\n\n"
                     f"💳 **5168 7451 4881 9912**\n💰 170 грн/міс\n"
                     f"✅ Після оплати: «кв. [номер] – оплачено»")
    
    # 11 ЧИСЛО - 12:00 або Ручний запуск
    elif (day == 11 and hour == 12) or is_manual:
        send_text = f"📊 **Звіт по оплатах ({month_name}):**\n\n✅ Оплатили: "
        send_text += (", ".join(paid) if paid else "поки що ніхто")
        if unpaid:
            send_text += f"\n\n⏳ Очікуємо: {', '.join(unpaid)}"

    # 19 ЧИСЛО - 12:00
    elif day == 19 and hour == 12:
        if unpaid:
            send_text = f"✨ Нагадуємо про оплату прибирання! Кв: {', '.join(unpaid)} 💚"

    if send_text:
        msg = bot.send_message(CHAT_ID, send_text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        if day == 1 and not is_manual:
            try: bot.pin_chat_message(CHAT_ID, msg.message_id)
            except: pass

    # Анпін 28 числа о 23:00
    if day >= 28 and hour == 23:
        try: bot.unpin_all_chat_messages(CHAT_ID)
        except: pass

if __name__ == "__main__":
    run_logic()

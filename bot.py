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

# Активні квартири
ACTIVE_APARTMENTS = [6, 7, 11, 14, 17, 18, 19, 20, 22, 23, 26, 33, 34, 36, 39, 42, 43, 44, 46]

bot = telebot.TeleBot(TOKEN)

def get_month_ukr(month_idx):
    months = {
        1: "січень", 2: "лютий", 3: "березень", 4: "квітень", 5: "травень", 6: "червень",
        7: "липень", 8: "серпень", 9: "вересень", 10: "жовтень", 11: "листопад", 12: "грудень"
    }
    return months[month_idx]

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

    # Читаємо останні повідомлення
    updates = bot.get_updates(limit=100)
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            if str(u.message.message_thread_id) == str(THREAD_ID):
                text = u.message.text.lower() if u.message.text else ""
                match = re.search(r'(\d+)', text)
                
                if match and any(word in text for word in ['оплат', 'сплачено', 'ок', 'готово']):
                    num = str(match.group(1))
                    if int(num) in ACTIVE_APARTMENTS and num not in history[curr_key]:
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

    # 1 ЧИСЛО - 09:00 - Вітання
    if day == 1 and hour == 9:
        text = (f"🌿 Почався {month_name} — дякуємо, що підтримуєте чистоту 💚\n\n"
                f"💳 **5168 7451 4881 9912**\n💰 170 грн/міс (до 10 числа)\n"
                f"📝 Призначення: «прибирання, кв. [номер]»\n\n"
                f"✅ Після оплати напишіть: «кв. [номер] – оплачено»")
        msg = bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        try: bot.pin_chat_message(CHAT_ID, msg.message_id)
        except: pass

    # 11 ЧИСЛО - 12:00 - Звіт
    elif day == 11 and hour == 12:
        text = f"📊 **Звіт по оплатах за {month_name}:**\n\n"
        text += "✅ Оплатили: " + (", ".join(paid) if paid else "поки що ніхто")
        if unpaid:
            text += f"\n\n⏳ Ще чекаємо на підтвердження від: {', '.join(unpaid)}"
        bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 19 ЧИСЛО - 12:00 - Нагадування
    elif day == 19 and hour == 12:
        if unpaid:
            text = (f"✨ Нагадуємо про оплату чистоти у нашому домі!\n\n"
                    f"Будемо вдячні за внесок від кв: {', '.join(unpaid)} 💚\n"
                    f"Це допомагає підтримувати наш під'їзд у гарному стані.")
            bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID)

    # Останній день місяця 23:00 - Зняти закріп
    if day >= 28 and hour == 23:
        try: bot.unpin_all_chat_messages(CHAT_ID)
        except: pass

if __name__ == "__main__":
    run_logic()

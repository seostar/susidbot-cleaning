import os
import json
import re
from datetime import datetime, timedelta
import telebot
import pytz

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

bot = telebot.TeleBot(TOKEN)

def load_config():
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

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
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    curr_key = now_dt.strftime('%m-%Y')
    next_dt = (now_dt.replace(day=28) + timedelta(days=5))
    next_key = next_dt.strftime('%m-%Y')

    if curr_key not in history: history[curr_key] = []
    if next_key not in history: history[next_key] = []

    updates = bot.get_updates(limit=100, timeout=10)
    active_apps = config['active_apartments']
    
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            text = u.message.text.lower() if u.message.text else ""
            numbers = re.findall(r'(\d+)', text)
            
            # Словник підтверджень (укр + рос)
            confirm_words = [
                'оплат', 'сплач', 'готово', 'є', 'ок', '+', '✅', 
                'перевела', 'скинула', 'оплатила', 'оплатил', 'заплатили', 'перевел'
            ]
            # Маркери наперед (укр + рос)
            advance_indicators = [
                'наперед', 'вперед', '2 місяці', '2 месяца', 'за два', 'наступний',
                'січень', 'январь', 'лютий', 'февраль', 'березень', 'март', 
                'квітень', 'апрель', 'травень', 'май', 'червень', 'июнь'
            ]
            
            if any(kw in text for kw in confirm_words) or any(ai in text for ai in advance_indicators):
                for num in numbers:
                    if int(num) in active_apps:
                        if num not in history[curr_key]:
                            history[curr_key].append(num)
                        if any(ai in text for ai in advance_indicators):
                            if num not in history[next_key]:
                                history[next_key].append(num)
    
    save_history(history)
    return history[curr_key]

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    
    paid = scan_messages()
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    month_name = get_month_ukr(now.month)
    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

    # --- 1 ЧИСЛО: Реквізити ---
    if (day == 1 and hour == 9) or is_manual:
        template = config['templates'][now.month - 1]
        msg_text = template.format(
            month_name=month_name, 
            neighbors_list=", ".join(active_list),
            card=config['card_details'], 
            amount=config['monthly_fee']
        )
        msg = bot.send_message(CHAT_ID, msg_text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        try: bot.pin_chat_message(CHAT_ID, msg.message_id)
        except: pass

    # --- 11 ЧИСЛО: Звіт ---
    if (day == 11 and hour == 12) or (is_manual and day != 1):
        report = (f"📊 **Звіт по внесках за {month_name}:**\n\n"
                  f"Дякуємо всім, хто підтримує чисте середовище! ✨\n\n"
                  f"✅ **Внесок зробили:** {', '.join(sorted(paid, key=int)) if paid else 'поки ніхто'}\n"
                  f"⏳ **Ще очікуємо від:** {', '.join(unpaid) if unpaid else 'всіх добросусідів!'}\n\n"
                  f"*Якщо ви оплатили, але вас немає в списку — просто напишіть номер квартири та «оплачено»*.")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # --- 19 ЧИСЛО: Нагадування (До совісті) ---
    if (day == 19 and hour == 12) or (is_manual and day != 1 and day != 11):
        if unpaid:
            remind_text = (f"📢 **Сусіди, маленьке нагадування!**\n\n"
                           f"Ми все ще очікуємо внески за {month_name} від кв: {', '.join(unpaid)}.\n\n"
                           f"Чи можемо ми на вас розрахувати? Якщо ні — будь ласка, повідомте. "
                           f"Від кількості учасників залежить розмір внеску для кожного, і нам важливо розуміти, чи не доведеться його збільшувати наступного місяця.\n\n"
                           f"💳 `{config['card_details']}` | Внесок: {config['monthly_fee']} грн")
            bot.send_message(CHAT_ID, remind_text, message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

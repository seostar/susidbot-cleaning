import os
import json
import re
import random
import telebot
import pytz
from datetime import datetime, timedelta

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
    return {"01-2026": [], "02-2026": []}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_messages():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    
    curr_key = now_dt.strftime('%m-%Y')
    next_month_dt = (now_dt.replace(day=28) + timedelta(days=5))
    next_key = next_month_dt.strftime('%m-%Y')
    
    if curr_key not in history: history[curr_key] = []
    if next_key not in history: history[next_key] = []

    # Отримуємо повідомлення (за останні 24 години)
    updates = bot.get_updates(limit=100, timeout=10)
    active_apps = [int(a) for a in config['active_apartments']]
    
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            text = u.message.text.lower() if u.message.text else ""
            numbers = re.findall(r'(\d+)', text)
            
            # Маркери оплати
            confirm_words = ['оплат', 'сплач', 'готово', 'є', 'есть', 'ок', '+', '✅', 'перев', 'скинув', 'скинул', 'оплатил']
            # Маркери майбутнього часу (лютий, наперед тощо)
            advance_words = ['наперед', '2 міс', '2 мес', 'два міс', 'два мес', 'наступн', 'лютий', 'февраль', 'лютого', 'февраля']

            if any(kw in text for kw in confirm_words):
                for num in numbers:
                    val = int(num)
                    if val in active_apps:
                        str_num = str(val)
                        # Якщо оплата за 2 місяці
                        if any(aw in text for aw in advance_words):
                            if str_num not in history[curr_key]: history[curr_key].append(str_num)
                            if str_num not in history[next_key]: history[next_key].append(str_num)
                        else:
                            # Звичайна оплата за поточний місяць
                            if str_num not in history[curr_key]:
                                history[curr_key].append(str_num)
    
    save_history(history)
    return history[curr_key]

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    
    # Завжди скануємо і оновлюємо історію
    paid = scan_messages()
    
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    month_name = get_month_ukr(now.month)

    # 1 ЧИСЛО: Реквізити (9:00)
    if day == 1 and hour == 9:
        template = config['templates'][now.month - 1]
        msg_text = template.format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee'])
        bot.send_message(CHAT_ID, msg_text, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 11 ЧИСЛО: Звіт (12:00)
    if day == 11 and hour == 12:
        tpl = random.choice(config['report_templates'])
        report = tpl.format(month_name=month_name, paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 19 ЧИСЛО: Нагадування (12:00)
    if day == 1

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

# Словник коренів місяців для розпізнавання (UA/RU)
MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май', 'мая'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

def load_config():
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_history():
    if os.path.exists('history.json'):
        with open('history.json', 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
            except: return {}
    return {}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_messages():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    curr_month_key = now_dt.strftime('%m-%Y')
    
    updates = bot.get_updates(limit=100, timeout=10)
    active_apps = [int(a) for a in config['active_apartments']]
    
    confirm_words = ['оплат', 'сплач', 'готово', 'є', 'есть', 'ок', '+', '✅', 'перев', 'скину', 'оплатил', 'оплатила']
    advance_words = ['наперед', '2 міс', '2 мес', 'два міс', 'два мес', 'наступн']

    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            text = u.message.text.lower() if u.message.text else ""
            numbers = re.findall(r'(\d+)', text)
            
            if any(kw in text for kw in confirm_words):
                for num in numbers:
                    val = int(num)
                    if val in active_apps:
                        str_num = str(val)
                        found_month = False
                        for m_idx, roots in MONTHS_MAP.items():
                            if any(root in text for root in roots):
                                target_year = now_dt.year
                                if m_idx < now_dt.month and now_dt.month > 10: target_year += 1
                                target_key = f"{m_idx:02d}-{target_year}"
                                if target_key not in history: history[target_key] = []
                                if str_num not in history[target_key]: history[target_key].append(str_num)
                                if target_key != curr_month_key:
                                    if curr_month_key not in history: history[curr_month_key] = []
                                    if str_num not in history[curr_month_key]: history[curr_month_key].append(str_num)
                                found_month = True

                        if not found_month and any(aw in text for aw in advance_words):
                            next_dt = (now_dt.replace(day=28) + timedelta(days=5))
                            next_key = next_dt.strftime('%m-%Y')
                            for k in [curr_month_key, next_key]:
                                if k not in history: history[k] = []
                                if str_num not in history[k]: history[k].append(str_num)
                            found_month = True

                        if not found_month:
                            if curr_month_key not in history: history[curr_month_key] = []
                            if str_num not in history[curr_month_key]: history[curr_month_key].append(str_num)
    
    save_history(history)
    return history.get(curr_month_key, [])

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    paid = scan_messages()
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    month_name = ukr_months.get(now.month)

    # Тестове повідомлення для сьогодні (31-ше число)
    if day == 31:
        bot.send_message(CHAT_ID, f"✅ Тест успішний! Оплатили сьогодні: {', '.join(paid) if paid else 'нікого'}", message_thread_id=THREAD_ID)

    if day == 1 and hour == 9:
        template = config['templates'][now.month - 1]
        msg = template.format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee'])
        bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')

    if day == 11 and hour == 12:
        tpl = random.choice(config['report_templates'])
        report = tpl.format(month_name=month_name, paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

    if day == 19 and hour == 12:
        if unpaid:
            tpl = random.choice(config['reminder_templates'])
            remind = tpl.format(month_name=month_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, remind, message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

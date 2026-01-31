import os
import json
import re
import random
from datetime import datetime, timedelta
import telebot
import pytz

# Налаштування
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

bot = telebot.TeleBot(TOKEN)

def load_config():
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_history():
    if os.path.exists('history.json'):
        with open('history.json', 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def get_target_months(text, now_dt):
    months_keys = []
    curr_m = now_dt.strftime('%m-%Y')
    next_dt = (now_dt.replace(day=28) + timedelta(days=5))
    next_m = next_dt.strftime('%m-%Y')
    
    # Словник для розпізнавання
    mapping = {
        curr_m: ['січ', 'янв', 'поточ'],
        next_m: ['лют', 'фев', 'наступ', 'наперед', 'чіч']
    }

    found = False
    for key, keywords in mapping.items():
        if any(kw in text for kw in keywords):
            months_keys.append(key)
            found = True
    
    if re.search(r'за\s*(2|дв[аі])\s*м', text):
        months_keys.extend([curr_m, next_m])
        found = True

    if not found:
        months_keys.append(curr_m)
        
    return list(set(months_keys))

def scan_messages():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    
    # Беремо останні 100 повідомлень
    updates = bot.get_updates(limit=100, offset=-50) 
    active_apps = [str(a) for a in config['active_apartments']]
    triggers = ['+', '✅', 'ок', 'готово', 'сплач', 'оплат', 'скинув', 'є', 'есть', 'зарахув']

    for u in updates:
        msg = u.message or u.edited_message
        if not msg or str(msg.chat.id) != str(CHAT_ID):
            continue
        
        text = msg.text.lower() if msg.text else ""
        
        # Шукаємо цифри, що відповідають номерам квартир
        found_apts = [n for n in re.findall(r'\b\d{1,3}\b', text) if n in active_apps]
        
        if found_apts and (any(t in text for t in triggers) or "за" in text):
            target_months = get_target_months(text, now_dt)
            for m_key in target_months:
                if m_key not in history: history[m_key] = []
                for apt in found_apts:
                    if apt not in history[m_key]:
                        history[m_key].append(apt)
                        print(f"Знайдено: {apt} за {m_key}")
    
    save_history(history)
    return history.get(now_dt.strftime('%m-%Y'), [])

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    
    paid = scan_messages()
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    ukr_months = ["січень", "лютий", "березень", "квітень", "травень", "червень", 
                  "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
    month_name = ukr_months[now.month - 1]

    # ВІДПРАВКА (БЕЗ УМОВ ДАТИ - ДЛЯ ПЕРЕВІРКИ)
    # Збір
    tpl_start = config['templates'][now.month - 1]
    bot.send_message(CHAT_ID, tpl_start.format(
        month_name=month_name, neighbors_list=", ".join(active_list), 
        card=config['card_details'], amount=config['monthly_fee']
    ), message_thread_id=THREAD_ID, parse_mode='Markdown')

    # Звіт
    tpl_report = random.choice(config['report_templates'])
    bot.send_message(CHAT_ID, tpl_report.format(
        month_name=month_name, 
        paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого", 
        unpaid_list=", ".join(unpaid) if unpaid else "всіх!"
    ), message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

import os
import json
import re
import random
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
    
    mapping = {
        curr_m: ['січ', 'янв', 'поточ'],
        next_m: ['лют', 'фев', 'наступ', 'наперед', 'чіч']
    }

    found = False
    for key, keywords in mapping.items():
        if any(kw in text for kw in keywords):
            months_keys.append(key)
            found = True
    
    if re.search(r'за\s*(2|дв[аі])\s*м', text) or (curr_m in months_keys and any(kw in text for kw in mapping[next_m])):
        months_keys.extend([curr_m, next_m])
        found = True

    if not months_keys:
        months_keys.append(curr_m)
        
    return list(set(months_keys))

def scan_messages():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    
    # Використовуємо offset=-100 для глибокого сканування
    updates = bot.get_updates(limit=100, offset=-50) 
    active_apps = [str(a) for a in config['active_apartments']]
    triggers = ['+', '✅', 'ок', 'готово', 'сплач', 'оплат', 'скинув', 'є', 'есть', 'зарахув']

    for u in updates:
        msg = u.message or u.edited_message
        if not msg or str(msg.chat.id) != str(CHAT_ID):
            continue
        
        text = msg.text.lower() if msg.text else ""
        found_apts = [n for n in re.findall(r'\b\d{1,3}\b', text) if n in active_apps]
        
        if found_apts and (any(t in text for t in triggers) or "за" in text):
            target_months = get_target_months(text, now_dt)
            for m_key in target_months:
                if m_key not in history: history[m_key] = []
                for apt in found_apts:
                    if apt not in history[m_key]:
                        history[m_key].append(apt)
    
    save_history(history)
    return history.get(now_dt.strftime('%m-%Y'), [])

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    
    paid = scan_messages()
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    ukr_months = ["січень", "лютий", "березень", "квітень", "травень", "червень", 
                  "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
    month_name = ukr_months[now.month - 1]
    
    # Перевірка чи запуск ручний (кнопкою)
    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

    # 1 число: Збір (09:00)
    if (day == 1 and hour == 9) or is_manual:
        tpl = config['templates'][now.month - 1]
        msg = bot.send_message(CHAT_ID, tpl.format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee']), message_thread_id=THREAD_ID, parse_mode='Markdown')
        try: bot.pin_chat_message(CHAT_ID, msg.message_id)
        except: pass

    # 11 число: Звіт (12:00)
    if (day == 11 and hour == 12) or is_manual:
        tpl = random.choice(config['report_templates'])
        report = tpl.format(month_name=month_name, paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 19 число: Нагадування (12:00)
    if (day == 19 and hour == 12) or is_manual:
        if unpaid:
            tpl = random.choice(config['reminder_templates'])
            remind = tpl.format(month_name=month_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, remind, message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

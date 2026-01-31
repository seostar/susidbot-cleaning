import os
import json
import re
import random
from datetime import datetime, timedelta
import telebot
import pytz

# Ініціалізація
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

bot = telebot.TeleBot(TOKEN)

# Словник для розпізнавання місяців (UA/RU + специфіка)
MONTHS_MAP = {
    1: ['січ', 'янв'],
    2: ['лют', 'фев', 'чіч'],
    3: ['берез', 'март'],
    4: ['квіт', 'апр'],
    5: ['трав', 'май', 'мая'],
    6: ['черв', 'июн'],
    7: ['лип', 'июл'],
    8: ['серп', 'авг'],
    9: ['верес', 'сент'],
    10: ['жовт', 'окт'],
    11: ['листоп', 'нояб'],
    12: ['груд', 'дек']
}

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
    found_months = []
    text_lower = text.lower()
    
    # Спеціальний випадок: за 2 місяці
    if re.search(r'за\s*2', text_lower) or re.search(r'дв[аі]\s*м', text_lower):
        m1 = now_dt.strftime('%m-%Y')
        m2 = (now_dt.replace(day=28) + timedelta(days=5)).strftime('%m-%Y')
        return [m1, m2]

    # Пошук по назвах місяців
    for m_num, keywords in MONTHS_MAP.items():
        if any(kw in text_lower for kw in keywords):
            year = now_dt.year
            # Корекція року (якщо в грудні платять за січень)
            if m_num < now_dt.month and now_dt.month >= 11: year += 1
            # Корекція року (якщо в січні платять за грудень минулого року)
            if m_num > now_dt.month and now_dt.month <= 2 and m_num == 12: year -= 1
            found_months.append(f"{m_num:02d}-{year}")

    if not found_months:
        found_months.append(now_dt.strftime('%m-%Y'))
    return list(set(found_months))

def scan_messages():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    
    # Беремо останні 100 повідомлень
    updates = bot.get_updates(limit=100, offset=-50, timeout=5) 
    active_apps = [str(a) for a in config['active_apartments']]
    triggers = ['+', '✅', 'ок', 'готово', 'сплач', 'оплат', 'скинув', 'є', 'есть', 'оплатил', 'зарахув']

    for u in updates:
        msg = u.message or u.edited_message
        if not msg or str(msg.chat.id) != str(CHAT_ID): continue
        
        # Фільтр по даті: ігноруємо старіше 3 днів (для надійності)
        msg_ts = datetime.fromtimestamp(msg.date, pytz.utc).astimezone(TIMEZONE)
        if (now_dt - msg_ts).days > 3: continue
            
        text = msg.text.lower() if msg.text else ""
        found_apts = [n for n in re.findall(r'\b\d{1,3}\b', text) if n in active_apps]
        
        if found_apts and any(t in text for t in triggers):
            targets = get_target_months(text, msg_ts)
            for m_key in targets:
                if m_key not in history: history[m_key] = []
                for apt in found_apts:
                    if apt not in history[m_key]: history[m_key].append(apt)
    
    save_history(history)
    return history.get(now_dt.strftime('%m-%Y'), [])

def run_logic():
    config = load_config()
    now = datetime.now(TIMEZONE)
    day, hour = now.day, now.hour
    
    paid = scan_messages()
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    month_names_ukr = ["січень", "лютий", "березень", "квітень", "травень", "червень", 
                      "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
    month_name = month_names_ukr[now.month - 1]
    
    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'

    # 1. Збір (1 число 09:00)
    if (day == 1 and hour == 9) or is_manual:
        tpl = config['templates'][now.month - 1]
        text = tpl.format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee'])
        msg = bot.send_message(CHAT_ID, text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        try: bot.pin_chat_message(CHAT_ID, msg.message_id)
        except: pass

    # 2. Звіт (11 число 12:00)
    if (day == 11 and hour == 12) or is_manual:
        tpl = random.choice(config['report_templates'])
        report = tpl.format(month_name=month_name, paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 3. Нагадування (19 число 12:00)
    if (day == 19 and hour == 12) or is_manual:
        if unpaid:
            tpl = random.choice(config['reminder_templates'])
            remind = tpl.format(month_name=month_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, remind, message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

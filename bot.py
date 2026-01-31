import os
import json
import re
import random
import telebot
import pytz
from datetime import datetime

# Налаштування
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID') 
TIMEZONE = pytz.timezone('Europe/Kyiv')

bot = telebot.TeleBot(TOKEN)

# Словник для розпізнавання місяців
MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

def load_config():
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_history():
    if os.path.exists('history.json'):
        try:
            with open('history.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_messages_and_update_history():
    config = load_config()
    history = load_history()
    now_dt = datetime.now(TIMEZONE)
    curr_month_key = now_dt.strftime('%m-%Y')
    
    updates = bot.get_updates(limit=100, timeout=10)
    active_apps = [str(a) for a in config['active_apartments']]
    confirm_words = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'перев', 'скину']
    
    for u in updates:
        if u.message and str(u.message.chat.id) == str(CHAT_ID):
            text = u.message.text.lower() if u.message.text else ""
            numbers = re.findall(r'(\d+)', text)
            
            if any(kw in text for kw in confirm_words) or "+" in text:
                for num in numbers:
                    if num in active_apps:
                        # Визначаємо місяць (поточний або вказаний)
                        target_key = curr_month_key
                        for m_idx, roots in MONTHS_MAP.items():
                            if any(root in text for root in roots):
                                target_key = f"{m_idx:02d}-{now_dt.year}"
                        
                        if target_key not in history: history[target_key] = []
                        if num not in history[target_key]:
                            history[target_key].append(num)
    
    save_history(history)
    return history

def run_logic():
    # 1. Спершу бот завжди сканує чат і оновлює історію
    history = scan_messages_and_update_history()
    config = load_config()
    now = datetime.now(TIMEZONE)
    
    # Підготовка даних для текстів
    curr_month_key = now.strftime('%m-%Y')
    paid_this_month = history.get(curr_month_key, [])
    active_list = sorted([str(a) for a in config['active_apartments']], key=int)
    unpaid = [a for a in active_list if a not in paid_this_month]
    
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    month_name = ukr_months.get(now.month)

    # 2. ПЕРЕВІРКА: Якщо запуск ручний (кнопка Run Workflow) — видаємо всі 3 типи
    if os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        # Повідомлення 1
        msg1 = config['templates'][now.month - 1].format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee'])
        bot.send_message(CHAT_ID, msg1, message_thread_id=THREAD_ID, parse_mode='Markdown')
        
        # Повідомлення 2
        msg2 = random.choice(config['report_templates']).format(month_name=month_name, paid_list=", ".join(sorted(paid_this_month, key=int)) if paid_this_month else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, msg2, message_thread_id=THREAD_ID, parse_mode='Markdown')
        
        # Повідомлення 3
        if unpaid:
            msg3 = random.choice(config['reminder_templates']).format(month_name=month_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, msg3, message_thread_id=THREAD_ID, parse_mode='Markdown')
        return

    # 3. РОБОТА ЗА РОЗКЛАДОМ (CRON)
    day, hour = now.day, now.hour
    if day == 1 and hour == 9:
        msg = config['templates'][now.month - 1].format(month_name=month_name, neighbors_list=", ".join(active_list), card=config['card_details'], amount=config['monthly_fee'])
        bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')
    elif day == 11 and hour == 12:
        report = random.choice(config['report_templates']).format(month_name=month_name, paid_list=", ".join(sorted(paid_this_month, key=int)) if paid_this_month else "нікого", unpaid_list=", ".join(unpaid) if unpaid else "всіх!")
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')
    elif day == 19 and hour == 12:
        if unpaid:
            remind = random.choice(config['reminder_templates']).format(month_name=month_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, remind, message_thread_id=THREAD_ID, parse_mode='Markdown')

if __name__ == "__main__":
    run_logic()

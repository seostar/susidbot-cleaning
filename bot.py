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

# Словник коренів для розпізнавання місяців (UA/RU)
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
                        
                        # Перевірка на конкретний місяць
                        for m_idx, roots in MONTHS_MAP.items():

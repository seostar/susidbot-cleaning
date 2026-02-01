import os
import json
import re
import random
import telebot
import pytz
from datetime import datetime

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
TIMEZONE = pytz.timezone('Europe/Kyiv')

try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') and os.getenv('THREAD_ID').strip() else None
except:
    print("❌ Помилка конфігурації ID")
    exit(1)

bot = telebot.TeleBot(TOKEN)

MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
            except: return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        # Сортуємо номери для краси
        for k in data:
            if isinstance(data[k], list):
                data[k] = sorted(list(set(str(x) for x in data[k])), key=int)
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_period(now):
    m = now.month if now.day < 25 else (now.month % 12) + 1
    y = now.year if not (now.month == 12 and m == 1) else now.year + 1
    return m, y

def scan(config, history, now):
    active = [str(a) for a in config.get('active_apartments', [])]
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID: continue
            text = (u.message.text or "").lower()
            m_app = re.search(r'\d+', text)
            if m_app:
                app = m_app.group()
                if app in active:
                    found = []
                    for idx, roots in MONTHS_MAP.items():
                        if any(r in text for r in roots): found.append(idx)
                    
                    if not found:
                        multi = re.search(r'(\d+)\s*(міс|мес)', text.replace(app, "", 1))
                        if multi:
                            start_m, _ = get_period(now)
                            for i in range(int(multi.group(1))):
                                found.append(((start_m + i - 1) % 12) + 1)
                    
                    target = found if found else [get_period(now)[0]]
                    for m_idx in set(target):
                        _, year = get_period(now)
                        if m_idx < now.month and now.month >= 11: year += 1
                        key = f"{m_idx:02d}-{year}"
                        if key not in history: history[key] = []
                        if str(app) not in history[key]:
                            history[key].append(str(app))
    except Exception as e: print(f"Scan error: {e}")
    return history

def send(config, history, m_idx, year):
    names = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
             7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    key = f"{m_idx:02d}-{year}"
    paid = sorted(history.get(key, []), key=int)
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active if a not in paid]
    
    sig = "\n\n_🤖 beta: перевіряйте запис._"
    try:
        # Реквізити
        tpl = config['templates'][m_idx

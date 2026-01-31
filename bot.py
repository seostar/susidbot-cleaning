import os, json, re, random, telebot, pytz
from datetime import datetime

# Налаштування змінних середовища
TOKEN = os.getenv('TELEGRAM_TOKEN')
try:
    # Обов'язково перетворюємо на числа для API Telegram
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') else None
except ValueError as e:
    print(f"ERROR: Неправильний формат CHAT_ID або THREAD_ID. Мають бути лише цифри: {e}")
    CHAT_ID = None
    THREAD_ID = None

TIMEZONE = pytz.timezone('Europe/Kyiv')
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
            try: return json.load(f)
            except: return {}
    return {}

def save_history(history):
    with open('history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def scan_and_update():
    config = load_json('config.json')
    history = load_json('history.json')
    now = datetime.now(TIMEZONE)
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    
    print(f"DEBUG: Починаю сканування повідомлень для чату {CHAT_ID}...")
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        confirm_keywords = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'переказ', 'скинув', 'скинула', 'за']

        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID: continue
            
            text = u.message.text.lower() if u.message.text else ""
            match = re.search(r'\d+', text)
            if not match: continue
            
            app_num = match.group()
            if app_num in active_apps and (any(kw in text for kw in confirm_keywords) or "+" in text):
                target_months = []
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots):
                        target_months.append(m_idx)
                
                if not target_months:
                    target_months = [now.month if now.day < 25 else (now.month % 12) + 1]
                
                for m_idx in set(target_months):
                    year = now.year
                    if m_idx < now.month and now.month >= 11: year += 1
                    key = f"{m_idx:02d}-{year}"
                    if key not in history: history[key] = []
                    if app_num not in history[key]:
                        history[key].append(app_num)
                        print(f"DEBUG: Знайдено оплату: кв. {app_num} за {key}")
    except Exception as e:
        print(f"SCAN ERROR: {e}")
    
    save_history(history)
    return history

def send_all_messages(config, history, month_idx, year):
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    
    m_name = ukr_months[month_idx]
    curr_key = f"{month_idx:02d}-{year}"
    paid = sorted(list(set(history.get(curr_key, []))), key=int)

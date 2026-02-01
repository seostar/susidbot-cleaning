import os
import json
import re
import random
import telebot
import pytz
from datetime import datetime

# --- КОНФІГУРАЦІЯ ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
TIMEZONE = pytz.timezone('Europe/Kyiv')

# Чисто для діагностики в логах GitHub
EVENT = os.getenv('GITHUB_EVENT_NAME', 'manual')
print(f"🚀 Запуск! Подія: {EVENT}")

try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    t_id = os.getenv('THREAD_ID')
    THREAD_ID = int(t_id) if t_id and t_id.strip() else None
    print(f"✅ Конфіг завантажено: CHAT_ID={CHAT_ID}, THREAD_ID={THREAD_ID}")
except Exception as e:
    print(f"❌ Помилка секретів: {e}")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Карта місяців для пошуку в тексті
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

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_target_period(now):
    # Якщо після 25-го числа, збираємо вже на наступний місяць
    m = now.month if now.day < 25 else (now.month % 12) + 1
    y = now.year if not (now.month == 12 and m == 1) else now.year + 1
    return m, y

def scan_payments(config, history, now):
    active_apps = [str(a).strip() for a in config.get('active_apartments', [])]
    print(f"🔍 Сканую останні повідомлення для квартир: {active_apps}")
    try:
        updates = bot.get_updates(limit=50, timeout=5)
        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID:
                continue
            text = (u.message.text or "").lower()
            match_app = re.search(r'\b\d+\b', text)
            if match_app:
                app_num = match_app.group()
                if app_num in active_apps:
                    # Визначаємо за який місяць оплата
                    found_months = []
                    for m_idx, roots in MONTHS_MAP.items():
                        if any(root in text for root in roots):
                            found_months.append(m_idx)
                    
                    target_months = found_months if found_months else [get_target_period(now)[0]]
                    for m_idx in set(target_months):
                        _, year = get_target_period(now)
                        key = f"{m_idx:02d}-{year}"
                        if key not in history: history[key] = []
                        if app_num not in history[key]:
                            history[key].append(app_num)
                            print(f"💳 Знайдено оплату: кв. {app_num} за {key}")
    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")
    return history

def send_reports(config, history, month_idx, year):
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    m_name = ukr_months[month_idx]
    key = f"{month_idx:02d}-{year}"
    
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    paid = sorted(list(set(history.get(key, []))), key=int)
    unpaid = [a for a in active if a not in paid]
    
    sig = "\n\n_beta: можу помилятись, перевіряйте._"

    print(f"📤 Відправка звітів за {m_name}...")
    
    # 1. Реквізити
    text_tpl = config['templates'][month_idx-1].format(
        month_name=m_name, neighbors_list=", ".join(active), 
        card=config['card_details'], amount=config['monthly_fee'])
    
    msg = bot.send_message(CHAT_ID, text_tpl + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')
    print("✅ Повідомлення з реквізитами відправлено")
    
    try:
        bot.unpin_all_chat_messages(CHAT_ID)
        bot.pin_chat_message(CHAT_ID, msg.message_id)
    except: pass

    # 2. Звіт
    report = random.choice(config['report_templates']).format(
        month_name=m_name, 
        paid_list=", ".join(paid) if paid else "поки ніхто", 
        unpaid_list=", ".join(unpaid) if unpaid else

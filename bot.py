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

try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') and os.getenv('THREAD_ID').strip() else None
except (ValueError, TypeError):
    print("❌ Помилка в CHAT_ID або THREAD_ID")
    exit(1)

bot = telebot.TeleBot(TOKEN)

MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

# --- ДОПОМІЖНІ ФУНКЦІЇ ---

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
    m = now.month if now.day < 25 else (now.month % 12) + 1
    y = now.year if not (now.month == 12 and m == 1) else now.year + 1
    return m, y

# --- ОСНОВНА ЛОГІКА СКАНУВАННЯ ---

def scan_payments(config, history, now):
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    
    print("🔍 Починаю сканування чату...")
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID:
                continue
            
            text = (u.message.text or "").lower()
            match_app = re.search(r'\d+', text)
            
            if match_app:
                app_num = match_app.group()
                if app_num in active_apps:
                    found_months = []
                    
                    # Шукаємо назви місяців
                    for m_idx, roots in MONTHS_MAP.items():
                        if any(root in text for root in roots):
                            found_months.append(m_idx)
                    
                    # Обробка "за X міс"
                    if not found_months:
                        multi = re.search(r'(\d+)\s*(міс|мес)', text.replace(app_num, "", 1))
                        if multi:
                            count = int(multi.group(1))
                            start_m, _ = get_target_period(now)
                            for i in range(count):
                                found_months.append(((start_m + i - 1) % 12) + 1)
                    
                    # ПРАВИЛО: Якщо місяці не вказані, але є номер — це поточний місяць
                    target_months = found_months if found_months else [get_target_period(now)[0]]

                    for m_idx in set(target_months):
                        _, year = get_target_period(now)
                        if m_idx < now.month and now.month >= 11:
                            year += 1
                        
                        key = f"{m_idx:02d}-{year}"
                        
                        # Тільки додаємо, нічого не видаляємо
                        if key not in history: history[key] = []
                        if app_num not in history[key]:
                            history[key].append(app_num)
                            print(f"✅ Записано: кв. {app_num} за {key}")
                            
    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")
    return history

# --- ЛОГІКА ЗВІТІВ ---

def send_reports(config, history, month_idx, year):
    ukr_months = {
        1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
        7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"
    }
    m_name = ukr_months[month_idx]
    key = f"{month_idx:02d}-{year}"
    
    paid = sorted(list(set(history.get(key, []))), key=int)
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active if a not in paid]
    
    sig = "\n\n_🤖 beta: можу помилятись, перевіряйте._"

    try:
        # 1. Реквізити
        text_tpl = config['templates'][month_idx-1].format(
            month_name=m_name, neighbors_list=", ".join(active), 
            card=config['card_details'], amount=config['monthly_fee'])
        m = bot.send_message(CHAT_ID, text_tpl + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')
        
        try:
            bot.unpin_all_chat_messages(CHAT_ID)
            bot.pin_chat_message(CHAT_ID, m.message_id)
        except: pass

        # 2. Звіт
        report = random.choice(config['report_templates']).format(
            month_name=m_name, 
            paid_list=", ".join(paid) if paid else "поки ніхто", 
            unpaid_list=", ".join(unpaid) if unpaid else "всі! 🎉")
        bot.send_message(CHAT_ID, report + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')

        # 3. Нагадування
        if unpaid:
            remind = random.choice(config['reminder_templates']).format(
                month_name=m_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, remind + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')
            
    except Exception as e:
        print(f"⚠️ Помилка: {e}")

# --- ТОЧКА ВХОДУ ---

def run():
    now = datetime.now(TIMEZONE)
    config = load_json('config.json')
    history = load_json('history.json')

    updated_history = scan_payments(config, history, now)
    save_json('history.json', updated_history)

    m, y = get_target_period(now)
    
    is_manual = (os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    is_report_hour = now.hour in [9, 12]

    if is_manual or is_report_hour:
        send_reports(config, updated_history, m, y)

if __name__ == "__main__":
    run()

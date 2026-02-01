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
            try: return json.load(f)
            except: return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_billing_period(now):
    if now.day >= 25:
        if now.month == 12: return 1, now.year + 1
        return now.month + 1, now.year
    return now.month, now.year

def scan_chat(config, history, now):
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    triggers = ['опл', 'спла', 'скин', 'перек', '✅', '➕', 'плюс', 'грн', 'за']
    
    try:
        updates = bot.get_updates(limit=100, timeout=5)
        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID: continue
            
            text = (u.message.text or "").lower()
            found_apps = [w for w in re.findall(r'\d+', text) if w in active_apps]
            
            if found_apps and any(t in text for t in triggers):
                target_keys = []
                explicit_months = [m_idx for m_idx, roots in MONTHS_MAP.items() if any(r in text for r in roots)]
                multi_match = re.search(r'(\d+)\s*(міс|мес)', text)
                cur_m, cur_y = get_billing_period(now)

                if explicit_months:
                    for m in explicit_months:
                        y = cur_y
                        if now.month == 12 and m < 6: y += 1
                        target_keys.append(f"{m:02d}-{y}")
                elif multi_match:
                    count = int(multi_match.group(1))
                    for i in range(count):
                        m = ((cur_m + i - 1) % 12) + 1
                        y = cur_y + ((cur_m + i - 1) // 12)
                        target_keys.append(f"{m:02d}-{y}")
                else:
                    target_keys.append(f"{cur_m:02d}-{cur_y}")

                for key in set(target_keys):
                    if key not in history: history[key] = []
                    for app in set(found_apps):
                        if app not in history[key]:
                            history[key].append(app)
    except Exception as e:
        print(f"Помилка сканування: {e}")
    return history

def process_notifications(config, history, now, is_manual):
    target_m, target_y = get_billing_period(now)
    key = f"{target_m:02d}-{target_y}"
    
    paid = sorted(list(set(history.get(key, []))), key=lambda x: int(x))
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=lambda x: int(x))
    unpaid = [a for a in active if a not in paid]

    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    m_name = ukr_months[target_m]
    
    day = now.day

    # 1. ПРИВІТАННЯ (1 число або ТЕСТ)
    if day == 1 or is_manual:
        msg = config['templates'][target_m-1].format(
            month_name=m_name, neighbors_list=", ".join(active), 
            card=config['card_details'], amount=config['monthly_fee']
        )
        sent = bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')
        try:
            bot.unpin_all_chat_messages(CHAT_ID)
            bot.pin_chat_message(CHAT_ID, sent.message_id)
        except: pass

    # 2. ЗВІТ (11 число або ТЕСТ)
    if day == 11 or is_manual:
        tpl = random.choice(config['report_templates'])
        msg = tpl.format(month_name=m_name, paid_list=", ".join(paid) if paid else "—", 
                         unpaid_list=", ".join(unpaid) if unpaid else "всі молодці! 🎉")
        bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')

    # 3. НАГАДУВАННЯ (19 число або ТЕСТ)
    if day == 19 or is_manual:
        if unpaid:
            tpl = random.choice(config['reminder_templates'])
            msg = tpl.format(month_name=m_name, unpaid_list=", ".join(unpaid), card=config['card_details'])
            bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')

def run():
    now = datetime.now(TIMEZONE)
    is_manual = (os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    
    config = load_json('config.json')
    history = load_json('history.json')

    history = scan_chat(config, history, now)
    save_json('history.json', history)
    
    # ПРИБРАНО ОБМЕЖЕННЯ ГОДИН ДЛЯ ТЕСТУ
    process_notifications(config, history, now, is_manual)

if __name__ == "__main__":
    run()

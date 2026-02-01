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
except (ValueError, TypeError) as e:
    print(f"❌ Помилка в ID: {e}")
    exit(1)

bot = telebot.TeleBot(TOKEN)

MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

# --- JSON ---
def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_target_period(now):
    m = now.month if now.day < 25 else (now.month % 12) + 1
    y = now.year if not (now.month == 12 and m == 1) else now.year + 1
    return m, y

# --- СКАНУВАННЯ ---
def scan_payments(config, history, now):
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    confirm_keywords = [
        'оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅',
        'переказ', 'скинув', 'скинула', 'за', 'міс', 'мес', 'грн'
    ]

    meta = history.setdefault("_meta", {})
    last_update_id = meta.get("last_update_id", 0)

    target_month, target_year = get_target_period(now)

    print("🔍 Сканую нові повідомлення…")
    updates = bot.get_updates(offset=last_update_id + 1, limit=100, timeout=10)

    for u in updates:
        if not u.message or u.message.chat.id != CHAT_ID:
            continue

        text = (u.message.text or "").lower()
        match_app = re.search(r'\d+', text)
        if not match_app:
            continue

        app_num = match_app.group()
        if app_num not in active_apps:
            continue
        if not any(k in text for k in confirm_keywords):
            continue

        target_months = []

        # місяці текстом
        for m_idx, roots in MONTHS_MAP.items():
            if any(r in text for r in roots):
                target_months.append(m_idx)

        # "за X міс"
        multi = re.search(r'(\d+)\s*(міс|мес|місяц)', text)
        if multi:
            count = int(multi.group(1))
            for i in range(count):
                target_months.append(((target_month + i - 1) % 12) + 1)

        if not target_months:
            target_months = [target_month]

        for m_idx in set(target_months):
            year = target_year
            if m_idx < target_month:
                year += 1

            key = f"{m_idx:02d}-{year}"
            history.setdefault(key, [])

            if app_num not in history[key]:
                history[key].append(app_num)
                print(f"✅ Оплата: кв {app_num} → {key}")

    if updates:
        meta["last_update_id"] = updates[-1].update_id

    return history

# --- ПОВІДОМЛЕННЯ ---
def send_reports(config, history, month_idx, year):
    ukr_months = {
        1:"січень",2:"лютий",3:"березень",4:"квітень",5:"травень",6:"червень",
        7:"липень",8:"серпень",9:"вересень",10:"жовтень",11:"листопад",12:"грудень"
    }

    key = f"{month_idx:02d}-{year}"
    paid = sorted(history.get(key, []), key=int)
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active if a not in paid]

    sig = "\n\n_🤖 beta: можу помилятись, перевіряйте._"

    text = config['templates'][month_idx-1].format(
        month_name=ukr_months[month_idx],
        neighbors_list=", ".join(active),
        card=config['card_details'],
        amount=config['monthly_fee']
    )

    bot.send_message(CHAT_ID, text + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')

# --- RUN ---
def run():
    now = datetime.now(TIMEZONE)
    config = load_json('config.json')
    history = load_json('history.json')

    history = scan_payments(config, history, now)
    save_json('history.json', history)

    m, y = get_target_period(now)

    is_manual = os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    is_report_hour = now.hour in [9, 12]

    if is_manual or is_report_hour:
        send_reports(config, history, m, y)
    else:
        print("😴 Тільки сканування")

if __name__ == "__main__":
    run()

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

# Налаштування ID (з обробкою помилок)
try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') and os.getenv('THREAD_ID').strip() else None
except (ValueError, TypeError) as e:
    print(f"❌ Помилка в ID чату або теми: {e}")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Карта місяців
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

    print("🔍 Починаю сканування нових повідомлень...")

    try:
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
            if not any(kw in text for kw in confirm_keywords):
                continue

            target_months = []

            # Місяці текстом
            for m_idx, roots in MONTHS_MAP.items():
                if any(root in text for root in roots):
                    target_months.append(m_idx)

            # "за X міс"
            clean_text = text.replace(app_num, "", 1)
            multi = re.search(r'(\d+)\s*(міс|мес|місяц)', clean_text)
            if multi:
                count = int(multi.group(1))
                start_m, _ = get_target_period(now)
                for i in range(count):
                    target_months.append(((start_m + i - 1) % 12) + 1)

            if not target_months:
                m, _ = get_target_period(now)
                target_months = [m]

            for m_idx in set(target_months):
                _, year = get_target_period(now)
                if m_idx < now.month and now.month >= 11:
                    year += 1

                key = f"{m_idx:02d}-{year}"
                if key not in history:
                    history[key] = []

                if app_num not in history[key]:
                    history[key].append(app_num)
                    print(f"✅ Знайдено оплату: кв. {app_num} за {key}")

        if updates:
            meta["last_update_id"] = updates[-1].update_id

    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")

    return history

# --- ПОВІДОМЛЕННЯ ---
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
        text_tpl = config['templates'][month_idx-1].format(
            month_name=m_name,
            neighbors_list=", ".join(active),
            card=config['card_details'],
            amount=config['monthly_fee']
        )

        m = bot.send_message(
            CHAT_ID,
            text_tpl + sig,
            message_thread_id=THREAD_ID,
            parse_mode='Markdown'
        )

        try:
            bot.unpin_all_chat_messages(CHAT_ID)
            bot.pin_chat_message(CHAT_ID, m.message_id)
        except:
            pass

        report = random.choice(config['report_templates']).format(
            month_name=m_name,
            paid_list=", ".join(paid) if paid else "поки ніхто",
            unpaid_list=", ".join(unpaid) if unpaid else "всі! 🎉"
        )

        bot.send_message(CHAT_ID, report + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')

        if unpaid:
            remind = random.choice(config['reminder_templates']).format(
                month_name=m_name,
                unpaid_list=", ".join(unpaid),
                card=config['card_details']
            )
            bot.send_message(CHAT_ID, remind + sig, message_thread_id=THREAD_ID, parse_mode='Markdown')

        print("📢 Звіт надіслано успішно.")

    except Exception as e:
        print(f"⚠️ Помилка надсилання: {e}")

# --- RUN ---
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
    else:
        print(f"😴 Планове сканування о {now.hour}:00 завершено.")

if __name__ == "__main__":
    run()

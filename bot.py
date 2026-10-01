import os
import json
import re
import telebot
import pytz
import requests
import random
from datetime import datetime

# --- КОНФІГУРАЦІЯ ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
TIMEZONE = pytz.timezone('Europe/Kyiv')

try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') and os.getenv('THREAD_ID').strip() else None
except (ValueError, TypeError) as e:
    print(f"❌ Помилка ID: {e}")
    exit(1)

bot = telebot.TeleBot(TOKEN)

MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

# --- РОБОТА З ФАЙЛАМИ ---
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
        else: return now.month + 1, now.year
    else:
        return now.month, now.year

# --- СИНХРОНІЗАЦІЯ З GOOGLE SHEETS ---
def sync_to_google(history, config):
    script_url = os.getenv('GOOGLE_SCRIPT_URL')
    if not script_url:
        print("ℹ️ GOOGLE_SCRIPT_URL не знайдено. Синхронізація пропущена.")
        return

    print("🚀 Відправка даних в Google Sheets...")
    
    # Відфільтровуємо службові ключі перед відправкою в Google Таблицю
    clean_history = {k: v for k, v in history.items() if not k.startswith('_')}

    payload = {
        "history": clean_history,
        "active_apartments": config.get('active_apartments', [])
    }

    try:
        response = requests.post(script_url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Дані успішно оновлено в Google Таблиці.")
        else:
            print(f"⚠️ Google Script повернув помилку: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Помилка з'єднання з Google: {e}")

# --- СМАРТ-СКАНУВАННЯ ---
def scan_chat(config, history, now):
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    valid_triggers = ['опл', 'спла', 'скин', 'перек', '✅', '➕', 'плюс', 'грн', 'за']
    
    print("🔍 Сканую чат (останні 100 повідомлень)...")
    
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        for u in reversed(updates):
            if not u.message or u.message.chat.id != CHAT_ID:
                continue
            
            text = (u.message.text or "").lower()
            found_apps = []
            words = re.findall(r'\d+', text)
            for w in words:
                if w in active_apps:
                    found_apps.append(w)
            
            if not found_apps:
                continue

            is_payment = any(t in text for t in valid_triggers)
            if not is_payment and len(text) < 10: 
                is_payment = True 
            
            if is_payment:
                target_keys = []
                explicit_months = []
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots):
                        explicit_months.append(m_idx)
                
                multi_match = re.search(r'(\d+)\s*(міс|мес)', text)
                months_count = 1
                if multi_match:
                    months_count = int(multi_match.group(1))

                current_billing_m, current_billing_y = get_billing_period(now)
                
                if explicit_months:
                    for m in explicit_months:
                        y = current_billing_y
                        if now.month == 12 and m < 6: y += 1 
                        if now.month < 6 and m > 9: y -= 1 
                        target_keys.append(f"{m:02d}-{y}")
                
                elif months_count > 1:
                    start_m = current_billing_m
                    start_y = current_billing_y
                    for i in range(months_count):
                        total_m = start_m + i
                        calc_m = ((total_m - 1) % 12) + 1
                        calc_y = start_y + ((total_m - 1) // 12)
                        target_keys.append(f"{calc_m:02d}-{calc_y}")
                else:
                    target_keys.append(f"{current_billing_m:02d}-{current_billing_y}")

                for key in set(target_keys):
                    if key not in history: history[key] = []
                    for app in set(found_apps): 
                        if app not in history[key]:
                            history[key].append(app)
                            print(f"💰 Зараховано: кв. {app} за період {key}")

    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")
    
    return history

# --- ВІДПРАВКА ПОВІДОМЛЕНЬ ---
def process_notifications(config, history, now):
    target_m, target_y = get_billing_period(now)
    key = f"{target_m:02d}-{target_y}"
    
    paid = sorted(list(set(history.get(key, []))), key=int)
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active if a not in paid]

    ukr_months = {
        1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
        7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"
    }
    month_name = ukr_months[target_m]
    
    day = now.day
    is_manual = (os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    sent_list = history.get('_sent_notifications', [])
    
    msg = None
    should_pin = False
    notification_tag = None

    if day == 1:
        notification_tag = f"{now.strftime('%Y-%m')}-01_greeting"
        if notification_tag in sent_list and not is_manual:
            print(f"ℹ️ Привітання вже надсилалося сьогодні ({notification_tag}). Пропускаємо.")
            return

        print("📅 Сьогодні 1-ше число. Готуємо ПРИВІТАННЯ.")
        template = config['templates'][target_m-1]
        msg = template.format(
            month_name=month_name, 
            neighbors_list=", ".join(active), 
            card=config['card_details'], 
            amount=config['monthly_fee']
        )
        
        if paid:
            msg += f"\n\n🌟 **Вже сплатили наперед:** кв. {', '.join(paid)}"
            
        should_pin = True

    elif day == 11:
        notification_tag = f"{now.strftime('%Y-%m')}-11_report"
        if notification_tag in sent_list and not is_manual:
            print(f"ℹ️ Звіт вже надсилався сьогодні ({notification_tag}). Пропускаємо.")
            return

        print("📅 Сьогодні 11-те число. Готуємо ЗВІТ.")
        tpl = random.choice(config['report_templates'])
        msg = tpl.format(
            month_name=month_name,
            paid_list=", ".join(paid) if paid else "—",
            unpaid_list=", ".join(unpaid) if unpaid else "всі молодці! 🎉"
        )

    elif day == 19:
        notification_tag = f"{now.strftime('%Y-%m')}-19_reminder"
        if notification_tag in sent_list and not is_manual:
            print(f"ℹ️ Нагадування вже надсилалося сьогодні ({notification_tag}). Пропускаємо.")
            return

        print("📅 Сьогодні 19-те число. Готуємо НАГАДУВАННЯ.")
        if unpaid:
            tpl = random.choice(config['reminder_templates'])
            msg = tpl.format(
                month_name=month_name,
                unpaid_list=", ".join(unpaid),
                card=config['card_details']
            )
        else:
            print("🎉 Боржників немає, нагадування не потрібне.")

    else:
        print(f"📆 Сьогодні {day}-те число. Повідомлення за графіком не передбачені.")
        if is_manual:
            print("ℹ️ Ручний запуск: Тільки сканування.")

    if msg:
        try:
            sent_msg = bot.send_message(CHAT_ID, msg, message_thread_id=THREAD_ID, parse_mode='Markdown')
            print("✅ Повідомлення відправлено.")
            if should_pin:
                try:
                    bot.unpin_all_chat_messages(CHAT_ID)
                    bot.pin_chat_message(CHAT_ID, sent_msg.message_id)
                    print("📌 Повідомлення закріплено.")
                except Exception as pin_e:
                    print(f"⚠️ Не вдалося закріпити: {pin_e}")
            
            # Зафіксовуємо факт відправки
            if notification_tag:
                if '_sent_notifications' not in history:
                    history['_sent_notifications'] = []
                if notification_tag not in history['_sent_notifications']:
                    history['_sent_notifications'].append(notification_tag)

        except Exception as e:
            print(f"❌ Помилка відправки Telegram: {e}")

# --- MAIN ---
def run():
    now = datetime.now(TIMEZONE)
    print(f"🕒 Запуск бота: {now.strftime('%Y-%m-%d %H:%M:%S')} (Kyiv)")
    
    config = load_json('config.json')
    history = load_json('history.json')

    # 1. Скануємо чат та оновлюємо історію оплат
    history = scan_chat(config, history, now)
    
    # 2. Перевіряємо та надсилаємо сповіщення (якщо це 1, 11 або 19 число та час >= 09:00 Kyiv)
    if now.hour >= 9:
        process_notifications(config, history, now)
    else:
        print("🌙 Нічний/ранішній запуск (до 09:00). Тільки сканування та синхронізація.")

    # 3. Зберігаємо оновлені дані локально
    save_json('history.json', history)
    
    # 4. Відправляємо оновлені дані в Google Таблицю
    sync_to_google(history, config)

if __name__ == "__main__":
    run()

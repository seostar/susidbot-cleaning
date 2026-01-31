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

# Перетворюємо ID на числа, щоб уникнути помилок Telegram API
try:
    CHAT_ID = int(os.getenv('CHAT_ID')) if os.getenv('CHAT_ID') else None
    THREAD_ID = int(os.getenv('THREAD_ID')) if os.getenv('THREAD_ID') and os.getenv('THREAD_ID').strip() else None
except ValueError as e:
    print(f"❌ Помилка: ID чату або теми мають бути числами! {e}")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Карта коренів місяців для розпізнавання в тексті
MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

# --- ДОПОМІЖНІ ФУНКЦІЇ ---

def load_data(filename):
    """Завантажує дані з JSON файлу."""
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(filename, data):
    """Зберігає дані у JSON файл."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_target_period(now):
    """Визначає актуальний місяць та рік для оплати (після 25-го числа - наступний)."""
    month = now.month if now.day < 25 else (now.month % 12) + 1
    year = now.year if not (now.month == 12 and month == 1) else now.year + 1
    return month, year

# --- ОСНОВНА ЛОГІКА ---

def scan_payments(config, history, now):
    """Сканує чат на наявність повідомлень про оплату."""
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    keywords = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'переказ', 'скинув', 'за']

    print("🔍 Сканування повідомлень...")
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        for u in updates:
            if not u.message or u.message.chat.id != CHAT_ID:
                continue

            text = (u.message.text or "").lower()
            
            # Шукаємо номер квартири (перше число в тексті)
            match = re.search(r'\d+', text)
            if not match:
                continue

            app_num = match.group()
            if app_num not in active_apps:
                continue

            # Перевірка на ключові слова або символ "+"
            if any(kw in text for kw in keywords) or "+" in text:
                target_months = []

                # 1. Пошук назви місяця
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots):
                        target_months.append(m_idx)

                # 2. Пошук конструкції "за X міс"
                clean_text = text.replace(app_num, "", 1)
                multi = re.search(r'(\d+)\s*(міс|мес|місяц)', clean_text)
                if multi:
                    count = int(multi.group(1))
                    start_m, _ = get_target_period(now)
                    for i in range(count):
                        target_months.append(((start_m + i - 1) % 12) + 1)

                # 3. Якщо місяць не вказано - беремо поточний цільовий
                if not target_months:
                    m, _ = get_target_period(now)
                    target_months = [m]

                # Записуємо в історію
                for m_idx in set(target_months):
                    _, year = get_target_period(now)
                    # Корекція року для минулих місяців у кінці року
                    if m_idx < now.month and now.month >= 11:
                        year += 1
                    
                    key = f"{m_idx:02d}-{year}"
                    if key not in history: history[key] = []
                    if app_num not in history[key]:
                        history[key].append(app_num)
                        print(f"✅ Додано: кв. {app_num} за {key}")

    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")
    
    return history

def send_reports(config, history, month_idx, year):
    """Формує та надсилає звіти в Telegram."""
    ukr_months = {
        1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
        7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"
    }
    
    m_name = ukr_months[month_idx]
    key = f"{month_idx:02d}-{year}"
    
    paid = sorted(list(set(history.get(key, []))), key=int)
    active_list = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    sig = "\n\n_🤖 автоматичний звіт_"

    try:
        # 1. Основні реквізити (Template)
        main_msg = config['templates'][month_idx-1].format(
            month_name=m_name, neighbors_list=", ".join(active_list), 
            card=config['card_details'], amount=config['monthly_fee']) + sig
        
        sent = bot.send_message(CHAT_ID, main_msg, message_thread_id=THREAD_ID, parse_mode='Markdown')
        
        # Оновлення закріпленого повідомлення
        try:
            bot.unpin_all_chat_messages(CHAT_ID)
            bot.pin_chat_message(CHAT_ID, sent.message_id)
        except: pass

        # 2. Список тих, хто здав / не здав
        report_msg = random.choice(config['report_templates']).format(
            month_name=m_name, 
            paid_list=", ".join(paid) if paid else "поки ніхто", 
            unpaid_list=", ".join(unpaid) if unpaid else "всі! 🎉") + sig
        bot.send_message(CHAT_ID, report_msg, message_thread_id=THREAD_ID, parse_mode='Markdown')

        # 3. Нагадування (якщо є боржники)
        if unpaid:
            remind_msg = random.choice(config['reminder_templates']).format(
                month_name=m_name, unpaid_list=", ".join(unpaid), 
                card=config['card_details']) + sig
            bot.send_message(CHAT_ID, remind_msg, message_thread_id=THREAD_ID, parse_mode='Markdown')
            
        print("📢 Звіти успішно надіслані в чат.")
    except Exception as e:
        print(f"⚠️ Помилка надсилання: {e}")

# --- ТОЧКА ВХОДУ ---

def main():
    now = datetime.now(TIMEZONE)
    config = load_data('config.json')
    history = load_data('history.json')

    # Оновлюємо дані про оплати
    updated_history = scan_payments(config, history, now)
    save_data('history.json', updated_history)

    # Визначаємо цільовий місяць для звіту
    target_m, target_y = get_target_period(now)
    
    event = os.getenv('GITHUB_EVENT_NAME')
    
    # Вирішуємо, чи публікувати звіт у чат
    # Умови: ручний запуск АБО дати 1, 11, 19
    is_report_day = now.day in [1, 11, 19]
    is_manual = (event == 'workflow_dispatch')

    if is_manual or is_report_day:
        print(f"🚀 Запуск звіту (Причина: {'ручна' if is_manual else 'планова'})")
        send_reports(config, updated_history, target_m, target_y)
    else:
        print(f"ℹ️ Сьогодні {now.day}-те число. Тільки оновлення бази даних.")

if __name__ == "__main__":
    main()

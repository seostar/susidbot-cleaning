import os
import json
import re
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
    """
    Логіка:
    - До 25 числа — працюємо з поточним місяцем.
    - Після 25 числа — вважаємо, що оплати йдуть вже за наступний.
    Повертає (month, year) "цільового" місяця збору.
    """
    if now.day >= 25:
        # Наступний місяць
        if now.month == 12:
            return 1, now.year + 1
        else:
            return now.month + 1, now.year
    else:
        # Поточний місяць
        return now.month, now.year

# --- СМАРТ-СКАНУВАННЯ ---
def scan_chat(config, history, now):
    active_apps = [str(a) for a in config.get('active_apartments', [])]
    
    # Ключові слова, що це точно про оплату
    valid_triggers = ['опл', 'спла', 'скин', 'перек', '✅', '➕', 'плюс', 'грн', 'за']
    
    print("🔍 Сканую чат (останні 100 повідомлень)...")
    
    try:
        # Беремо останні повідомлення
        updates = bot.get_updates(limit=100, timeout=10)
        # Обертаємо список, щоб спочатку обробляти старіші, потім новіші (логічніше для історії)
        for u in reversed(updates):
            if not u.message or u.message.chat.id != CHAT_ID:
                continue
            
            text = (u.message.text or "").lower()
            
            # 1. Шукаємо номери квартир у повідомленні
            # Знаходить всі числа, які є в списку active_apartments
            found_apps = []
            words = re.findall(r'\d+', text)
            for w in words:
                if w in active_apps:
                    found_apps.append(w)
            
            if not found_apps:
                continue

            # 2. Перевіряємо, чи це повідомлення про оплату
            is_payment = any(t in text for t in valid_triggers)
            # Додаткова евристика: якщо просто число і емодзі або коротка відповідь
            if not is_payment and len(text) < 10: 
                is_payment = True 
            
            if is_payment:
                # 3. Визначаємо, за які місяці оплата
                target_keys = []
                
                # А) Перевірка на конкретні назви місяців у тексті (пріоритет)
                explicit_months = []
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots):
                        explicit_months.append(m_idx)
                
                # Б) Перевірка на "за 2 місяці", "за 3 мес"
                multi_match = re.search(r'(\d+)\s*(міс|мес)', text)
                months_count = 1
                if multi_match:
                    months_count = int(multi_match.group(1))

                # В) Формуємо ключі (MM-YYYY)
                current_billing_m, current_billing_y = get_billing_period(now)
                
                if explicit_months:
                    # Якщо вказані конкретні місяці (напр. "за січень і лютий")
                    for m in explicit_months:
                        # Спроба вгадати рік. Якщо зараз грудень (12), а платять за січень (1) — це наст. рік
                        y = current_billing_y
                        if now.month == 12 and m < 6: y += 1 
                        if now.month < 6 and m > 9: y -= 1 # Рідкісний кейс (платять за минулий рік)
                        target_keys.append(f"{m:02d}-{y}")
                
                elif months_count > 1:
                    # Якщо "за 2 місяці" — беремо поточний цільовий + наступні
                    start_m = current_billing_m
                    start_y = current_billing_y
                    for i in range(months_count):
                        # Математика додавання місяців
                        total_m = start_m + i
                        calc_m = ((total_m - 1) % 12) + 1
                        calc_y = start_y + ((total_m - 1) // 12)
                        target_keys.append(f"{calc_m:02d}-{calc_y}")
                else:
                    # Стандарт: за поточний розрахунковий місяць
                    target_keys.append(f"{current_billing_m:02d}-{current_billing_y}")

                # 4. Записуємо в базу
                for key in set(target_keys):
                    if key not in history: history[key] = []
                    for app in set(found_apps): # set щоб прибрати дублі, якщо двічі написали 44
                        if app not in history[key]:
                            history[key].append(app)
                            print(f"💰 Зараховано: кв. {app} за період {key}")

    except Exception as e:
        print(f"⚠️ Помилка сканування: {e}")
        # Не падаємо, щоб зберегти хоча б те, що встигли
    
    return history

# --- ВІДПРАВКА ПОВІДОМЛЕНЬ (СТРОГО ПО ДАТАХ) ---
def process_notifications(config, history, now):
    target_m, target_y = get_billing_period(now)
    key = f"{target_m:02d}-{target_y}"
    
    # Списки
    paid = sorted(list(set(history.get(key, []))), key=int)
    active = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active if a not in paid]

    ukr_months = {
        1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
        7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"
    }
    month_name = ukr_months[target_m]
    
    # Визначаємо тип дії за датою
    day = now.day
    hour = now.hour
    
    # Прапорець для ручного запуску (GITHUB_EVENT_NAME)
    is_manual = (os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch')
    
    msg = None
    should_pin = False

    # ЛОГІКА РОЗКЛАДУ
    if day == 1:
        print("📅 Сьогодні 1-ше число. Готуємо ПРИВІТАННЯ.")
        template = config['templates'][target_m-1]
        msg = template.format(
            month_name=month_name, 
            neighbors_list=", ".join(active), 
            card=config['card_details'], 
            amount=config['monthly_fee']
        )
        should_pin = True

    elif day == 11:
        print("📅 Сьогодні 11-те число. Готуємо ЗВІТ (Статистика).")
        # Беремо випадковий шаблон звіту
        tpl = random.choice(config['report_templates'])
        msg = tpl.format(
            month_name=month_name,
            paid_list=", ".join(paid) if paid else "—",
            unpaid_list=", ".join(unpaid) if unpaid else "всі молодці! 🎉"
        )

    elif day == 19:
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
             print("ℹ️ Ручний запуск: Тільки сканування виконано. Щоб протестувати повідомлення, змініть дату на сервері або логіку коду.")

    # ВІДПРАВКА
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
        except Exception as e:
            print(f"❌ Помилка відправки Telegram: {e}")

# --- MAIN ---
def run():
    now = datetime.now(TIMEZONE)
    print(f"🕒 Запуск бота: {now.strftime('%Y-%m-%d %H:%M:%S')} (Kyiv)")
    
    config = load_json('config.json')
    history = load_json('history.json')

    # 1. Завжди скануємо чат і оновлюємо базу
    history = scan_chat(config, history, now)
    save_json('history.json', history)
    
    # 2. Перевіряємо, чи треба слати повідомлення
    # Перевірка часу: дозволяємо відправку тільки в діапазоні ранку/дня, 
    # щоб нічне сканування (22:30) нічого випадково не слало.
    if 8 <= now.hour <= 14:
        process_notifications(config, history, now)
    else:
        print("🌙 Вечірній/Нічний запуск. Тільки оновлення бази.")

if __name__ == "__main__":
    run()

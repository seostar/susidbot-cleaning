
import os, json, re, random, telebot, pytz
from datetime import datetime

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
THREAD_ID = os.getenv('THREAD_ID')
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
    
    # --- КРОК 1: АВТО-СКАН ЧАТУ ---
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        confirm_keywords = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'переказ', 'скинула']

        for u in updates:
            if not u.message or str(u.message.chat.id) != str(CHAT_ID): continue
            text = u.message.text.lower() if u.message.text else ""
            
            all_numbers = re.findall(r'\d+', text)
            app_num = next((n for n in all_numbers if n in active_apps), None)
            
            if app_num and (any(kw in text for kw in confirm_keywords) or "+" in text):
                target_months = []
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots): target_months.append(m_idx)
                
                # Обробка "за X міс"
                multi_match = re.search(r'(\d+)\s*(міс|мес|місяц)', text.replace(app_num, ""))
                if multi_match:
                    count = int(multi_match.group(1))
                    start_m = now.month if now.day < 25 else (now.month % 12) + 1
                    for i in range(count):
                        target_months.append(((start_m + i - 1) % 12) + 1)

                if not target_months:
                    target_months = [now.month if now.day < 25 else (now.month % 12) + 1]
                
                for m_idx in set(target_months):
                    year = now.year
                    if m_idx < now.month and now.month >= 10: year += 1
                    key = f"{m_idx:02d}-{year}"
                    if key not in history: history[key] = []
                    if app_num not in history[key]: history[key].append(app_num)
    except Exception as e:
        print(f"Scan error: {e}")

    # --- КРОК 2: ПРИМУСОВЕ ВНЕСЕННЯ (якщо бот не бачить чат) ---
    # Якщо в корневій папці є файл manual_paid.txt з номерами через кому
    if os.path.exists('manual_paid.txt'):
        with open('manual_paid.txt', 'r') as f:
            manual_nums = re.findall(r'\d+', f.read())
            target_key = f"{(now.month if now.day < 25 else (now.month % 12) + 1):02d}-{now.year}"
            if target_key not in history: history[target_key] = []
            for n in manual_nums:
                if n in active_apps and n not in history[target_key]:
                    history[target_key].append(n)
    
    save_history(history)
    return history

def send_all_messages(config, history, month_idx, year):
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    
    m_name = ukr_months[month_idx]
    curr_key = f"{month_idx:02d}-{year}"
    
    # БЕРЕМО ДАНІ ТІЛЬКИ З HISTORY.JSON
    paid = sorted(list(set(history.get(curr_key, []))), key=int)
    active_list = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    signature = "\n\n_🤖 beta-версія_"

    try:
        # 1. Реквізити
        main_text = config['templates'][month_idx-1].format(
            month_name=m_name, neighbors_list=", ".join(active_list), 
            card=config['card_details'], amount=config['monthly_fee']) + signature
        m = bot.send_message(CHAT_ID, main_text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        bot.unpin_all_chat_messages(CHAT_ID)
        bot.pin_chat_message(CHAT_ID, m.message_id)

        # 2. Звіт (Використовує тільки реальні цифри з paid)
        report = random.choice(config['report_templates']).format(
            month_name=m_name, 
            paid_list=", ".join(paid) if paid else "поки ніхто", 
            unpaid_list=", ".join(unpaid) if unpaid else "всі! 🎉") + signature
        bot.send_message(CHAT_ID, report, message_thread_id=THREAD_ID, parse_mode='Markdown')

        # 3. Нагадування
        if unpaid:
            remind = random.choice(config['reminder_templates']).format(
                month_name=m_name, unpaid_list=", ".join(unpaid), 
                card=config['card_details']) + signature
            bot.send_message(CHAT_ID, remind, message_thread_id=THREAD_ID, parse_mode='Markdown')
    except Exception as e:
        print(f"Send error: {e}")

def run_logic():
    history = scan_and_update()
    config = load_json('config.json')
    now = datetime.now(TIMEZONE)
    target_month = now.month if now.day < 25 else (now.month % 12) + 1
    target_year = now.year if not (now.month == 12 and target_month == 1) else now.year + 1

    if os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        send_all_messages(config, history, target_month, target_year)

if __name__ == "__main__":
    run_logic()

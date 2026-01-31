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
    
    try:
        updates = bot.get_updates(limit=100, timeout=10)
        confirm_keywords = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'скину', 'переказ', 'опалч', 'оплае']

        for u in updates:
            if not u.message or str(u.message.chat.id) != str(CHAT_ID): continue
            text = u.message.text.lower() if u.message.text else ""
            found_numbers = re.findall(r'(\d+)', text)
            
            if any(kw in text for kw in confirm_keywords) or "+" in text:
                target_months = []
                for m_idx, roots in MONTHS_MAP.items():
                    if any(root in text for root in roots):
                        target_months.append(m_idx)
                
                if not target_months:
                    target_months = [now.month if now.day < 25 else (now.month % 12) + 1]
                
                for num in found_numbers:
                    if num in active_apps:
                        for m_idx in target_months:
                            year = now.year
                            if m_idx == 1 and now.month == 12: year += 1
                            if m_idx == 12 and now.month == 1: year -= 1
                            key = f"{m_idx:02d}-{year}"
                            if key not in history: history[key] = []
                            if num not in history[key]: history[key].append(num)
    except Exception as e:
        print(f"Scan error: {e}")
    
    save_history(history)
    return history

def send_all_messages(config, history, month_idx, year):
    ukr_months = {1:"січень", 2:"лютий", 3:"березень", 4:"квітень", 5:"травень", 6:"червень", 
                  7:"липень", 8:"серпень", 9:"вересень", 10:"жовтень", 11:"листопад", 12:"грудень"}
    
    m_name = ukr_months[month_idx]
    curr_key = f"{month_idx:02d}-{year}"
    
    paid = history.get(curr_key, [])
    active_list = sorted([str(a) for a in config.get('active_apartments', [])], key=int)
    unpaid = [a for a in active_list if a not in paid]
    
    signature = "\n\n_🤖 beta-версія (бот може помилятися)_"

    # 1. ЗБІР (ЗАКРІПЛЮЄТЬСЯ)
    try:
        main_text = config['templates'][month_idx-1].format(
            month_name=m_name, 
            neighbors_list=", ".join(active_list), 
            card=config['card_details'], 
            amount=config['monthly_fee']
        ) + signature
        
        main_msg = bot.send_message(CHAT_ID, main_text, message_thread_id=THREAD_ID, parse_mode='Markdown')
        bot.unpin_all_chat_messages(CHAT_ID)
        bot.pin_chat_message(CHAT_ID, main_msg.message_id)
    except Exception as e:
        print(f"Pin error: {e}")

    # 2. ЗВІТ
    report_text = random.choice(config['report_templates']).format(
        month_name=m_name, 
        paid_list=", ".join(sorted(paid, key=int)) if paid else "нікого ще немає", 
        unpaid_list=", ".join(unpaid) if unpaid else "всіх! 🎉"
    ) + signature
    bot.send_message(CHAT_ID, report_text, message_thread_id=THREAD_ID

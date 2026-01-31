def scan_and_update():
    config = load_json('config.json')
    history = load_json('history.json')
    now = datetime.now(TIMEZONE)
    active_apps = [str(a) for a in config['active_apartments']]
    
    updates = bot.get_updates(limit=100, timeout=10)
    # Додав варіанти з помилками: опалч, оплае
    confirm_keywords = ['оплат', 'сплач', 'готов', 'є', 'есть', 'ок', '+', '✅', 'скину', 'переказ', 'опалч', 'оплае']

    for u in updates:
        if not u.message or str(u.message.chat.id) != str(CHAT_ID): continue
        msg_time = datetime.fromtimestamp(u.message.date, pytz.utc).astimezone(TIMEZONE)
        
        # Перевіряємо повідомлення за останні 2 дні для надійності
        if (now - msg_time).total_seconds() > 172800: continue

        text = u.message.text.lower() if u.message.text else ""
        found_numbers = re.findall(r'(\d+)', text)
        
        if any(kw in text for kw in confirm_keywords) or "+" in text:
            target_months = []
            for m_idx, roots in MONTHS_MAP.items():
                if any(root in text for root in roots):
                    target_months.append(m_idx)
            
            # Якщо місяць не вказано — беремо поточний
            if not target_months: target_months = [now.month]
            
            for num in found_numbers:
                if num in active_apps:
                    for m_idx in target_months:
                        key = f"{m_idx:02d}-{now.year}"
                        if key not in history: history[key] = []
                        if num not in history[key]: history[key].append(num)
    
    save_history(history)
    return history

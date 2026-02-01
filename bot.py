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

# Словник для пошуку місяців
MONTHS_MAP = {
    1: ['січ', 'янв'], 2: ['лют', 'фев'], 3: ['берез', 'март'],
    4: ['квіт', 'апр'], 5: ['трав', 'май'], 6: ['черв', 'июн'],
    7: ['лип', 'июл'], 8: ['серп', 'авг'], 9: ['верес', 'сент'],
    10: ['жовт', 'окт'], 11: ['лист', 'нояб'], 12: ['груд', 'дек']
}

# --- ДОПОМІЖНІ ФУНКЦІЇ ---

def load_json(path):
    """Завантажує JSON або повертає порожній словник при помилці"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception as e:
                print(f"⚠️ Помилка читання {path}: {e}")
                return {}
    return {}

def save_json(path, data):
    """Зберігає дані, сортуючи номери квартир для зручності"""
    with open(path, 'w', encoding='utf-8') as f:
        # Сортуємо списки квартир перед записом у файл
        for key in data:
            if isinstance(data[key], list):
                data[key] = sorted(list(set(str(x) for x in data[key])), key=int)
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_target_period(now):
    """Визначає місяць оплати (після 25 числа — наступний)"""
    m = now.month if now.day < 25 else (now.month % 12) + 1
    y = now.year if not (now.month == 12 and m == 1) else now.year + 1
    return m, y

# ---

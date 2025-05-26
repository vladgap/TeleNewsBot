# main.py

import os
import asyncio
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
import anthropic
from zoneinfo import ZoneInfo

# 1. Загрузка ключей из .env файла
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
SESSION_NAME = "news_bot_session"

# Проверка загрузки ключей
print(f"TELEGRAM_TOKEN загружен: {TELEGRAM_TOKEN is not None}")
print(f"API_ID загружен: {API_ID is not None}")
print(f"API_HASH загружен: {API_HASH is not None}")
print(f"CLAUDE_API_KEY загружен: {CLAUDE_API_KEY is not None}")

if not all([TELEGRAM_TOKEN, API_ID, API_HASH, CLAUDE_API_KEY]):
    print("ОШИБКА: Не все ключи загружены из .env файла!")
    exit(1)

# 2. Инициализация клиентов
claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

# Таймзона Иерусалима
JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")

# Каналы для мониторинга
TARGET_CHANNELS = ['NEWSruIsrael', 'DilimShavimPlus'] 

# --- ФУНКЦИИ-ПОМОЩНИКИ ---

async def get_time_range(user_text: str):
    current_time = datetime.now(JERUSALEM_TZ)
    prompt = f"""
    Текущее время в Иерусалиме: {current_time.isoformat()}.
    Определи начальное и конечное время для поиска новостей на основе запроса пользователя.
    Запрос: "{user_text}"
    Верни ответ ТОЛЬКО в формате JSON с ключами "start_time" и "end_time" в формате ISO 8601.
    Если не можешь определить время, верни {{"start_time": null, "end_time": null}}.
    """
    try:
        response = claude_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = response.content[0].text.strip()
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response_text[start_idx:end_idx]
            data = json.loads(json_str)
            if data.get("start_time") and data.get("end_time"):
                start = datetime.fromisoformat(data["start_time"]).astimezone(JERUSALEM_TZ)
                end = datetime.fromisoformat(data["end_time"]).astimezone(JERUSALEM_TZ)
                return start, end
    except Exception as e:
        print(f"Ошибка при анализе времени: {e}")
    return None

async def fetch_news_from_telegram(channels, start_time, end_time):
    all_posts = []
    try:
        async with TelegramClient(SESSION_NAME, int(API_ID), API_HASH) as client:
            for channel in channels:
                try:
                    entity = await client.get_entity(channel)
                    async for message in client.iter_messages(entity, offset_date=end_time):
                        msg_time = message.date.astimezone(JERUSALEM_TZ)
                        if msg_time < start_time:
                            break
                        if msg_time > end_time:
                            continue
                        if message.text and not message.is_reply:
                            post_text = f"Из канала @{channel} ({msg_time.strftime('%H:%M %d.%m')}):\n{message.text}\n\n---\n"
                            all_posts.append(post_text)
                            if len(all_posts) >= 10:
                                break
                except Exception as e:
                    print(f"Не удалось получить сообщения из {channel}: {e}")
    except Exception as e:
        print(f"Ошибка Telethon: {e}")
        return []
    return all_posts

async def summarize_with_claude(posts):
    if not posts:
        return "Новостей для анализа не найдено."
    full_text = "".join(posts)
    if len(full_text) > 15000:
        full_text = full_text[:15000] + "\n...(текст обрезан)"
    prompt = f"""
    Ты — ИИ-аналитик новостей. Сделай краткую и четкую выжимку из предоставленных постов из Telegram-каналов.
    Сгруппируй новости по темам. Убери все маловажное. 
    Отформатируй ответ для Telegram, используя обычный текст без специальной разметки.
    Не придумывай ничего, основывайся только на тексте ниже.

    Текст для анализа:
    {full_text}
    """
    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Ошибка при суммаризации: {e}")
        return "Не удалось обработать новости."

# --- ОБРАБОТЧИКИ БОТА ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.message.chat_id
    print(f"Получен запрос от {chat_id}: {user_text}")
    await context.bot.send_message(chat_id, "✅ Принято! Анализирую запрос...")

    time_range = await get_time_range(user_text)
    if not time_range:
        await context.bot.send_message(chat_id, "❌ Не удалось понять временной интервал. Попробуйте 'за последние 6 часов' или 'за вчера'.")
        return

    start_time, end_time = time_range
    await context.bot.send_message(
        chat_id, 
        f"Ищу посты в каналах {TARGET_CHANNELS} с {start_time.strftime('%H:%M %d.%m')} по {end_time.strftime('%H:%M %d.%m')}..."
    )
    posts = await fetch_news_from_telegram(TARGET_CHANNELS, start_time, end_time)
    if not posts:
        await context.bot.send_message(chat_id, "🤷 Новостей за указанный период не найдено.")
        return

    await context.bot.send_message(chat_id, f"Найдено постов: {len(posts)}. Отправляю на суммаризацию...")
    summary = await summarize_with_claude(posts)
    if len(summary) > 4000:
        chunks = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
        for i, chunk in enumerate(chunks):
            await context.bot.send_message(chat_id, f"Часть {i+1}:\n\n{chunk}")
    else:
        await context.bot.send_message(chat_id, summary)

# --- ЗАПУСК БОТА ---

def main():
    print("Бот запускается...")
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("Бот готов к работе!")
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()

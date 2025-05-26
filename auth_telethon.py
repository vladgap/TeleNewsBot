# auth_telethon.py
# Запустите этот файл ОДИН РАЗ для авторизации Telethon

import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

# Загружаем ключи
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = "news_bot_session"

async def main():
    print("=== АВТОРИЗАЦИЯ TELETHON ===")
    print("Этот скрипт нужно запустить только один раз для авторизации.")
    print("После авторизации будет создан файл сессии, и основной бот будет работать автоматически.")
    print()

    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    
    try:
        await client.start()
        print("Успешно авторизован!")
        print(f"Файл сессии '{SESSION_NAME}.session' создан.")
        
        # Тестируем доступ к каналам
        print("\nТестируем доступ к каналам...")
        test_channels = ['durov', 'telegram']
        
        for channel in test_channels:
            try:
                entity = await client.get_entity(channel)
                print(f"✅ Канал @{channel} доступен: {entity.title}")
            except Exception as e:
                print(f"❌ Канал @{channel} недоступен: {e}")
        
        print("\nАвторизация завершена!")
        
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
import os
from dotenv import load_dotenv
import re
import random
import asyncio
from typing import Dict, List
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

load_dotenv()
LAST_UPDATES = -6
RANDOM_REPLY_CHANCE = 0.03
RANDOM_REPLIES = ["тру", "Нахуя пиздеть, если ты пидорас", "Аригато казаймас", "бб", "шок", "офк", "нн", "жиза",
                  "ГОУ?", "ШО", "КАЙФ", "кринж", "лол", "окей", "Трахать?", "Трахать!!!", "Сукааааааа",
                  "Я что дод?!", "Очень интереесно, но я не помню чтоб спрашивал", "Дякую", "Мы"]

# Карта: шаблон-триггер (regex) -> варианты ответов
TRIGGERS: Dict[str, List[str]] = {
    r"\bалвап\b": ["тру", "Нахуя пиздеть, если ты пидорас", "Аригато казаймас", "бб", "шок",
                   "офк", "нн", "жиза", "ГОУ?", "ШО", "КАЙФ"],
    r"\bрандон\b": ["кринж", "лол", "окей", "Трахать?", "Трахать!!!", "Я что дод?!",
                    "Очень интереесно, но я не помню чтоб спрашивал"],

    r"(баб|секс|трах|ебля|пизда|хуй)": ["Трахать?", "Трахать!!!", "Очень интереесно, но я не помню чтоб спрашивал",
                                        "нн", "Аригато казаймас", "КАЙФ", "ШО", "Сукааааааа"],

    r"(жиз|сук)": ["шок", "офк", "тру", "ШО", "КАЙФ", "Сукааааааа"],
    r"зумер": ["кринж", "КАЙФ", "Я что дод?!", "лол", "Сукааааааа"],
}


def find_response(text: str) -> str | None:
    normalized = text.casefold()
    for pattern, replies in TRIGGERS.items():
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return random.choice(replies)
    return None


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("I lurk in the chat, listening for forbidden triggers,"
                                    " and strike back with chaos. Summon me to your group.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    # Игнорируем свои сообщения
    if update.message.from_user and update.message.from_user.is_bot:
        return

    reply = find_response(update.message.text)
    if reply:
        await update.message.reply_text(reply)
    else:
        if random.random() < RANDOM_REPLY_CHANCE:
            await update.message.reply_text(random.choice(RANDOM_REPLIES))


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения.")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    await app.initialize()

    try:
        # Preload recent updates safely
        updates = await app.bot.get_updates()
        if updates:
            recent_updates = updates[LAST_UPDATES:]
            for upd in recent_updates:
                await app.process_update(upd)
            last_id = updates[-1].update_id
            await app.bot.get_updates(offset=last_id + 1)
        print("Bot is running...")

        await app.start()
        # Start polling without creating a nested event loop
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        try:
            await asyncio.Event().wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        # Graceful shutdown
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

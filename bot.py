import os
import html
from urllib.parse import urlparse
from io import BytesIO
import aiohttp
from dotenv import load_dotenv
import re
import random
import asyncio
from typing import Dict, List
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

load_dotenv()
VALID_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm")
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


def _as_dict(x) -> dict:
    return x if isinstance(x, dict) else {}


def _as_list(x) -> list:
    return x if isinstance(x, list) else []


def _extract_image_from_preview(post) -> str | None:
    post = _as_dict(post)
    preview = _as_dict(post.get("preview"))
    images = _as_list(preview.get("images"))
    if images:
        src = _as_dict(images[0]).get("source")
        url = _as_dict(src).get("url")
        if url:
            return html.unescape(url)
    return None


def _extract_from_gallery(post) -> str | None:
    post = _as_dict(post)
    if not post.get("is_gallery"):
        return None
    media = _as_dict(post.get("media_metadata"))
    candidates = []
    for item in media.values():
        item = _as_dict(item)
        p_list = _as_list(item.get("p"))
        if p_list:
            url = _as_dict(p_list[-1]).get("u") or _as_dict(p_list[0]).get("u")
        else:
            url = _as_dict(item.get("s")).get("u")
        if url:
            candidates.append(html.unescape(url))
    return random.choice(candidates) if candidates else None


def _extract_reddit_video(post) -> str | None:
    post = _as_dict(post)
    rv = _as_dict(_as_dict(post.get("secure_media")).get("reddit_video"))
    if rv.get("fallback_url"):
        return rv["fallback_url"]
    for cp in _as_list(post.get("crosspost_parent_list")):
        rv = _as_dict(_as_dict(_as_dict(cp).get("secure_media")).get("reddit_video"))
        if rv.get("fallback_url"):
            return rv["fallback_url"]
    return None


def _extract_url_overridden(post) -> str | None:
    post = _as_dict(post)
    url = post.get("url_overridden_by_dest") or post.get("url")
    if url:
        return html.unescape(url)
    return None


def _looks_like_media(url: str) -> bool:
    if url.endswith(VALID_EXTENSIONS):
        return True
    host = urlparse(url).netloc
    return host in {"i.redd.it", "v.redd.it", "i.imgur.com", "imgur.com"}


async def _collect_posts(session: aiohttp.ClientSession, listing: str, pages: int = 10) -> List[dict]:
    """
    Собирает до ~1000 постов (10 страниц по 100) из указанного листинга:
    listing: 'hot', 'new', 'top', 'rising'
    """
    headers = {
        "User-Agent": "telegram-bot/1.0 (by u/yourusername)",
        "Accept": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=20)
    after = None
    collected: List[dict] = []

    for _ in range(pages):
        params = {"limit": 100, "raw_json": 1}
        if listing == "top":
            params["t"] = "all"
        if after:
            params["after"] = after

        url = f"https://www.reddit.com/r/BurntFood/{listing}.json"
        async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
            if resp.status != 200:
                break
            data = await resp.json()

        children = _as_list(_as_dict(data.get("data")).get("children"))
        if not children:
            break

        collected.extend(children)
        after = _as_dict(data.get("data")).get("after")
        if not after:
            break

    return collected


async def reddit_burntfood() -> tuple[str, str]:
    """
    Возвращает случайный фото/видео пост с r/BurntFood из последних ~1000 постов
    (hot + new, при необходимости top(all) и rising)
    """
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        order = ["hot", "new", "top", "rising"]
        posts = []
        for listing in order:
            posts = await _collect_posts(session, listing, pages=10)
            if posts:
                break

    if not posts:
        raise RuntimeError("❌ Не удалось получить посты r/BurntFood.")

    media_posts: List[tuple[str, str]] = []

    for p in posts:
        post = _as_dict(_as_dict(p).get("data"))
        if not post:
            continue
        title = post.get("title") or "🔥 Burnt Food special"

        vurl = _extract_reddit_video(post)
        if vurl:
            media_posts.append((vurl, title))
            continue

        gurl = _extract_from_gallery(post)
        if gurl and _looks_like_media(gurl):
            media_posts.append((gurl, title))
            continue

        ipreview = _extract_image_from_preview(post)
        if ipreview and _looks_like_media(ipreview):
            media_posts.append((ipreview, title))
            continue

        ourl = _extract_url_overridden(post)
        if ourl and _looks_like_media(ourl):
            media_posts.append((ourl, title))
            continue

        for cp in _as_list(post.get("crosspost_parent_list")):
            cp = _as_dict(cp)
            ourl = cp.get("url_overridden_by_dest") or cp.get("url")
            if ourl:
                ourl = html.unescape(ourl)
                if _looks_like_media(ourl):
                    media_posts.append((ourl, title))
                    break

    if not media_posts:
        raise RuntimeError("❌ Нет фото/видео постов в r/BurntFood среди последних ~1000.")

    return random.choice(media_posts)


async def _download_bytes(url: str, max_bytes: int = 40 * 1024 * 1024) -> bytes:
    """Улучшенная функция скачивания с обработкой ошибок"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientError(f"HTTP {resp.status}")

                buf = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise RuntimeError("Файл слишком большой для отправки.")
                return bytes(buf)
        except Exception as e:
            raise RuntimeError(f"Ошибка скачивания {url}: {e}")


async def send_burnt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /burnt — отправляет случайный пост"""
    try:
        url, title = await reddit_burntfood()
        if url.endswith((".jpg", ".jpeg", ".png")) or ("i.redd.it" in url and not url.endswith(".mp4")):
            await update.message.reply_photo(url, caption=title)
        else:
            data = await _download_bytes(url)
            await update.message.reply_video(BytesIO(data), caption=title)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")


async def burnt_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Фоновая задача — постит в чат раз в несколько дней"""
    chat_id = context.job.chat_id
    try:
        url, title = await reddit_burntfood()
        if url.endswith((".jpg", ".jpeg", ".png")) or ("i.redd.it" in url and not url.endswith(".mp4")):
            await context.bot.send_photo(chat_id, url, caption=title)
        else:
            data = await _download_bytes(url)
            await context.bot.send_video(chat_id, BytesIO(data), caption=title)
    except Exception as e:
        await context.bot.send_message(chat_id, f"⚠️ Ошибка: {e}")


async def start_burnt_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда для включения автоматической рассылки"""
    chat_id = update.message.chat_id
    context.job_queue.run_repeating(burnt_job, interval=3 * 24 * 60 * 60, first=10, chat_id=chat_id)
    await update.message.reply_text("✅ Автоматическая рассылка включена (раз в 3 дня).")


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
    app.add_handler(CommandHandler("burnt", send_burnt))
    app.add_handler(CommandHandler("burnt_auto", start_burnt_job))

    await app.initialize()

    try:
        updates = await app.bot.get_updates()
        if updates:
            recent_updates = updates[LAST_UPDATES:]
            for upd in recent_updates:
                await app.process_update(upd)
            last_id = updates[-1].update_id
            await app.bot.get_updates(offset=last_id + 1)
        print("Bot is running...")

        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        try:
            await asyncio.Event().wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
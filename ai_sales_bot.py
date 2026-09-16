import os
import feedparser
import schedule
import time
import telegram
from groq import Groq
from datetime import datetime

# ================= НАСТРОЙКИ =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ================= ИСТОЧНИКИ =================
# RSS-ленты по теме AI + B2B продажи
RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.artificialintelligence-news.com/feed/",
    "https://habr.com/ru/rss/hubs/artificial_intelligence/all/?fl=ru",
    "https://vc.ru/rss/all",
]

# ================= ИИ =================
groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """Ты — редактор Telegram-канала «AI-отдел продаж».
Канал про автоматизацию B2B-продаж с помощью ИИ: кейсы, промпты, инструменты.
Твоя задача: взять новость из мира ИИ и превратить её в полезный пост для канала.

Стиль: энергичный, но без воды. Профессионально, но по-человечески.
Структура поста:
1. Заголовок с эмодзи (1 строка).
2. Суть новости — 2–3 предложения простым языком.
3. Почему это важно для B2B-продаж — 1–2 предложения.
4. Практический совет или вывод — 1 предложение.
5. Финальная строка с хэштегами: #AI #Продажи #Автоматизация

Длина: до 900 символов. Без markdown-звёздочек и ссылок."""


def get_latest_news():
    """Собирает свежие новости из всех RSS-лент, возвращает топ-1."""
    all_news = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")[:500]
                if title:
                    all_news.append({"title": title, "summary": summary})
        except Exception as e:
            print(f"Ошибка с {url}: {e}")
    return all_news


def pick_best_news(news_list):
    """Просим ИИ выбрать самую релевантную новость."""
    if not news_list:
        return None
    news_text = "\n\n".join([f"- {n['title']}\n{n['summary']}" for n in news_list[:20]])
    prompt = f"""Вот список новостей за сегодня. Выбери ОДНУ, самую релевантную для канала про B2B-продажи и ИИ.
Верни её текст в формате:
ЗАГОЛОВОК: ...
ТЕКСТ: ...

Список:
{news_text}"""
    try:
        resp = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Ошибка выбора новости: {e}")
        return None


def generate_post(selected_news):
    """Превращает выбранную новость в пост для канала."""
    try:
        resp = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сделай пост на основе этой новости:\n\n{selected_news}"},
            ],
            temperature=0.7,
            max_tokens=700,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Ошибка генерации поста: {e}")
        return None


def publish():
    """Главный цикл: собрать → выбрать → написать → опубликовать."""
    print(f"\n[{datetime.now()}] Цикл публикации начался")
    news = get_latest_news()
    print(f"Собрано новостей: {len(news)}")
    if not news:
        print("Нет новостей — пропускаем")
        return

    selected = pick_best_news(news)
    if not selected:
        print("Не удалось выбрать новость")
        return

    post = generate_post(selected)
    if not post:
        print("Не удалось сгенерировать пост")
        return

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    try:
        bot.send_message(chat_id=CHANNEL_ID, text=post, parse_mode=None)
        print("✅ Пост опубликован!")
        print("---")
        print(post)
        print("---")
    except Exception as e:
        print(f"Ошибка публикации: {e}")


# ================= РАСПИСАНИЕ =================
# Первая публикация — сразу при запуске
publish()

# Дальше — каждые 6 часов
schedule.every(6).hours.do(publish)

print("\n🚀 Бот запущен. Следующая публикация — через 6 часов.")
print("Не закрывай Termux. Для остановки нажми Ctrl+C.\n")

while True:
    schedule.run_pending()
    time.sleep(60)


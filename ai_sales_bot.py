import os
import feedparser
import schedule
import time
import telegram
import requests
import urllib.parse
from datetime import datetime

# ================= НАСТРОЙКИ (из переменных окружения) =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ================= ИСТОЧНИКИ (российские + мировые) =================
RSS_FEEDS = [
    # Российские
    "https://habr.com/ru/rss/hubs/artificial_intelligence/all/?fl=ru",
    "https://vc.ru/rss/all",
    "https://rb.ru/feeds/all/",
    "https://www.cnews.ru/inc/rss/news.xml",
    # Мировые (для контекста — если новость применима в РФ)
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
]

# ================= ИИ через Groq =================
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"

# ================= ПРОМПТ ДЛЯ ПОСТА =================
SYSTEM_PROMPT = """Ты — редактор Telegram-канала «AI-отдел продаж».
Канал читают российские B2B-предприниматели, руководители отделов продаж и владельцы бизнеса.

Тема канала: автоматизация B2B-продаж с помощью ИИ. Кейсы, промпты, инструменты.

КРИТИЧЕСКИ ВАЖНО:
- Отбирай только новости, применимые в России. Если инструмент недоступен в РФ — упомяни российский аналог или пропусти новость.
- Пиши на русском, без англицизмов, где можно использовать русское слово.
- Не используй ссылки на западные сервисы, которые не работают в РФ (OpenAI, ChatGPT, Claude и т.д. — упоминай только как контекст).

Стиль: энергичный, но без воды. Профессионально, но по-человечески.

Структура поста:
1. Заголовок с эмодзи (1 строка).
2. Суть новости — 2–3 предложения простым языком.
3. Почему это важно для российских B2B-продаж — 1–2 предложения.
4. Практический совет или вывод — 1 предложение.
5. Финальная строка с хэштегами: #AI #Продажи #Автоматизация

Длина: до 900 символов. Без markdown-звёздочек и ссылок."""

# ================= ПРОМПТ ДЛЯ КАРТИНКИ =================
IMAGE_PROMPT_SYSTEM = """Ты — арт-директор Telegram-канала про ИИ и продажи.
На основе поста придумай короткий промпт (на английском) для генерации картинки.

Требования:
- Стиль: современный, минималистичный, деловой, технологичный.
- Без текста на картинке, без логотипов, без лиц людей.
- Абстрактные образы: нейросети, потоки данных, графики, интерфейсы, роботы-помощники.
- Длина промпта: 15–25 слов.
- Только промпт, без объяснений и кавычек.

Пример: futuristic abstract visualization of AI automating sales pipeline, minimalistic blue and purple gradient, geometric shapes, business tech style, 4k"""


def groq_request(messages, temperature=0.7, max_tokens=700):
    """Универсальный запрос к Groq через requests."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        r = requests.post(GROQ_URL, headers=headers, json=data, timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Ошибка Groq: {e}")
        return None


def get_latest_news():
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
    if not news_list:
        return None
    news_text = "\n\n".join([f"- {n['title']}\n{n['summary']}" for n in news_list[:20]])
    prompt = f"""Вот список новостей. Выбери ОДНУ, самую релевантную для российского канала про B2B-продажи и ИИ.

Критерии:
- Тема применима в России (не про сервисы, недоступные в РФ).
- Связана с продажами, автоматизацией, B2B, ИИ-инструментами.
- Свежая и практичная.

Верни её текст в формате:
ЗАГОЛОВОК: ...
ТЕКСТ: ...

Список:
{news_text}"""
    return groq_request(
        [{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=600,
    )


def generate_post(selected_news):
    return groq_request(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Сделай пост на основе этой новости:\n\n{selected_news}"},
        ],
        temperature=0.7,
        max_tokens=700,
    )


def generate_image_url(post_text):
    """Генерирует промпт для картинки и возвращает URL готового изображения."""
    # 1. Просим Groq придумать промпт для картинки
    image_prompt = groq_request(
        [
            {"role": "system", "content": IMAGE_PROMPT_SYSTEM},
            {"role": "user", "content": f"Пост:\n\n{post_text}"},
        ],
        temperature=0.8,
        max_tokens=100,
    )
    if not image_prompt:
        return None

    image_prompt = image_prompt.strip().strip('"').strip("'")
    print(f"Промпт картинки: {image_prompt}")

    # 2. Кодируем и формируем URL для Pollinations AI
    encoded = urllib.parse.quote(image_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=576&nologo=true&seed={int(time.time())}"
    return url


def publish():
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

    image_url = generate_image_url(post)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    try:
        if image_url:
            # Скачиваем картинку, чтобы отправить файлом (надёжнее, чем по URL)
            img_data = requests.get(image_url, timeout=60).content
            bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=img_data,
                caption=post,
            )
            print("✅ Пост с картинкой опубликован!")
        else:
            bot.send_message(chat_id=CHANNEL_ID, text=post)
            print("✅ Пост (без картинки) опубликован!")
        print("---")
        print(post)
        print("---")
    except Exception as e:
        print(f"Ошибка публикации: {e}")


# ================= РАСПИСАНИЕ =================
publish()
schedule.every(6).hours.do(publish)

print("\n🚀 Бот запущен. Следующая публикация — через 6 часов.")
print("Не закрывай Termux. Для остановки нажми Ctrl+C.\n")

while True:
    schedule.run_pending()
    time.sleep(60)

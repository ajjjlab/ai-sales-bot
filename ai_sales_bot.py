import os
import feedparser
import schedule
import time
import telegram
import requests
import urllib.parse
from datetime import datetime

# ================= НАСТРОЙКИ =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ================= ИСТОЧНИКИ =================
RSS_FEEDS = [
    "https://habr.com/ru/rss/hubs/artificial_intelligence/all/?fl=ru",
    "https://vc.ru/rss/all",
    "https://rb.ru/feeds/all/",
    "https://www.cnews.ru/inc/rss/news.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """Ты — автор Telegram-канала «AI-отдел продаж».
Канал читают российские B2B-предприниматели, руководители отделов продаж, владельцы бизнеса.

Тема: автоматизация B2B-продаж с помощью ИИ. Кейсы, промпты, инструменты.

КРИТИЧЕСКИ ВАЖНО:
- Отбирай только новости, применимые в России. Если инструмент недоступен в РФ — упомяни российский аналог или пропусти новость.
- Пиши на русском, живо и по делу. Без англицизмов, где есть русские слова.
- НЕ пересказывай новость сухо. Дай свой взгляд: почему это важно, как применить, что делать.

Стиль: энергичный, экспертный, но по-человечески. Как будто пишешь другу-предпринимателю.

Структура поста:
1. Заголовок с эмодзи (1 строка, цепляющий).
2. Что случилось — 1–2 предложения.
3. Что это значит для российского B2B — 2–3 предложения с конкретикой.
4. Мини-чеклист из 3 пунктов: «Что сделать уже сегодня» (каждый пункт с новой строки, начинается с ✅).
5. Финальная строка: «💾 Сохрани в закладки, чтобы не потерять» — она всегда одинаковая, не меняй её.
6. Хэштеги: #AI #Продажи #Автоматизация

Длина: до 1100 символов. Без markdown-звёздочек и ссылок."""

IMAGE_PROMPT_SYSTEM = """Ты — арт-директор канала про ИИ и продажи.
Придумай короткий промпт (на английском) для генерации картинки к посту.

Требования:
- Стиль: современный, минималистичный, деловой, технологичный.
- Без текста, без логотипов, без лиц людей.
- Абстрактные образы: нейросети, потоки данных, графики, интерфейсы, роботы.
- 15–25 слов. Только промпт, без кавычек и объяснений.

Пример: futuristic abstract visualization of AI automating sales pipeline, minimalistic blue and purple gradient, geometric shapes, business tech style, 4k"""

FALLBACK_IMAGE_PROMPT = "abstract futuristic AI neural network, business technology, blue and purple gradient, minimalist, 4k"


def groq_request(messages, temperature=0.7, max_tokens=800):
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
- Свежая и практичная, есть что обсудить.

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
        temperature=0.8,
        max_tokens=900,
    )


def generate_image_url(post_text):
    image_prompt = groq_request(
        [
            {"role": "system", "content": IMAGE_PROMPT_SYSTEM},
            {"role": "user", "content": f"Пост:\n\n{post_text}"},
        ],
        temperature=0.8,
        max_tokens=100,
    )

    if not image_prompt:
        print("Groq не дал промпт — используем fallback")
        image_prompt = FALLBACK_IMAGE_PROMPT
    else:
        image_prompt = image_prompt.strip().strip('"').strip("'")

    print(f"Промпт картинки: {image_prompt}")
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
            img_data = requests.get(image_url, timeout=90).content
            if len(post) <= 1024:
                bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=img_data,
                    caption=post,
                )
                print("✅ Пост с картинкой опубликован!")
            else:
                bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=img_data,
                )
                bot.send_message(chat_id=CHANNEL_ID, text=post)
                print(f"✅ Пост с картинкой + текстом опубликован (длина: {len(post)})")
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
print("Для остановки нажми Ctrl+C.\n")

while True:
    schedule.run_pending()
    time.sleep(60)

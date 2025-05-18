import os
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from dotenv import load_dotenv
from functools import lru_cache
import logging

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения из файла .env
load_dotenv()

# Получение API-ключей из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OMDB_API_KEY = os.getenv('OMDB_API_KEY')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
GOOGLE_BOOKS_API_KEY = os.getenv('GOOGLE_BOOKS_API_KEY')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

# Проверка наличия всех ключей
if not all([TELEGRAM_BOT_TOKEN, OMDB_API_KEY, TMDB_API_KEY, GOOGLE_BOOKS_API_KEY, MISTRAL_API_KEY]):
    logger.error("Не все необходимые переменные окружения установлены.")
    exit(1)

# Базовый URL для изображений TMDb
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

# Функция для отправки запроса к модели Mistral
def get_mistral_response(prompt):
    try:
        url = "https://api.mistral.ai/v1/chat/completions"  # Замените на реальный URL Mistral API, если он отличается
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "pixtral-12b-2409",  # Используем правильное название модели Pixtral
            "messages": [
                {"role": "system", "content": "Вы являетесь помощником, который предоставляет рекомендации по фильмам, сериалам и книгам."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,  # Увеличим максимальное количество токенов
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=data, timeout=30)  # Увеличим таймаут до 30 секунд
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP ошибка при запросе к Mistral API: {e}")
        logger.error(f"Ответ от сервера: {response.text}")  # Добавляем вывод ответа сервера для отладки
        return "Произошла ошибка при обработке запроса. Попробуйте снова позже."
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Mistral API: {e}")
        return "Произошла ошибка при обработке запроса. Попробуйте снова позже."
    except KeyError as e:
        logger.error(f"Ошибка в ответе от Mistral API: {e}")
        logger.error(f"Ответ от сервера: {response.text}")  # Добавляем вывод ответа сервера для отладки
        return "Произошла ошибка в ответе от Mistral API. Попробуйте снова позже."

# Функция для получения рекомендаций с OMDb API
@lru_cache(maxsize=128)
def get_recommendations_omdb(query):
    try:
        url = f"http://www.omdbapi.com/?s={query}&apikey={OMDB_API_KEY}"
        response = requests.get(url, timeout=30)  # Увеличим таймаут до 30 секунд
        response.raise_for_status()
        data = response.json()
        if data.get('Response') == 'True':
            results = data.get('Search', [])
            recommendations = []
            media = []
            for item in results:
                title = item.get('Title', 'Название не указано')
                year = item.get('Year', 'Год выпуска не указан')
                poster_url = item.get('Poster', None)
                recommendations.append(f"{title} ({year})")
                if poster_url and poster_url != "N/A":
                    media.append((poster_url, f"{title} ({year})"))
            return "\n".join(recommendations), media
        else:
            return "Извините, ничего не найдено.", []
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к OMDb API: {e}")
        return "Произошла ошибка при получении данных. Попробуйте снова позже.", []

# Функция для получения рекомендаций с TMDb API
@lru_cache(maxsize=128)
def get_recommendations_tmdb(query):
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&language=ru-RU&query={query}&page=1&include_adult=false"
        response = requests.get(url, timeout=30)  # Увеличим таймаут до 30 секунд
        response.raise_for_status()
        data = response.json()
        if data.get('results'):
            results = data.get('results', [])
            recommendations = []
            media = []
            for item in results:
                if item.get('media_type') == 'movie':
                    title = item.get('title', 'Название не указано')
                    release_date = item.get('release_date', 'Год выпуска не указан')
                    poster_path = item.get('poster_path', None)
                    recommendations.append(f"Фильм: {title} ({release_date.split('-')[0] if release_date else 'Год выпуска не указан'})")
                    if poster_path:
                        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
                        media.append((poster_url, f"Фильм: {title} ({release_date.split('-')[0] if release_date else 'Год выпуска не указан'})"))
                elif item.get('media_type') == 'tv':
                    name = item.get('name', 'Название не указано')
                    first_air_date = item.get('first_air_date', 'Год выпуска не указан')
                    poster_path = item.get('poster_path', None)
                    recommendations.append(f"Сериал: {name} ({first_air_date.split('-')[0] if first_air_date else 'Год выпуска не указан'})")
                    if poster_path:
                        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
                        media.append((poster_url, f"Сериал: {name} ({first_air_date.split('-')[0] if first_air_date else 'Год выпуска не указан'})"))
            return "\n".join(recommendations), media
        else:
            return "Извините, ничего не найдено.", []
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к TMDb API: {e}")
        return "Произошла ошибка при получении данных. Попробуйте снова позже.", []

# Функция для получения рекомендаций с Google Books API
@lru_cache(maxsize=128)
def get_recommendations_books(query):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&key={GOOGLE_BOOKS_API_KEY}&langRestrict=ru"
        response = requests.get(url, timeout=30)  # Увеличим таймаут до 30 секунд
        response.raise_for_status()
        data = response.json()
        if data.get('items'):
            results = data.get('items', [])
            recommendations = []
            media = []
            for item in results:
                volume_info = item.get('volumeInfo', {})
                title = volume_info.get('title', 'Название не указано')
                authors = ', '.join(volume_info.get('authors', ['Автор не указан'])) if volume_info.get('authors') else 'Автор не указан'
                published_date = volume_info.get('publishedDate', 'Год издания не указан')
                image_links = volume_info.get('imageLinks', {})
                thumbnail_url = image_links.get('thumbnail', None)
                recommendations.append(f"Книга: {title} ({published_date}) - Авторы: {authors}")
                if thumbnail_url:
                    media.append((thumbnail_url, f"Книга: {title} ({published_date}) - Авторы: {authors}"))
            return "\n".join(recommendations), media
        else:
            return "Извините, ничего не найдено.", []
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Google Books API: {e}")
        return "Произошла ошибка при получении данных. Попробуйте снова позже.", []

# Обработчик команды /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Привет! Я твой новый друг и я могу помочь тебе с выбором сериала, фильма и даже аниме . Что тебя интересует ? ')

# Функция для разделения длинных сообщений
def split_message(message, max_length=4096):
    parts = []
    while message:
        if len(message) <= max_length:
            parts.append(message)
            break
        part = message[:max_length]
        last_newline = part.rfind('\n')
        if last_newline != -1:
            part = part[:last_newline]
        parts.append(part)
        message = message[len(part):]
    return parts

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    if "рекомендации" in user_message.lower():
        query = user_message.replace("рекомендации", "").strip()
        if not query:
            await update.message.reply_text("Пожалуйста, укажите, что вы хотите найти (например, рекомендации фильмы).")
            return

        recommendations_omdb, media_omdb = get_recommendations_omdb(query)
        recommendations_tmdb, media_tmdb = get_recommendations_tmdb(query)
        recommendations_books, media_books = get_recommendations_books(query)

        response = ""
        media = []

        if recommendations_omdb:
            response += f"Рекомендации с OMDb API:\n{recommendations_omdb}\n\n"
            media.extend(media_omdb)
        if recommendations_tmdb:
            response += f"Рекомендации с TMDb API:\n{recommendations_tmdb}\n\n"
            media.extend(media_tmdb)
        if recommendations_books:
            response += f"Рекомендации с Google Books API:\n{recommendations_books}\n\n"
            media.extend(media_books)

        if response:
            parts = split_message(response)
            for part in parts:
                await update.message.reply_text(part)

            if media:
                for poster_url, caption in media:
                    try:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
                        }
                        response = requests.get(poster_url, headers=headers, timeout=30)
                        response.raise_for_status()
                        await update.message.reply_photo(photo=response.content, caption=caption)
                    except requests.exceptions.HTTPError as e:
                        logger.error(f"HTTP ошибка при запросе изображения: {e}")
                        await update.message.reply_text(f"Не удалось отправить постер: {caption}. Попробуйте снова позже.")
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Ошибка при запросе изображения: {e}")
                        await update.message.reply_text(f"Не удалось отправить постер: {caption}. Попробуйте снова позже.")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке изображения: {e}")
                        await update.message.reply_text(f"Не удалось отправить постер: {caption}. Попробуйте снова позже.")
        else:
            await update.message.reply_text("Извините, ничего не найдено.")
    else:
        mistral_response = get_mistral_response(user_message)
        parts = split_message(mistral_response)
        for part in parts:
            await update.message.reply_text(part)

# Обработчик ошибок
async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before handling it.
    logger.error(f"Произошла ошибка: {context.error}")
    # Notify the developer
    if isinstance(update, Update):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка при обработке запроса. Попробуйте снова позже.")

def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
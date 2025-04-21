import logging
import os
import re
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from yt_dlp import YoutubeDL

# Ваш API токен для Telegram
TELEGRAM_TOKEN = '7172553910:AAFnuMN1b6eXa0MOkvsu1oQvsGmbIS_K53I'

# Путь к папке для хранения скачанных файлов
DOWNLOAD_DIR = '/tmp/downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """
    Очистка имени файла от небезопасных символов.
    """
    # Заменяем слеши и другие специальные символы на подчеркивание
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! Отправь мне название песни или исполнителя, и я найду её для тебя.')

async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text('Пожалуйста, введите название песни или исполнителя.')
        return

    try:
        await update.message.reply_text('Ищу музыку, пожалуйста, подождите...')
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'extract_flat': True,  # Avoid downloading the video
            'quiet': True,         # Reduce output
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)  # Fetch multiple results
            entries = info.get('entries', [])

        if not entries:
            await update.message.reply_text('Ничего не найдено.')
            return

        # Send the list of search results
        buttons = []
        for index, entry in enumerate(entries[:3]):  # Limit to the first 3 results
            title = entry.get('title', 'Unknown title')
            button_text = f"{index + 1}. {title}"
            # Limit button text to avoid Telegram API errors
            if len(button_text) > 60:
                button_text = button_text[:57] + "..."
            # В данных callback у Telegram есть ограничение на размер
            # Поэтому используем ID видео вместо полного URL
            video_id = entry.get('id', '')
            buttons.append((button_text, video_id))

        # Create inline keyboard
        keyboard = [[InlineKeyboardButton(text=btn[0], callback_data=btn[1])] for btn in buttons]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Выберите один из вариантов:', reply_markup=reply_markup)

    except Exception as e:
        logger.error(f'Error during search: {e}')
        await update.message.reply_text(f'Произошла ошибка при поиске: {str(e)}')

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    video_id = query.data

    if not video_id:
        await query.edit_message_text(text="Выбор недействителен.")
        return

    try:
        await query.edit_message_text(text="Скачиваю и конвертирую файл, это может занять некоторое время...")
        
        # Получаем полный URL из ID видео
        song_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Generate a unique filename to avoid conflicts
        unique_filename = str(uuid.uuid4())
        temp_file_path = os.path.join(DOWNLOAD_DIR, f"{unique_filename}.webm")

        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'outtmpl': temp_file_path,
            'quiet': True,  # Снижаем вывод для экономии ресурсов
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(song_url, download=True)

        # Rename the downloaded file
        original_title = info['title']
        sanitized_title = sanitize_filename(original_title)
        downloaded_file_path = temp_file_path.replace('.webm', '.mp3')
        new_file_path = os.path.join(DOWNLOAD_DIR, f"{sanitized_title}.mp3")

        if os.path.exists(downloaded_file_path):
            os.rename(downloaded_file_path, new_file_path)
            logger.info(f'Renamed file: {downloaded_file_path} to {new_file_path}')
        else:
            logger.warning(f'File to rename not found: {downloaded_file_path}')
            new_file_path = downloaded_file_path  # fallback to downloaded file path if renaming failed

        # Check if file exists
        if not os.path.exists(new_file_path):
            await query.edit_message_text(text='Ошибка при скачивании или конвертации файла.')
            logger.error(f'File does not exist after renaming: {new_file_path}')
            return

        # Send the mp3 file
        await query.edit_message_text(text=f"Отправляю трек: {original_title}")
        with open(new_file_path, 'rb') as mp3_file:
            await query.message.reply_document(document=InputFile(mp3_file, filename=f'{sanitized_title}.mp3'))
            
        # Отправляем сообщение об успехе
        await query.message.reply_text("✅ Трек отправлен!")

        # Remove the mp3 file after sending to save space
        os.remove(new_file_path)
        logger.info(f'File sent and deleted: {new_file_path}')

    except Exception as e:
        logger.error(f'Error during file handling: {e}', exc_info=True)
        await query.edit_message_text(text=f'Произошла ошибка при отправке файла. Попробуйте другой трек.')

def main():
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))
        application.add_handler(CallbackQueryHandler(button))

        # Запускаем бота до прерывания
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)

if __name__ == '__main__':
    main()

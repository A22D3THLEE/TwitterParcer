import asyncio
import logging
import pickle
import json
import os
import random
import time
import tempfile
import shutil
import requests
from datetime import datetime, timedelta
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from aiogram import Bot
from aiogram.types import InputFile
from selenium.common.exceptions import TimeoutException
import yt_dlp
import ffmpeg

# Настройка логирования с явной поддержкой UTF-8
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ],
    encoding="utf-8"
)
logging.info("Скрипт запущен")

# Конфигурация
TELEGRAM_BOT_TOKEN = "7605069590:AAECOU7H3OFoVj6HwUfEQKAkXj7A6KWvsqI"
TELEGRAM_CHANNEL_ID = "@xwitter_rss"
TWITTER_ACCOUNTS = [
    "IntEngineering", "dexerto", "openai", "krea_ai", "huggingface", "CultureCrave", "grok",
    "PsyPost", "perplexity_ai", "sama", "satyanadella", "github", "deepseek_ai",
    "DiscussingFilm", "IGN", "testingcatalog", "kimmonismus", "HYPEX", "alliekmiller",
    "wccftech", "D_S_O_Gaming", "cognition_labs", "gdb", "TechCrunch", "alliekmiller",
    "netflix", "Alibaba_Qwen", "FLScience", "BrandonLuuMD", "Steam", "Dr_Singularity",
    "PlayAIOfficial", "freepik", "thegameawards", "digitalfoundry", "RinoTheBouncer",
    "InsiderGamingIG", "_Tom_Henderson_", "tomwarren", "billbil_kun", "florafaunaai",
    "elevenlabsio", "AiBreakfast", "GameSpot", "engadget", "dr_cintas", "LumaLabsAI", "pika_labs",
    "Kling_ai", "arstechnica", "LumaLabsAI", "higgsfield_ai", "Aurelien_Gz", "godofprompt",
    "GoogleWorkspace", "GeminiApp", "PromptLLM", "CNET", "DigitalTrends", "pcworld",
    "techhalla", "WIRED", "WIREDScience", "Computerworld", "techradar", "Gizmodo", "PCMag",
    "techreview", "TechRepublic", "Kurakasis", "trendwatching", "tomshardware", "hasantoxr", "devolverdigital", "AIWarper", "charlieINTEL", "IntEngineering",
]
LAST_POSTED_FILE = 'last_posted_twitter.json'
COOKIES_FILES = ['twitter_cookies_1.pkl', 'twitter_cookies_2.pkl', 'twitter_cookies_3.pkl']
PROBLEMATIC_ACCOUNTS_FILE = 'problematic_accounts.json'

PARSING_INTERVAL = 180
MESSAGE_DELAY = 3
TIMEOUT = 30
FULL_CYCLE_DELAY = 300
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 ГБ - лимит Telegram

current_cookies_index = 0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
]

logging.info("Настройка undetected-chromedriver")
options = uc.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")
options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
options.add_argument("--disable-extensions")
options.add_argument("--disable-sync")

# Указываем путь к профилю
profile_dir = "/opt/chrome_profiles"
if os.path.exists(profile_dir):
    shutil.rmtree(profile_dir, ignore_errors=True)
os.makedirs(profile_dir, exist_ok=True)
os.chmod(profile_dir, 0o777)
options.add_argument(f"--user-data-dir={profile_dir}")

try:
    driver = uc.Chrome(options=options)
    logging.info("undetected-chromedriver успешно настроен")
except Exception as e:
    logging.error(f"Не удалось настроить undetected-chromedriver: {e}")
    raise

logging.info("Инициализация Telegram бота")
bot = Bot(token=TELEGRAM_BOT_TOKEN)
logging.info("Telegram бот инициализирован")

def switch_to_next_cookies():
    """Переключение на следующий файл cookies"""
    global current_cookies_index
    current_cookies_index = (current_cookies_index + 1) % len(COOKIES_FILES)
    logging.info(f"Переключено на файл cookies: {COOKIES_FILES[current_cookies_index]}")
    return COOKIES_FILES[current_cookies_index]

def load_cookies(cookies_file):
    """Загрузка только ct0 и auth_token из файла cookies"""
    if os.path.exists(cookies_file):
        driver.get("https://x.com")
        with open(cookies_file, 'rb') as f:
            cookies = pickle.load(f)
        
        essential_cookies = [cookie for cookie in cookies if cookie['name'] in ['ct0', 'auth_token']]
        
        if not essential_cookies:
            logging.error(f"В файле {cookies_file} отсутствуют ct0 или auth_token")
            return False
        
        for cookie in essential_cookies:
            logging.info(f"Загрузка cookie: {cookie['name']} = {cookie['value']}")
            driver.add_cookie(cookie)
        
        logging.info(f"Основные cookies (ct0 и auth_token) успешно загружены из {cookies_file}")
        driver.refresh()
        time.sleep(5)
        return True
    else:
        logging.error(f"Файл cookies {cookies_file} не найден")
        return False

def load_problematic_accounts():
    """Загрузка списка проблемных аккаунтов"""
    if os.path.exists(PROBLEMATIC_ACCOUNTS_FILE):
        with open(PROBLEMATIC_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_problematic_accounts(problematic_accounts):
    """Сохранение списка проблемных аккаунтов"""
    with open(PROBLEMATIC_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(problematic_accounts, f, ensure_ascii=False, indent=2)

def reencode_video(input_path):
    """Перекодирование видео (оставлено для возможного использования в будущем)"""
    logging.warning("Функция reencode_video не используется, так как ограничения на размер видео сняты")
    return input_path

def download_video_with_ytdlp(tweet_url):
    """Скачивание видео с помощью yt-dlp без ограничений на размер"""
    try:
        # Настройки для yt-dlp
        ydl_opts = {
            'outtmpl': os.path.join(tempfile.gettempdir(), 'tweet_video_%(id)s.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Извлекаем информацию о видео
            info = ydl.extract_info(tweet_url, download=False)
            if not info:
                logging.error("Не удалось извлечь информацию о видео")
                return None

            # Скачиваем видео
            ydl.download([tweet_url])
            video_file_path = ydl.prepare_filename(info)

            # Проверяем, существует ли файл после скачивания
            if not os.path.exists(video_file_path):
                logging.error("Видео не было скачано: файл не найден")
                return None

            actual_size = os.path.getsize(video_file_path)
            logging.info(f"Видео скачано: {video_file_path}, размер: {actual_size} байт")

            return video_file_path

    except Exception as e:
        logging.error(f"Ошибка при скачивании видео с yt-dlp: {str(e)}")
        return None

def extract_media(post, username, tweet_url):
    """Извлечение медиа (изображений и видео) из поста"""
    image_urls = []
    has_video = False
    video_file_path = None

    try:
        # Извлечение изображений
        image_elements = post.find_all("img")
        for img in image_elements:
            img_url = None
            if "src" in img.attrs and "media" in img["src"]:
                img_url = img["src"]
            elif "srcset" in img.attrs:
                srcset = img["srcset"].split(",")[0].split(" ")[0]
                if "media" in srcset:
                    img_url = srcset
            
            if img_url:
                if "format=" in img_url:
                    base_url = img_url.split("?")[0]
                    img_url = f"{base_url}?format=jpg&name=large"
                else:
                    if not img_url.startswith("http"):
                        img_url = f"https://x.com{img_url}"
                    img_url = f"{img_url}?format=jpg&name=large"
                image_urls.append(img_url)
                logging.info(f"Извлечён URL изображения: {img_url}")

        # Проверка наличия видео и попытка его скачивания
        video_elements = post.find_all("video")
        has_video = len(video_elements) > 0
        if has_video:
            logging.info(f"Обнаружено видео для {username}, пытаемся скачать с помощью yt-dlp")
            video_file_path = download_video_with_ytdlp(tweet_url)
            if video_file_path:
                logging.info(f"Видео успешно скачано для {username}: {video_file_path}")
            else:
                logging.warning(f"Не удалось скачать видео для {username}, будет отправлена ссылка")

    except Exception as e:
        logging.error(f"Ошибка при извлечении медиа для {username}: {str(e)}")

    return image_urls, has_video, video_file_path

class FeedState:
    def __init__(self):
        self.last_timestamps = self.load_state()

    def load_state(self):
        """Загружаем состояние последней временной метки для каждого аккаунта"""
        if os.path.exists(LAST_POSTED_FILE):
            try:
                with open(LAST_POSTED_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and all(
                        isinstance(v, str) for v in data.values()
                    ):
                        logging.info("JSON состояние успешно загружено")
                        return data
                    else:
                        logging.warning("Неверная структура JSON состояния, сброс состояния")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logging.error(f"Ошибка загрузки JSON состояния: {e}, сброс состояния")
        logging.info("Создание нового пустого состояния")
        new_state = {account: "" for account in TWITTER_ACCOUNTS}
        self.save_state(new_state=new_state)
        return new_state

    def save_state(self, username=None, timestamp=None, new_state=None):
        """Сохраняем состояние: либо для одного аккаунта, либо полностью"""
        try:
            if new_state is not None:
                with open(LAST_POSTED_FILE, "w", encoding="utf-8") as f:
                    json.dump(new_state, f, ensure_ascii=False, indent=2)
                logging.info("Сохранено начальное состояние для всех аккаунтов")
                self.last_timestamps = new_state
            elif username and timestamp:
                if os.path.exists(LAST_POSTED_FILE):
                    with open(LAST_POSTED_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {account: "" for account in TWITTER_ACCOUNTS}

                data[username] = timestamp
                with open(LAST_POSTED_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logging.info(f"Сохранена временная метка для {username}: {timestamp}")
                self.last_timestamps[username] = timestamp
            else:
                raise ValueError("Должны быть указаны либо new_state, либо username и timestamp")
        except Exception as e:
            logging.error(f"Ошибка сохранения состояния: {e}")
            raise

def fetch_latest_tweet(username, problematic_accounts, state):
    """Получаем самый новый незакреплённый пост (без прокрутки) для указанного аккаунта"""
    attempts_made = 0

    while attempts_made < len(COOKIES_FILES):
        try:
            logging.info(f"Загрузка страницы для {username} (попытка {attempts_made + 1}/{len(COOKIES_FILES)} с {COOKIES_FILES[current_cookies_index]})")
            
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": random.choice(USER_AGENTS)})
            driver.get(f"https://x.com/{username}")

            try:
                WebDriverWait(driver, TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet'], article div[data-testid='tweetText']"))
                )
                logging.info(f"Элементы постов найдены для {username}")
            except TimeoutException as e:
                logging.warning(f"Элементы постов не найдены для {username}: {e}")
                soup = BeautifulSoup(driver.page_source, "html.parser")
                page_source_lower = driver.page_source.lower()
                if "captcha" in page_source_lower:
                    logging.error(f"Обнаружена CAPTCHA для {username}")
                    skip_until = (datetime.now(pytz.UTC) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S%z")
                    problematic_accounts[username] = {"skip_until": skip_until}
                    save_problematic_accounts(problematic_accounts)
                elif "you've reached your view limit" in page_source_lower or "rate limit exceeded" in page_source_lower:
                    logging.error(f"Достигнут лимит просмотров для текущего аккаунта при загрузке {username}")
                elif not soup.find("body"):
                    logging.error(f"Пустая страница возвращена для {username}")
                else:
                    logging.info(f"Страница загружена, но элементы постов не найдены для {username}")
                
                cookies_file = switch_to_next_cookies()
                load_cookies(cookies_file)
                attempts_made += 1
                time.sleep(5 + random.uniform(1, 3))
                continue

            soup = BeautifulSoup(driver.page_source, "html.parser")
            posts = soup.find_all("article", {"data-testid": "tweet"})
            logging.info(f"Найдено {len(posts)} постов для {username}")

            if not posts:
                logging.info(f"Посты не найдены для {username}")
                return None

            # Ищем самый новый незакреплённый пост
            latest_post = None
            latest_published = None
            current_time = datetime.now(pytz.UTC)

            for post in posts[:5]:
                try:
                    # Проверяем, закреплён ли пост
                    social_context = post.find("span", {"data-testid": "socialContext"})
                    is_pinned = False
                    if social_context:
                        social_text = social_context.get_text().lower()
                        if "pinned" in social_text or "закреплённый" in social_text:
                            logging.info(f"Пропущен закреплённый пост для {username} (socialContext)")
                            is_pinned = True
                    
                    # Дополнительная проверка на наличие иконки закреплённого поста
                    pin_icon = post.find("svg", {"aria-label": "Pinned Tweet"})
                    if pin_icon:
                        logging.info(f"Пропущен закреплённый пост для {username} (pin icon)")
                        is_pinned = True

                    if is_pinned:
                        continue

                    text_element = post.find("div", {"data-testid": "tweetText"})
                    text = text_element.get_text(strip=True) if text_element else "Без текста"
                    text = text.encode('utf-8', 'replace').decode('utf-8')

                    retweet_info = post.find("span", {"data-testid": "socialContext"})
                    if retweet_info and not ("pinned" in retweet_info.get_text().lower() or "закреплённый" in retweet_info.get_text().lower()):
                        retweet_text = retweet_info.get_text(strip=True)
                        retweet_text = retweet_text.encode('utf-8', 'replace').decode('utf-8')
                        text = f"{retweet_text} {text}"

                    time_element = post.find("time")
                    if not time_element:
                        logging.debug(f"Нет временного элемента для поста в {username}")
                        continue

                    tweet_link = time_element.find_parent("a")["href"]
                    tweet_url = f"https://x.com{tweet_link}"
                    datetime_str = time_element["datetime"]
                    published = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)

                    # Если пост старше 7 дней, считаем его закреплённым
                    if published < current_time - timedelta(days=7):
                        logging.info(f"Пропущен пост для {username}, слишком старый (возможно закреплённый): {published}")
                        continue

                    if "/status/" in tweet_url:
                        reply_to = post.find("a", href=lambda x: x and "/status/" in x and "in_reply_to" in x)
                        if reply_to:
                            reply_to_user = reply_to["href"].split("/")[1]
                            text = f"Ответ на @{reply_to_user}: {text}"

                    # Сравниваем временные метки, чтобы найти самый новый пост
                    if latest_published is None or published > latest_published:
                        latest_published = published
                        latest_post = {
                            "text": text,
                            "link": tweet_url,
                            "published": published.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            "post_element": post  # Сохраняем элемент поста для извлечения медиа позже
                        }

                except Exception as e:
                    logging.error(f"Ошибка при парсинге поста для {username}: {str(e)}")
                    continue

            if latest_post is None:
                logging.info(f"Не найдено незакреплённых постов для {username}")
                return None

            # Проверяем, не старше ли пост текущей даты
            if latest_published < current_time - timedelta(days=1):
                logging.info(f"Пост для {username} слишком старый: {latest_published}, пропуск")
                return None

            # Сравниваем временную метку с сохранённой
            saved_timestamp = state.last_timestamps.get(username, "")
            saved_published = None
            if saved_timestamp:
                try:
                    saved_published = datetime.strptime(saved_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=pytz.UTC)
                    logging.info(f"Сохранённое время для {username}: {saved_published}")
                except ValueError:
                    logging.warning(f"Неверный формат сохранённой даты для {username}, обработка как новый твит")
                    saved_published = None

            if saved_published is not None and latest_published <= saved_published:
                logging.info(f"Нет новых твитов для {username}: {latest_post['text'][:50]}... в {latest_post['published']}")
                return None

            # Если пост новый, извлекаем медиа
            logging.info(f"Обнаружен новый твит для {username}: {latest_post['text'][:50]}... в {latest_post['published']}")
            image_urls, has_video, video_file_path = extract_media(latest_post["post_element"], username, latest_post["link"])
            latest_post["images"] = image_urls
            latest_post["has_video"] = has_video
            latest_post["video_file_path"] = video_file_path
            del latest_post["post_element"]  # Удаляем временное поле

            if username in problematic_accounts:
                del problematic_accounts[username]
                save_problematic_accounts(problematic_accounts)

            return latest_post

        except Exception as e:
            logging.error(f"Ошибка при загрузке страницы для {username}: {str(e)}")
            cookies_file = switch_to_next_cookies()
            load_cookies(cookies_file)
            attempts_made += 1
            time.sleep(5 + random.uniform(1, 3))
            continue

    logging.warning(f"Все файлы cookies были использованы для {username}. Ожидание {FULL_CYCLE_DELAY} секунд перед повторной попыткой...")
    time.sleep(FULL_CYCLE_DELAY)
    return None

async def send_telegram_message(post_data, show_preview=True):
    """Асинхронная отправка сообщения в Telegram с медиа"""
    try:
        # Санитизируем текст сообщения
        text = post_data['text'].encode('utf-8', 'replace').decode('utf-8')
        link = post_data['link'].encode('utf-8', 'replace').decode('utf-8')
        message = f"<b>{text}</b>\n{link}"
        images = post_data.get("images", [])
        has_video = post_data.get("has_video", False)
        video_file_path = post_data.get("video_file_path", None)
        media_sent = False

        # Проверяем, удалось ли скачать видео
        if has_video and video_file_path:
            try:
                video_size = os.path.getsize(video_file_path)
                if video_size > MAX_FILE_SIZE:
                    logging.error(f"Видео слишком большое для Telegram: {video_size} байт, лимит {MAX_FILE_SIZE} байт")
                    message += "\n(Видео слишком большое для Telegram, используйте ссылку для просмотра)"
                else:
                    await bot.send_video(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        video=InputFile(video_file_path),
                        caption=message,
                        parse_mode="HTML"
                    )
                    logging.info(f"Отправлено видео для поста: {message[:50]}...")
                    media_sent = True
                # Удаляем временный файл после отправки
                os.unlink(video_file_path)
                await asyncio.sleep(MESSAGE_DELAY + random.uniform(1, 2))
                if media_sent:
                    return
            except Exception as e:
                logging.error(f"Ошибка при отправке видео: {str(e)}")
                # Удаляем временный файл в случае ошибки
                if os.path.exists(video_file_path):
                    os.unlink(video_file_path)
                message += "\n(Видео не удалось отправить, используйте ссылку для просмотра)"

        # Если видео не удалось скачать, добавляем уведомление
        if has_video and not video_file_path:
            message += "\n(Видео не удалось скачать, используйте ссылку для просмотра)"

        if images and not media_sent:
            for img_url in images:
                try:
                    headers = {"User-Agent": random.choice(USER_AGENTS)}
                    # Проверяем размер файла через HEAD-запрос
                    head_response = requests.head(img_url, headers=headers, allow_redirects=True)
                    content_length = int(head_response.headers.get("content-length", 0))
                    if content_length == 0:
                        logging.warning(f"Не удалось определить размер изображения {img_url}, пробуем загрузить")
                    elif content_length > MAX_FILE_SIZE:
                        logging.error(f"Изображение {img_url} слишком большое: {content_length} байт, лимит {MAX_FILE_SIZE} байт")
                        continue

                    # Загружаем изображение
                    response = requests.get(img_url, headers=headers, stream=True, timeout=10)
                    if response.status_code != 200:
                        logging.error(f"Не удалось скачать изображение {img_url}: статус {response.status_code}")
                        continue

                    # Дополнительная проверка размера после загрузки
                    content_length = int(response.headers.get("content-length", 0))
                    if content_length > MAX_FILE_SIZE:
                        logging.error(f"Изображение {img_url} слишком большое после загрузки: {content_length} байт, лимит {MAX_FILE_SIZE} байт")
                        continue

                    await bot.send_photo(
                        chat_id=TELEGRAM_CHANNEL_ID,
                        photo=InputFile(response.raw),
                        caption=message,
                        parse_mode="HTML"
                    )
                    logging.info(f"Отправлено изображение для поста: {message[:50]}... URL: {img_url}, размер: {content_length} байт")
                    media_sent = True
                    await asyncio.sleep(MESSAGE_DELAY + random.uniform(1, 2))
                    return
                except requests.exceptions.RequestException as e:
                    logging.error(f"Ошибка загрузки изображения {img_url}: {str(e)}")
                    continue
                except Exception as e:
                    logging.error(f"Ошибка при отправке изображения {img_url}: {str(e)}")
                    continue

        # Если медиа отправить не удалось, отправляем только текст
        if not media_sent:
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=message,
                parse_mode="HTML",
                disable_web_page_preview=not show_preview
            )
            logging.info(f"Медиа отправить не удалось, отправлено текстовое сообщение: {message[:50]}...")
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {str(e)}")
        # Удаляем временный файл, если он остался
        if video_file_path and os.path.exists(video_file_path):
            os.unlink(video_file_path)
        raise
    finally:
        await asyncio.sleep(MESSAGE_DELAY + random.uniform(1, 2))

async def parse_twitter(state):
    """Последовательный парсинг твитов для всех аккаунтов с немедленной отправкой"""
    logging.info("Начало парсинга Twitter")
    problematic_accounts = load_problematic_accounts()

    for username in TWITTER_ACCOUNTS:
        if username in problematic_accounts:
            skip_until = problematic_accounts.get(username, {}).get("skip_until")
            if skip_until and datetime.now(pytz.UTC) < datetime.strptime(skip_until, "%Y-%m-%d %H:%M:%S%z"):
                logging.info(f"Пропуск {username} из-за предыдущей CAPTCHA, повторная попытка после {skip_until}")
                continue

        latest_tweet = fetch_latest_tweet(username, problematic_accounts, state)
        if latest_tweet is None:
            logging.info(f"Нет новых данных о твитах для {username}, пропуск")
            continue

        # Если твит новый, отправляем его и обновляем состояние
        await send_telegram_message(latest_tweet)
        state.save_state(username=username, timestamp=latest_tweet["published"])

    logging.info("Парсинг Twitter завершён")

async def check_session():
    """Проверка активности сессии"""
    attempts_made = 0

    while attempts_made < len(COOKIES_FILES):
        try:
            driver.get("https://x.com")
            await asyncio.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            page_source_lower = driver.page_source.lower()
            if "login" in driver.current_url.lower() or soup.find("input", {"name": "session[username_or_email]"}):
                logging.error("Сессия неактивна: обнаружена страница логина")

            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-testid='tweet']"))
            )
            logging.info("Сессия активна: твиты найдены на главной странице")
            return True

        except TimeoutException as e:
            logging.error(f"Проверка сессии не удалась: твиты не найдены на главной странице: {str(e)}")
            soup = BeautifulSoup(driver.page_source, "html.parser")
            page_source_lower = driver.page_source.lower()
            if "captcha" in page_source_lower:
                logging.error("Обнаружена CAPTCHA при проверке сессии")
            elif "you've reached your view limit" in page_source_lower or "rate limit exceeded" in page_source_lower:
                logging.error("Достигнут лимит просмотров для текущего аккаунта при проверке сессии")
            else:
                logging.error("Сессия неактивна: неизвестная ошибка")

            cookies_file = switch_to_next_cookies()
            load_cookies(cookies_file)
            attempts_made += 1
            await asyncio.sleep(5 + random.uniform(1, 3))
            continue

        except Exception as e:
            logging.error(f"Ошибка при проверке сессии: {str(e)}")
            cookies_file = switch_to_next_cookies()
            load_cookies(cookies_file)
            attempts_made += 1
            await asyncio.sleep(5 + random.uniform(1, 3))
            continue

    logging.warning(f"Все файлы cookies были использованы при проверке сессии. Ожидание {FULL_CYCLE_DELAY} секунд перед повторной попыткой...")
    await asyncio.sleep(FULL_CYCLE_DELAY)
    return False

async def main():
    logging.info("Запуск основной функции")
    state = FeedState()
    try:
        if not load_cookies(COOKIES_FILES[current_cookies_index]):
            raise Exception(f"Файл cookies {COOKIES_FILES[current_cookies_index]} не найден или отсутствуют основные cookies (ct0, auth_token). Пожалуйста, обновите cookies.")

        if not await check_session():
            raise Exception("Сессия неактивна после попытки использования всех файлов cookies. Пожалуйста, обновите cookies.")

        while True:
            await parse_twitter(state)
            logging.info(f"Ожидание {PARSING_INTERVAL} секунд до следующего парсинга")
            await asyncio.sleep(PARSING_INTERVAL + random.uniform(30, 60))
    except Exception as e:
        logging.error(f"Ошибка в основном цикле: {str(e)}")
        raise
    finally:
        driver.quit()
        try:
            shutil.rmtree(temp_profile_dir)
            logging.info(f"Временный профиль {temp_profile_dir} удалён")
        except Exception as e:
            logging.error(f"Ошибка при удалении временного профиля: {str(e)}")

if __name__ == "__main__":
    logging.info("Запуск бота")
    asyncio.run(main())

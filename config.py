import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = "8546123786:AAFHdnlAYk2qu8lIr--yXmdJlELDWOQ-KRM"  # Your token
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Download settings
DOWNLOAD_PATH = os.getenv("DOWNLOAD_PATH", "./downloads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "2147483648"))  # 2GB

# Allowed extensions
ALLOWED_EXTENSIONS = [
    # Videos
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    # Audio
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a',
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg',
    # Documents
    '.pdf', '.doc', '.docx', '.txt', '.rtf', '.xls', '.xlsx', '.ppt', '.pptx',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
    # Others
    '.apk', '.exe', '.iso', '.torrent'
]

# Rate limiting (per user)
MAX_DOWNLOADS_PER_DAY = 10
DOWNLOAD_COOLDOWN = 60  # seconds between downloads
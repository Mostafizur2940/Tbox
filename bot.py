import os
import logging
import asyncio
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
import aiohttp
import aiofiles
from tqdm.asyncio import tqdm

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler,
    ConversationHandler
)
from telegram.constants import ParseMode, ChatAction

from config import BOT_TOKEN, DOWNLOAD_PATH, MAX_FILE_SIZE, ALLOWED_EXTENSIONS, ADMIN_IDS
from terabox_downloader import TeraboxDownloader

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_ACTION, DOWNLOADING = range(2)

class TeraboxDownloadBot:
    def __init__(self):
        self.downloader = TeraboxDownloader()
        self.user_stats: Dict[int, Dict[str, Any]] = {}
        self.download_tasks: Dict[int, asyncio.Task] = {}
        
        # Ensure download directory exists
        self.download_path = Path(DOWNLOAD_PATH)
        self.download_path.mkdir(exist_ok=True)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Initialize user stats
        if user.id not in self.user_stats:
            self.user_stats[user.id] = {
                'downloads_today': 0,
                'total_downloads': 0,
                'last_download': None,
                'start_date': datetime.now()
            }
        
        welcome_text = f"""
🤖 *Welcome to Terabox Downloader Bot* 🤖

👋 Hello {user.first_name}!

📥 *Send me any Terabox link and I'll download it for you!*

✅ *Supported Links:*
• terabox.com
• dubox.com
• terabox.app

📁 *Supported Files:*
• Videos (MP4, AVI, MKV, etc.)
• Audio (MP3, WAV, etc.)
• Images (JPG, PNG, GIF, etc.)
• Documents (PDF, DOC, TXT, etc.)
• Archives (ZIP, RAR, 7Z, etc.)

⚡ *Features:*
• Fast downloads
• Progress updates
• File size checking
• Automatic format detection

⚠️ *Limitations:*
• Max file size: 2GB
• Rate limited to prevent abuse

🛠 *Commands:*
/start - Start the bot
/help - Show help message
/cancel - Cancel current operation
/stats - Your download statistics
/support - Get support

🔗 *Just send me a Terabox link to get started!*
        """
        
        keyboard = [
            [InlineKeyboardButton("📖 How to Use", callback_data="help")],
            [InlineKeyboardButton("⚠️ Limitations", callback_data="limits")],
            [InlineKeyboardButton("🛠 Commands", callback_data="commands")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📖 *HOW TO USE THIS BOT*

1. *Find a Terabox link* - Get any shareable link from Terabox
2. *Send the link* - Paste the link in chat
3. *Wait for processing* - Bot will analyze the file
4. *Confirm download* - Check file info and confirm
5. *Receive file* - Bot will send you the downloaded file

⚙️ *COMMANDS*

/start - Start bot & show welcome
/help - This help message
/cancel - Cancel current operation
/stats - Your download statistics
/support - Contact support

🔒 *PRIVACY & SAFETY*
• Files are deleted immediately after sending
• No logs of your downloads are kept
• Your data is never shared
• Bot only processes public links

⚠️ *IMPORTANT NOTES*
• Only download content you own or have permission for
• Respect copyright laws
• Large files may take time
• Bot may be rate-limited
• Use responsibly!

📞 *SUPPORT*
If you have issues:
1. Check if link is valid
2. Ensure file is under 2GB
3. Try again in few minutes
4. Contact admin for help

*Ready to download? Just send me a Terabox link!*
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming Terabox links"""
        user = update.effective_user
        message = update.message
        
        # Check if user is rate limited
        if await self.is_rate_limited(user.id):
            await message.reply_text(
                "⏳ Please wait a moment before sending another link.\n"
                "Rate limit: 1 request per minute."
            )
            return
        
        # Extract URL from message
        text = message.text.strip()
        
        # Validate it's a Terabox URL
        if not self.downloader.is_valid_terabox_url(text):
            await message.reply_text(
                "❌ *Invalid Terabox Link!*\n\n"
                "Please send a valid Terabox URL.\n"
                "Example: `https://terabox.com/s/xxxxxxxxxx`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Send processing message
        processing_msg = await message.reply_text(
            "🔍 *Processing your link...*\n"
            "⏳ Please wait while I analyze the file.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Extract file information
            file_info = self.downloader.extract_file_info(text)
            
            if not file_info:
                await processing_msg.edit_text(
                    "❌ *Unable to process link!*\n\n"
                    "Possible reasons:\n"
                    "• Link is private/restricted\n"
                    "• File doesn't exist\n"
                    "• Server error\n"
                    "• Link format changed\n\n"
                    "Please check the link and try again.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Check file size
            file_size = file_info.get('size', 0)
            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / (1024 * 1024)
                max_mb = MAX_FILE_SIZE / (1024 * 1024)
                await processing_msg.edit_text(
                    f"❌ *File too large!*\n\n"
                    f"File size: {size_mb:.1f} MB\n"
                    f"Max allowed: {max_mb:.1f} MB\n\n"
                    f"Please choose a smaller file.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Prepare file info for user
            filename = file_info.get('filename', 'Unknown')
            size_str = self.format_size(file_size) if file_size else "Unknown"
            
            info_text = f"""
✅ *File Found!*

📁 *Filename:* `{filename}`
📊 *Size:* {size_str}
🔗 *Source:* Terabox

📥 *Do you want to download this file?*
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Download", callback_data=f"download_{hash(text)}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store context for callback
            context.user_data['current_link'] = text
            context.user_data['file_info'] = file_info
            context.user_data['processing_msg_id'] = processing_msg.message_id
            
            await processing_msg.edit_text(
                info_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error processing link: {str(e)}")
            await processing_msg.edit_text(
                f"❌ *Error processing link!*\n\n"
                f"Error: {str(e)[:100]}\n\n"
                f"Please try again later or contact support.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        data = query.data
        
        if data.startswith("download_"):
            # Extract original link from user_data
            original_link = context.user_data.get('current_link')
            file_info = context.user_data.get('file_info')
            
            if not original_link or not file_info:
                await query.edit_message_text("❌ Session expired. Please send link again.")
                return
            
            # Start download
            await self.start_download(user.id, original_link, file_info, query)
            
        elif data == "cancel":
            await query.edit_message_text("❌ Download cancelled.")
            del context.user_data['current_link']
            del context.user_data['file_info']
            
        elif data == "help":
            await self.help_command(update, context)
        elif data == "limits":
            await query.edit_message_text(
                "⚠️ *LIMITATIONS*\n\n"
                "• Max file size: 2GB\n"
                "• Rate limit: 1 request/minute\n"
                "• Supported formats only\n"
                "• Public links only\n"
                "• No password protected files",
                parse_mode=ParseMode.MARKDOWN
            )
        elif data == "commands":
            await query.edit_message_text(
                "🛠 *COMMANDS*\n\n"
                "/start - Start bot\n"
                "/help - Show help\n"
                "/cancel - Cancel operation\n"
                "/stats - Your stats\n"
                "/support - Get help\n\n"
                "*Just send a link to download!*",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def start_download(self, user_id: int, url: str, file_info: dict, query):
        """Start download process"""
        try:
            # Update user stats
            if user_id not in self.user_stats:
                self.user_stats[user_id] = {
                    'downloads_today': 0,
                    'total_downloads': 0,
                    'last_download': datetime.now(),
                    'start_date': datetime.now()
                }
            
            self.user_stats[user_id]['downloads_today'] += 1
            self.user_stats[user_id]['total_downloads'] += 1
            self.user_stats[user_id]['last_download'] = datetime.now()
            
            filename = file_info.get('filename', f"download_{int(time.time())}")
            file_size = file_info.get('size', 0)
            
            # Create unique filename
            unique_id = hashlib.md5(f"{url}_{time.time()}".encode()).hexdigest()[:8]
            ext = self.get_file_extension(filename)
            safe_filename = f"{unique_id}_{self.sanitize_filename(filename)}"
            if ext and not safe_filename.endswith(ext):
                safe_filename += ext
            
            download_path = self.download_path / safe_filename
            
            # Update message
            await query.edit_message_text(
                f"⬇️ *Downloading...*\n\n"
                f"📁 *File:* `{filename}`\n"
                f"📊 *Size:* {self.format_size(file_size)}\n"
                f"⏳ *Status:* Starting download...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Start download
            task = asyncio.create_task(
                self.download_file(url, download_path, query, file_info)
            )
            self.download_tasks[user_id] = task
            
            # Wait for download to complete
            success = await task
            
            if success:
                # Send file to user
                await self.send_file_to_user(user_id, download_path, query, file_info)
            else:
                await query.edit_message_text(
                    "❌ *Download failed!*\n\n"
                    "Possible reasons:\n"
                    "• Network error\n"
                    "• File unavailable\n"
                    "• Server blocked\n"
                    "• Timeout\n\n"
                    "Please try again later.",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            # Cleanup
            if download_path.exists():
                try:
                    download_path.unlink()
                except:
                    pass
            
            if user_id in self.download_tasks:
                del self.download_tasks[user_id]
                
        except Exception as e:
            logger.error(f"Error in download process: {str(e)}")
            await query.edit_message_text(
                f"❌ *Download error!*\n\n"
                f"Error: {str(e)[:100]}\n\n"
                f"Please try again.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def download_file(self, url: str, path: Path, query, file_info: dict) -> bool:
        """Download file with progress"""
        try:
            # Try to get direct download URL
            direct_url = self.downloader.get_direct_download_url(url)
            if not direct_url:
                direct_url = url
            
            async with aiohttp.ClientSession() as session:
                async with session.get(direct_url, timeout=3600) as response:
                    if response.status != 200:
                        return False
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    # Create progress message
                    progress_msg = await query.message.reply_text(
                        f"📥 *Download Progress*\n"
                        f"📁 File: `{file_info.get('filename', 'Unknown')}`\n"
                        f"📊 Size: {self.format_size(total_size)}\n"
                        f"⏳ Status: Starting...\n"
                        f"📈 Progress: 0%",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    # Download with progress
                    chunk_size = 8192
                    async with aiofiles.open(path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            if not chunk:
                                break
                            
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress every 5% or 5MB
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if downloaded % (5 * 1024 * 1024) < chunk_size or progress % 5 < 0.1:
                                    try:
                                        await progress_msg.edit_text(
                                            f"📥 *Download Progress*\n"
                                            f"📁 File: `{file_info.get('filename', 'Unknown')}`\n"
                                            f"📊 Size: {self.format_size(total_size)}\n"
                                            f"⏳ Status: Downloading...\n"
                                            f"📈 Progress: {progress:.1f}%\n"
                                            f"📥 Downloaded: {self.format_size(downloaded)} / {self.format_size(total_size)}",
                                            parse_mode=ParseMode.MARKDOWN
                                        )
                                    except:
                                        pass
                    
                    await progress_msg.edit_text(
                        f"✅ *Download Complete!*\n"
                        f"📁 File: `{file_info.get('filename', 'Unknown')}`\n"
                        f"📊 Size: {self.format_size(total_size)}\n"
                        f"⏱️ Status: Preparing to send...",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                    return True
                    
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            return False
    
    async def send_file_to_user(self, user_id: int, path: Path, query, file_info: dict):
        """Send downloaded file to user"""
        try:
            file_size = path.stat().st_size
            filename = file_info.get('filename', path.name)
            
            # Determine file type for sending
            ext = path.suffix.lower()
            
            # Update message
            sending_msg = await query.message.reply_text(
                f"📤 *Sending file...*\n\n"
                f"📁 File: `{filename}`\n"
                f"📊 Size: {self.format_size(file_size)}\n"
                f"⏳ Please wait...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send based on file type
            try:
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                    await query.message.reply_photo(
                        photo=open(path, 'rb'),
                        caption=f"📷 *Image Downloaded*\n\n📁 `{filename}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                    await query.message.reply_audio(
                        audio=open(path, 'rb'),
                        caption=f"🎵 *Audio Downloaded*\n\n📁 `{filename}`",
                        parse_mode=ParseMode.MARKDOWN,
                        title=filename
                    )
                elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv']:
                    await query.message.reply_video(
                        video=open(path, 'rb'),
                        caption=f"🎥 *Video Downloaded*\n\n📁 `{filename}`",
                        parse_mode=ParseMode.MARKDOWN,
                        supports_streaming=True
                    )
                elif ext in ['.pdf', '.doc', '.docx', '.txt']:
                    await query.message.reply_document(
                        document=open(path, 'rb'),
                        caption=f"📄 *Document Downloaded*\n\n📁 `{filename}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await query.message.reply_document(
                        document=open(path, 'rb'),
                        caption=f"📁 *File Downloaded*\n\n📁 `{filename}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Success message
                await sending_msg.edit_text(
                    f"✅ *File Sent Successfully!*\n\n"
                    f"📁 File: `{filename}`\n"
                    f"📊 Size: {self.format_size(file_size)}\n"
                    f"🎉 Ready for next download!\n\n"
                    f"Send another Terabox link when ready.",
                    parse_mode=ParseMode.MARKDOWN
                )
                
            except Exception as e:
                await sending_msg.edit_text(
                    f"⚠️ *File too large for Telegram!*\n\n"
                    f"File size: {self.format_size(file_size)}\n"
                    f"Telegram limit: 2GB\n\n"
                    f"Download link: `{str(path.absolute())}`",
            
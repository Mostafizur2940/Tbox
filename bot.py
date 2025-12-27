import os
import logging
import asyncio
import aiohttp
import aiofiles
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import time

# Import our downloader
from terabox_downloader import TeraboxDownloader

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Your bot token
BOT_TOKEN = "8546123786:AAFHdnlAYk2qu8lIr--yXmdJlELDWOQ-KRM"

# Create downloader instance
downloader = TeraboxDownloader()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"👋 Hello {user.mention_html()}!\n\n"
        f"🤖 <b>Terabox Downloader Bot</b>\n\n"
        f"📥 <b>Send me any Terabox link and I'll download it for you!</b>\n\n"
        f"✅ <b>Supported:</b>\n"
        f"• terabox.com\n"
        f"• 1024terabox.com\n"
        f"• terabox.app\n"
        f"• dubox.com\n\n"
        f"⚡ <b>Just paste a Terabox link and I'll handle the rest!</b>"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message."""
    help_text = """
📖 <b>HOW TO USE:</b>

1. <b>Copy</b> any Terabox share link
2. <b>Paste</b> it in this chat
3. <b>Wait</b> for the bot to process
4. <b>Receive</b> your downloaded file

⚠️ <b>Note:</b> Some files may require manual download if protected.

🔗 <b>Example link format:</b>
https://terabox.com/s/XXXXX
https://1024terabox.com/s/XXXXX

🛠 <b>Commands:</b>
/start - Start the bot
/help - Show this help
/status - Check bot status
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    user_message = update.message.text.strip()
    
    # Check if it's a Terabox URL
    if downloader.is_terabox_url(user_message):
        await process_terabox_link(update, user_message)
    else:
        await update.message.reply_text(
            "❌ <b>Not a valid Terabox link!</b>\n\n"
            "Please send a valid Terabox URL.\n"
            "Example: <code>https://terabox.com/s/XXXXX</code>",
            parse_mode=ParseMode.HTML
        )

async def process_terabox_link(update: Update, url: str):
    """Process Terabox link and download file."""
    # Send processing message
    processing_msg = await update.message.reply_text(
        "🔍 <b>Processing your Terabox link...</b>\n"
        "⏳ Please wait while I analyze the file...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Extract file information
        file_info = downloader.extract_info(url)
        
        if not file_info:
            await processing_msg.edit_text(
                "❌ <b>Failed to process link!</b>\n\n"
                "Possible reasons:\n"
                "• Link is private/restricted\n"
                "• File doesn't exist\n"
                "• Server error\n\n"
                "Please check the link and try again.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get filename
        filename = file_info.get('filename', f'terabox_file_{int(time.time())}')
        
        # Try to get direct download
        download_info = downloader.get_direct_download(url)
        
        if download_info and 'url' in download_info:
            # We have a direct download URL
            await start_download(update, processing_msg, download_info, filename)
        else:
            # No direct download available, show manual method
            await show_manual_method(update, processing_msg, url, filename, file_info)
            
    except Exception as e:
        logger.error(f"Error processing link: {str(e)}")
        await processing_msg.edit_text(
            f"❌ <b>Error occurred!</b>\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Please try again later.",
            parse_mode=ParseMode.HTML
        )

async def start_download(update: Update, processing_msg, download_info, filename):
    """Start downloading the file."""
    try:
        # Update message
        await processing_msg.edit_text(
            f"⬇️ <b>Downloading file...</b>\n\n"
            f"📁 <b>File:</b> <code>{filename}</code>\n"
            f"⏳ <b>Status:</b> Starting download...",
            parse_mode=ParseMode.HTML
        )
        
        # Create temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
            temp_path = temp_file.name
        
        # Download the file
        download_url = download_info['url']
        
        # Use aiohttp for async download
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    total_size = 0
                    downloaded = 0
                    
                    # Get file size
                    if 'content-length' in response.headers:
                        total_size = int(response.headers['content-length'])
                    
                    # Download with progress
                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress every 1MB
                            if total_size > 0 and downloaded % (1024 * 1024) < 8192:
                                progress = (downloaded / total_size) * 100
                                try:
                                    await processing_msg.edit_text(
                                        f"⬇️ <b>Downloading file...</b>\n\n"
                                        f"📁 <b>File:</b> <code>{filename}</code>\n"
                                        f"📊 <b>Progress:</b> {progress:.1f}%\n"
                                        f"⏳ <b>Downloaded:</b> {downloaded / (1024*1024):.1f} MB",
                                        parse_mode=ParseMode.HTML
                                    )
                                except:
                                    pass
                    
                    # Send file to user
                    await send_file_to_user(update, processing_msg, temp_path, filename)
                    
                else:
                    await processing_msg.edit_text(
                        "❌ <b>Download failed!</b>\n\n"
                        "Server returned error code. Please try again later.",
                        parse_mode=ParseMode.HTML
                    )
        
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except:
            pass
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        await processing_msg.edit_text(
            f"❌ <b>Download failed!</b>\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Please try again or use manual method.",
            parse_mode=ParseMode.HTML
        )

async def send_file_to_user(update: Update, processing_msg, file_path, filename):
    """Send downloaded file to user."""
    try:
        file_size = os.path.getsize(file_path)
        
        # Determine file type
        ext = os.path.splitext(filename)[1].lower()
        
        # Update message
        await processing_msg.edit_text(
            f"📤 <b>Sending file to you...</b>\n\n"
            f"📁 <b>File:</b> <code>{filename}</code>\n"
            f"📊 <b>Size:</b> {file_size / (1024*1024):.1f} MB\n"
            f"⏳ Please wait...",
            parse_mode=ParseMode.HTML
        )
        
        # Send file based on type
        with open(file_path, 'rb') as file:
            if ext in ['.jpg', '.jpeg', '.png', '.gif']:
                await update.message.reply_photo(
                    photo=file,
                    caption=f"📷 <b>Downloaded:</b> <code>{filename}</code>",
                    parse_mode=ParseMode.HTML
                )
            elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
                await update.message.reply_video(
                    video=file,
                    caption=f"🎥 <b>Downloaded:</b> <code>{filename}</code>",
                    parse_mode=ParseMode.HTML,
                    supports_streaming=True
                )
            elif ext in ['.mp3', '.wav', '.flac']:
                await update.message.reply_audio(
                    audio=file,
                    caption=f"🎵 <b>Downloaded:</b> <code>{filename}</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_document(
                    document=file,
                    caption=f"📁 <b>Downloaded:</b> <code>{filename}</code>",
                    parse_mode=ParseMode.HTML
                )
        
        # Success message
        await processing_msg.edit_text(
            f"✅ <b>File sent successfully!</b>\n\n"
            f"📁 <b>File:</b> <code>{filename}</code>\n"
            f"📊 <b>Size:</b> {file_size / (1024*1024):.1f} MB\n"
            f"🎉 <b>Ready for next download!</b>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error sending file: {str(e)}")
        await processing_msg.edit_text(
            f"⚠️ <b>File too large for Telegram!</b>\n\n"
            f"Telegram has file size limits.\n"
            f"File saved at: <code>{file_path}</code>",
            parse_mode=ParseMode.HTML
        )

async def show_manual_method(update: Update, processing_msg, url, filename, file_info):
    """Show manual download method when direct download fails."""
    manual_text = f"""
⚠️ <b>Direct Download Not Available</b>

📁 <b>File:</b> <code>{filename}</code>

🔗 <b>Original Link:</b>
<code>{url}</code>

📋 <b>Manual Download Method:</b>

1. <b>Open link</b> in browser
2. <b>Wait</b> for page to load
3. Look for <b>download button</b>
4. Click to download manually

💡 <b>Tip:</b> Some Terabox files require login or have download restrictions.

🔄 You can try sending the link again in a few minutes.
    """
    
    await processing_msg.edit_text(manual_text, parse_mode=ParseMode.HTML)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check bot status."""
    await update.message.reply_text(
        "✅ <b>Bot Status: Running</b>\n\n"
        "🤖 <b>Terabox Downloader Bot</b>\n"
        "🟢 <b>Online</b>\n"
        "📥 <b>Ready to download</b>\n\n"
        "Send me any Terabox link to get started!",
        parse_mode=ParseMode.HTML
    )

def main():
    """Start the bot."""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Log errors
    application.add_error_handler(lambda u, c: logger.error(c.error) if c.error else None)
    
    # Start bot
    logger.info("🤖 Starting Terabox Downloader Bot...")
    print("\n" + "="*50)
    print("TERABOX DOWNLOADER BOT")
    print("="*50)
    print("🚀 Bot is running!")
    print("📱 Send /start to begin")
    print("🔗 Paste any Terabox link to download")
    print("="*50)
    
    # Run bot
    application.run_polling()

if __name__ == '__main__':
    main()

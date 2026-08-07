from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import re
import asyncio
from datetime import datetime
import os

# ============================================
# 🔧 خواندن تنظیمات از متغیرهای محیطی (رندر)
# ============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "توکن_ربات_اینجا")
GROUP_ID = int(os.environ.get("GROUP_ID", -1001234567890))
YOUR_USER_ID = int(os.environ.get("YOUR_USER_ID", 123456789))
# ============================================

pending_requests = {}
counter = 0

def generate_code():
    global counter
    counter += 1
    return f"REQ-{counter:04d}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 سلام! به ربات دانلود اینستاگرام خوش اومدی!\n\n"
        "📥 لینک پست، ریل یا استوری اینستاگرام رو برام بفرست تا برات دانلود کنم.\n\n"
        "مثال: https://instagram.com/p/ABC123\n"
        "مثال: https://instagram.com/reel/XYZ789\n"
        "مثال: https://instagram.com/stories/username/123456"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    link = update.message.text.strip()
    username = update.effective_user.username or "کاربر"
    
    if not re.match(r'https?://(www\.)?(instagram\.com|instagr\.am)/.+', link):
        await update.message.reply_text("❌ لینک معتبر نیست!")
        return
    
    code = generate_code()
    
    pending_requests[code] = {
        "user_id": user_id,
        "link": link,
        "username": username,
        "status": "waiting",
        "timestamp": datetime.now()
    }
    
    try:
        await context.bot.send_message(
            chat_id=YOUR_USER_ID,
            text=f"📥 درخواست جدید\n👤 کاربر: {username} (ID: {user_id})\n🆔 کد: {code}\n🔗 لینک: {link}"
        )
        
        await update.message.reply_text(
            f"✅ درخواست ثبت شد!\n\n🆔 کد پیگیری: `{code}`\n⏳ لطفاً چند لحظه صبر کنید...",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text("❌ خطا در پردازش!")

async def group_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return
    
    if not (update.message.video or update.message.photo or update.message.document):
        return
    
    caption = update.message.caption or ""
    reply_text = update.message.reply_to_message.text if update.message.reply_to_message else ""
    full_text = caption + " " + reply_text
    
    for code, data in list(pending_requests.items()):
        if code in full_text and data["status"] == "waiting":
            
            if update.message.video:
                file_id = update.message.video.file_id
                file_type = "video"
            elif update.message.photo:
                file_id = update.message.photo[-1].file_id
                file_type = "photo"
            else:
                file_id = update.message.document.file_id
                file_type = "document"
            
            try:
                await context.bot.send_message(
                    chat_id=data["user_id"],
                    text=f"✅ دانلود شد! 🎉\n🆔 کد درخواست: {code}"
                )
                
                if file_type == "video":
                    await context.bot.send_video(data["user_id"], video=file_id, caption=f"📥 کد: {code}")
                elif file_type == "photo":
                    await context.bot.send_photo(data["user_id"], photo=file_id, caption=f"📥 کد: {code}")
                else:
                    await context.bot.send_document(data["user_id"], document=file_id, caption=f"📥 کد: {code}")
                
                data["status"] = "done"
                asyncio.create_task(delete_after_delay(code))
                
            except Exception as e:
                print(f"❌ خطا: {e}")

async def delete_after_delay(code):
    await asyncio.sleep(10)
    if code in pending_requests:
        del pending_requests[code]

async def clean_old_requests():
    while True:
        await asyncio.sleep(300)
        now = datetime.now()
        to_remove = []
        for code, data in pending_requests.items():
            if (now - data["timestamp"]).seconds > 600:
                to_remove.append(code)
        for code in to_remove:
            del pending_requests[code]

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(MessageHandler(filters.ALL, group_listener))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(clean_old_requests())
    
    print("🤖 ربات شروع به کار کرد...")
    app.run_polling()

if __name__ == "__main__":
    main()

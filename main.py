#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات دانلودر اینستاگرام - نسخه کامل با Telethon
"""

import os
import json
import time
import asyncio
import logging
from threading import Thread
from datetime import datetime
from flask import Flask, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

# ======================== تنظیمات ========================
TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))
DOWNLOADER_ID = int(os.environ.get("DOWNLOADER_BOT_ID", 0))
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

FREE_LIMIT = int(os.environ.get("FREE_LIMIT", 3))
PREMIUM_PRICE = os.environ.get("PREMIUM_PRICE", "۲۰۰,۰۰۰ تومان")
SUPPORT_ID = os.environ.get("SUPPORT_ID", "admin")
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "📥 ربات دانلود از اینستاگرام : @inmedia_robot")

# Telethon Settings
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")

try:
    SPONSOR_CHANNELS = json.loads(os.environ.get("SPONSOR_CHANNELS", "[]"))
except:
    SPONSOR_CHANNELS = []

# ======================== Flask Web Server ========================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return jsonify({"status": "running", "bot": "inmedia_robot"})

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"})

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ======================== Logging ========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ======================== Database (Memory) ========================
users = {}
pending_requests = {}

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "downloads": 0,
            "first_time": 0,
            "premium": False,
            "bonus": 0,
            "referrals": 0,
            "username": None
        }
    return users[uid]

def can_download(user_id):
    user = get_user(user_id)
    if user["premium"]:
        return True, "♾️ پریمیوم", 999
    
    now = int(time.time())
    if user["first_time"] == 0:
        return True, "✅ اولین دانلود", FREE_LIMIT
    
    if now - user["first_time"] >= 86400:
        user["downloads"] = 0
        user["first_time"] = 0
        user["bonus"] = 0
        return True, "✅ سهمیه جدید", FREE_LIMIT
    
    limit = FREE_LIMIT + user["bonus"]
    remaining = limit - user["downloads"]
    if remaining > 0:
        return True, f"✅ {remaining} دانلود باقی مونده", remaining
    return False, "🚫 سهمیه دانلود امروز تموم شد!", 0

def increment_download(user_id):
    user = get_user(user_id)
    user["downloads"] += 1
    if user["first_time"] == 0:
        user["first_time"] = int(time.time())

# ======================== Telethon Client ========================
class TelethonService:
    def __init__(self):
        self.client = None
        self._running = False
        self.bot = None
    
    async def start(self):
        if not API_ID or not API_HASH or not SESSION_STRING:
            logger.error("❌ Telethon credentials not configured!")
            return False
        
        try:
            self.client = TelegramClient(
                StringSession(SESSION_STRING),
                API_ID,
                API_HASH
            )
            
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error("❌ Telethon client not authorized!")
                return False
            
            me = await self.client.get_me()
            logger.info(f"✅ Telethon started as: @{me.username}")
            
            self._running = True
            
            # Start listening to group
            @self.client.on(events.NewMessage(chats=GROUP_ID))
            async def handle_message(event):
                message = event.message
                
                # Only process messages from downloader bot
                if message.from_id and message.from_id.user_id == DOWNLOADER_ID:
                    logger.info(f"📩 Received message from downloader bot")
                    
                    if not message.reply_to:
                        return
                    
                    msg_id = message.reply_to.reply_to_msg_id
                    
                    if msg_id not in pending_requests:
                        return
                    
                    user_id = pending_requests[msg_id]
                    del pending_requests[msg_id]
                    
                    # Check if it's an error message
                    if message.text and ("error" in message.text.lower() or "❌" in message.text):
                        await self.bot.send_message(user_id, f"❌ خطا: {message.text}")
                        await self.cleanup(msg_id, message.id)
                        return
                    
                    # Send media to user
                    if message.media:
                        try:
                            await self.bot.copy_message(
                                chat_id=user_id,
                                from_chat_id=GROUP_ID,
                                message_id=message.id,
                                caption=CUSTOM_CAPTION
                            )
                            increment_download(user_id)
                            await self.cleanup(msg_id, message.id)
                        except Exception as e:
                            logger.error(f"❌ Error sending media: {e}")
                            await self.bot.send_message(user_id, f"❌ خطا: {str(e)[:50]}")
                            await self.cleanup(msg_id, message.id)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Telethon error: {e}")
            return False
    
    async def send_link(self, link: str, user_id: int) -> bool:
        try:
            message = await self.client.send_message(
                GROUP_ID,
                f"📥 {link}"
            )
            pending_requests[message.id] = user_id
            logger.info(f"✅ Link sent to group (msg_id: {message.id})")
            return True
        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait: {e.seconds}s")
            await asyncio.sleep(e.seconds)
            return await self.send_link(link, user_id)
        except Exception as e:
            logger.error(f"❌ Failed to send link: {e}")
            return False
    
    async def cleanup(self, link_id: int, downloader_id: int):
        try:
            await self.client.delete_messages(GROUP_ID, [link_id, downloader_id])
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete: {e}")
    
    async def stop(self):
        self._running = False
        if self.client:
            await self.client.disconnect()
            logger.info("🛑 Telethon stopped")

telethon = TelethonService()

# ======================== Bot Handlers ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["username"] = update.effective_user.username
    
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت من", callback_data="status")],
        [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
        [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")],
    ]
    
    text = (
        f"🎯 **به ربات دانلودر خوش آمدید!**\n\n"
        f"📥 لینک خود را ارسال کنید تا دانلود کنم.\n\n"
        f"📊 سهمیه رایگان: {FREE_LIMIT} دانلود/روز\n"
        f"💰 قیمت اشتراک: {PREMIUM_PRICE}\n\n"
        f"🔹 پشتیبانی از:\n"
        f"• اینستاگرام\n• یوتیوب\n• تیک‌تاک\n• فیسبوک\n• توییتر/X"
    )
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    link = update.message.text
    
    # 1️⃣ Check sponsor channels
    for channel in SPONSOR_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                keyboard = [[InlineKeyboardButton(f"📢 عضویت در {channel['name']}", url=f"https://t.me/{channel['id'].replace('-100', '')}")]]
                await update.message.reply_text(
                    f"🚨 لطفاً در {channel['name']} عضو شوید",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
        except:
            pass
    
    # 2️⃣ Check download limit
    can, msg, _ = can_download(user_id)
    if not can:
        keyboard = [
            [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
            [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")]
        ]
        await update.message.reply_text(
            f"{msg}\n\nیکی از گزینه‌ها رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 3️⃣ Send link via Telethon
    wait_msg = await update.message.reply_text("⏳ **در حال دانلود با بالاترین کیفیت...**")
    
    try:
        success = await telethon.send_link(link, user_id)
        if success:
            await wait_msg.edit_text("⏳ **در حال دانلود با بالاترین کیفیت...**\n✅ لینک ارسال شد. منتظر پاسخ باشید...")
        else:
            await wait_msg.edit_text("❌ خطا در ارسال به گروه. دوباره تلاش کنید.")
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا: {str(e)[:50]}")

async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    limit = FREE_LIMIT + user["bonus"]
    remaining = limit - user["downloads"]
    
    text = (
        f"📊 **وضعیت شما**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 {query.from_user.first_name}\n"
        f"📌 {'👑 پریمیوم' if user['premium'] else '🆓 رایگان'}\n"
        f"📥 دانلود امروز: {user['downloads']}\n"
        f"✅ باقی‌مانده: {max(0, remaining)}\n"
        f"🎁 هدیه دعوت: {user['bonus']}\n"
        f"👥 دعوت موفق: {user['referrals']}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت من", callback_data="status")],
        [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
        [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")],
    ]
    
    text = (
        f"🎯 **ربات دانلودر اینستاگرام**\n\n"
        f"👤 کاربر: @{user.get('username') or 'کاربر'}\n"
        f"💰 {'👑 پریمیوم' if user['premium'] else '🆓 رایگان'}\n"
        f"📥 دانلود امروز: {user['downloads']}\n"
        f"✅ باقی‌مانده: {FREE_LIMIT + user['bonus'] - user['downloads']}\n\n"
        f"📥 لینک خود را ارسال کنید تا دانلود کنم."
    )
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        f"🎁 **لینک دعوت شما**\n\n"
        f"🔗 {link}\n\n"
        f"📌 هر دعوت موفق = ۱ دانلود هدیه"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 اشتراک‌گذاری", url=f"tg://msg?text={link}")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        f"♾ **اشتراک مادام‌العمر**\n\n"
        f"با خرید اشتراک، بدون محدودیت دانلود کنید.\n\n"
        f"💰 قیمت: {PREMIUM_PRICE}\n\n"
        f"📞 برای خرید با پشتیبانی تماس بگیرید:\n"
        f"@{SUPPORT_ID}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📞 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_ID}")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== Admin Handlers ========================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
        [InlineKeyboardButton("👑 مدیریت پریمیوم", callback_data="admin_premium")],
        [InlineKeyboardButton("📋 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🔙 بستن", callback_data="admin_close")]
    ]
    
    await update.message.reply_text("🔧 **پنل مدیریت**", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    total = len(users)
    premium = sum(1 for u in users.values() if u.get("premium", False))
    
    text = (
        f"📊 **آمار کلی**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {total}\n"
        f"👑 پریمیوم: {premium}\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        f"👑 **مدیریت پریمیوم**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📋 دستور: /premium [user_id] on/off\n"
        f"💡 مثال: /premium 123456789 on"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    total = len(users)
    text = f"📋 **لیست کاربران**\n━━━━━━━━━━━━━━━\n👥 کل: {total}\n━━━━━━━━━━━━━━━\n"
    
    for i, (uid, data) in enumerate(list(users.items())[-10:], 1):
        premium = "👑" if data.get("premium", False) else "🆓"
        downloads = data.get("downloads", 0)
        text += f"{i}. `{uid}` {premium} - دانلود: {downloads}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_panel(update, context)

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔐 پنل بسته شد.")

async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text("❌ /premium [user_id] on/off")
        return
    
    try:
        target = int(parts[1])
        status = parts[2].lower()
    except:
        await update.message.reply_text("❌ فرمت نامعتبر!")
        return
    
    user = get_user(target)
    user["premium"] = (status == "on")
    
    try:
        if user["premium"]:
            await context.bot.send_message(target, "🎉 اشتراک شما فعال شد!")
        else:
            await context.bot.send_message(target, "⚠️ اشتراک شما لغو شد.")
    except:
        pass
    
    await update.message.reply_text(f"✅ کاربر {target} {'فعال' if user['premium'] else 'غیرفعال'} شد.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    total = len(users)
    premium = sum(1 for u in users.values() if u.get("premium", False))
    
    text = (
        f"📊 **آمار کلی**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {total}\n"
        f"👑 پریمیوم: {premium}\n"
    )
    
    await update.message.reply_text(text)

# ======================== Main ========================
async def main():
    # Start Flask
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("✅ Flask started")
    
    # Set bot for telethon
    telethon.bot = app.bot
    
    # Start Telethon
    await telethon.start()
    
    # Start bot polling
    logger.info("🤖 Bot started!")
    await app.run_polling()

if __name__ == "__main__":
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(status_callback, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(referral_callback, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_premium, pattern="^admin_premium$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close$"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    asyncio.run(main())

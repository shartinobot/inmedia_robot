#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات دانلودر اینستاگرام - نسخه نهایی با فوروارد کردن پیام‌ها
"""

import os
import json
import logging
import time
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ======================== تنظیمات ========================
TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))
DOWNLOADER_ID = int(os.environ.get("DOWNLOADER_BOT_ID", 0))
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

FREE_LIMIT = int(os.environ.get("FREE_LIMIT", 3))
PREMIUM_PRICE = os.environ.get("PREMIUM_PRICE", "۲۰۰,۰۰۰ تومان")
SUPPORT_ID = os.environ.get("SUPPORT_ID", "admin")
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", "📥 ربات دانلود از اینستاگرام : @inmedia_robot")

try:
    SPONSOR_CHANNELS = json.loads(os.environ.get("SPONSOR_CHANNELS", "[]"))
except:
    SPONSOR_CHANNELS = []

# ======================== وب‌سرور Flask ========================
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

# ======================== دیتابیس در حافظه ========================
users = {}

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

# ======================== منوی اصلی ========================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت من", callback_data="status")],
        [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
        [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")],
    ]
    
    text = f"🎯 **ربات دانلودر اینستاگرام**\n\n"
    text += f"👤 کاربر: @{user.get('username') or 'کاربر'}\n"
    text += f"💰 {'👑 پریمیوم' if user['premium'] else '🆓 رایگان'}\n"
    text += f"📥 دانلود امروز: {user['downloads']}\n"
    text += f"✅ باقی‌مانده: {FREE_LIMIT + user['bonus'] - user['downloads']}\n\n"
    text += f"📥 لینک خود را ارسال کنید تا دانلود کنم."
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== استارت ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    user = get_user(user_id)
    user["username"] = username
    
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت من", callback_data="status")],
        [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
        [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")],
    ]
    
    text = f"🎯 **به ربات دانلودر خوش آمدید!**\n\n"
    text += f"📥 لینک خود را ارسال کنید تا دانلود کنم.\n\n"
    text += f"📊 سهمیه رایگان: {FREE_LIMIT} دانلود/روز\n"
    text += f"💰 قیمت اشتراک: {PREMIUM_PRICE}\n\n"
    text += f"🔹 پشتیبانی از:\n"
    text += f"• اینستاگرام\n• یوتیوب\n• تیک‌تاک\n• فیسبوک\n• توییتر/X"
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== وضعیت ========================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    limit = FREE_LIMIT + user["bonus"]
    remaining = limit - user["downloads"]
    
    text = f"📊 **وضعیت شما**\n"
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"👤 {query.from_user.first_name}\n"
    text += f"📌 {'👑 پریمیوم' if user['premium'] else '🆓 رایگان'}\n"
    text += f"📥 دانلود امروز: {user['downloads']}\n"
    text += f"✅ باقی‌مانده: {max(0, remaining)}\n"
    text += f"🎁 هدیه دعوت: {user['bonus']}\n"
    text += f"👥 دعوت موفق: {user['referrals']}\n"
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"🔗 لینک دعوت شما:\n"
    text += f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    
    keyboard = [
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== دعوت ========================
async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = f"🎁 **لینک دعوت شما**\n\n"
    text += f"🔗 {link}\n\n"
    text += f"📌 هر دعوت موفق = ۱ دانلود هدیه\n\n"
    text += f"📋 روی لینک بالا کلیک کنید تا کپی شود"
    
    keyboard = [
        [InlineKeyboardButton("📤 اشتراک‌گذاری", url=f"tg://msg?text={link}")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== خرید اشتراک ========================
async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = f"♾ **اشتراک مادام‌العمر**\n\n"
    text += f"با خرید اشتراک، بدون محدودیت دانلود کنید.\n\n"
    text += f"💰 قیمت: {PREMIUM_PRICE}\n\n"
    text += f"📞 برای خرید با پشتیبانی تماس بگیرید:\n"
    text += f"@{SUPPORT_ID}"
    
    keyboard = [
        [InlineKeyboardButton("📞 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_ID}")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ======================== هندلر لینک با فوروارد ========================
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    link = message.text
    
    # 1️⃣ عضویت اجباری
    for ch in SPONSOR_CHANNELS:
        try:
            member = await context.bot.get_chat_member(ch["id"], user_id)
            if member.status in ["left", "kicked"]:
                keyboard = [[InlineKeyboardButton(f"📢 عضویت در {ch['name']}", url=f"https://t.me/{ch['id'].replace('-100', '')}")]]
                await message.reply_text(
                    f"🚨 لطفاً در {ch['name']} عضو شوید",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
        except:
            pass
    
    # 2️⃣ محدودیت دانلود
    can, msg, _ = can_download(user_id)
    if not can:
        keyboard = [
            [InlineKeyboardButton("🎁 دعوت از دوستان", callback_data="referral")],
            [InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy")]
        ]
        await message.reply_text(
            f"{msg}\n\nیکی از گزینه‌ها رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 3️⃣ فوروارد کردن پیام کاربر به گروه (به جای send_message)
    wait_msg = await message.reply_text("⏳ در حال پردازش...")
    try:
        # 🔥 قسمت اصلی: فوروارد کردن پیام کاربر به گروه
        group_msg = await context.bot.forward_message(
            chat_id=GROUP_ID,
            from_chat_id=user_id,
            message_id=message.message_id
        )
        
        # ذخیره برای matching
        context.user_data[f"pending_{group_msg.message_id}"] = user_id
        
        # تایمر ۲ دقیقه
        context.job_queue.run_once(
            timeout_job,
            120,
            data={"msg_id": group_msg.message_id, "user_id": user_id}
        )
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ خطا: {str(e)[:50]}")

# ======================== تایم‌اوت ========================
async def timeout_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    msg_id = data["msg_id"]
    user_id = data["user_id"]
    
    key = f"pending_{msg_id}"
    if key in context.user_data:
        del context.user_data[key]
        await context.bot.send_message(user_id, "⏰ زمان دانلود تمام شد. دوباره تلاش کنید.")
        try:
            await context.bot.delete_message(GROUP_ID, msg_id)
        except:
            pass

# ======================== گوش دادن به گروه ========================
async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # فقط از دانلودر
    if message.from_user.id != DOWNLOADER_ID:
        return
    
    if not message.reply_to_message:
        return
    
    # پیدا کردن message_id اصلی (که فوروارد شده)
    original_msg_id = message.reply_to_message.message_id
    key = f"pending_{original_msg_id}"
    
    if key not in context.user_data:
        return
    
    user_id = context.user_data[key]
    del context.user_data[key]
    
    # خطا؟
    if message.text and ("error" in message.text.lower() or "❌" in message.text):
        await context.bot.send_message(user_id, f"❌ خطا: {message.text}")
        await cleanup(context, original_msg_id, message.message_id)
        return
    
    # ثبت دانلود
    increment_download(user_id)
    
    # ارسال فایل با کپشن ثابت
    try:
        if message.video:
            await context.bot.send_video(user_id, message.video.file_id, caption=CUSTOM_CAPTION)
        elif message.photo:
            await context.bot.send_photo(user_id, message.photo[-1].file_id, caption=CUSTOM_CAPTION)
        elif message.document:
            await context.bot.send_document(user_id, message.document.file_id, caption=CUSTOM_CAPTION)
        elif message.audio:
            await context.bot.send_audio(user_id, message.audio.file_id, caption=CUSTOM_CAPTION)
        elif message.voice:
            await context.bot.send_voice(user_id, message.voice.file_id)
        elif message.animation:
            await context.bot.send_animation(user_id, message.animation.file_id, caption=CUSTOM_CAPTION)
        else:
            await context.bot.send_message(user_id, "⚠️ فرمت فایل پشتیبانی نمی‌شود")
            await cleanup(context, original_msg_id, message.message_id)
            return
    except Exception as e:
        await context.bot.send_message(user_id, f"❌ خطا: {str(e)[:50]}")
    
    await cleanup(context, original_msg_id, message.message_id)

# ======================== پاک‌سازی ========================
async def cleanup(context, link_id, reply_id):
    try:
        await context.bot.delete_message(GROUP_ID, link_id)
        await context.bot.delete_message(GROUP_ID, reply_id)
    except:
        pass

# ======================== دستورات ادمین ========================
async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("❌ /premium [user_id] on/off")
        return
    
    target = int(parts[1])
    status = parts[2].lower() if len(parts) > 2 else "on"
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

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    total = len(users)
    premium = sum(1 for u in users.values() if u.get("premium", False))
    
    text = f"📊 **آمار کلی**\n"
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"👥 کل کاربران: {total}\n"
    text += f"👑 پریمیوم: {premium}\n"
    text += f"📅 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    await update.message.reply_text(text)

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ دسترسی ندارید!")
        return
    
    global users
    users = {}
    await update.message.reply_text("🧹 **همه داده‌ها پاک شد!**")

# ======================== اصلی ========================
def main():
    logging.basicConfig(level=logging.INFO)
    
    # وب‌سرور Flask
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("✅ وب‌سرور Flask روشن شد")
    
    # ربات
    app = Application.builder().token(TOKEN).build()
    
    # دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("premium", premium_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    
    # کالبک‌ها
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(status_cmd, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(referral_cmd, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(buy_cmd, pattern="^buy$"))
    
    # پیام‌ها
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, handle_group))
    
    print("🤖 ربات دانلودر روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

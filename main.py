import os
import json
import asyncio
import time
import secrets
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.webhook import aiohttp_server
from aiogram.filters import Command

# ========== کلاس حافظه موقت ==========
class TempDB:
    """ذخیره‌سازی موقت در حافظه - با هر ری‌استارت پاک می‌شه"""
    def __init__(self):
        self.data = {}
        self.expiry = {}
    
    async def hset(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
    
    async def hgetall(self, key: str) -> dict:
        return self.data.get(key, {})
    
    async def hget(self, key: str, field: str):
        return self.data.get(key, {}).get(field)
    
    async def set(self, key: str, value: str, ex: int = None):
        self.data[key] = value
        if ex:
            self.expiry[key] = time.time() + ex
    
    async def get(self, key: str):
        if key in self.expiry and time.time() > self.expiry[key]:
            del self.data[key]
            del self.expiry[key]
            return None
        return self.data.get(key)
    
    async def delete(self, *keys):
        for key in keys:
            if key in self.data:
                del self.data[key]
            if key in self.expiry:
                del self.expiry[key]
    
    async def keys(self, pattern: str = "*"):
        return [k for k in self.data.keys() if pattern == "*" or pattern in k]
    
    async def incr(self, key: str):
        current = int(self.data.get(key, 0))
        self.data[key] = str(current + 1)
        return current + 1
    
    async def sadd(self, key: str, *values):
        if key not in self.data:
            self.data[key] = set()
        self.data[key].update(values)
    
    async def scard(self, key: str) -> int:
        return len(self.data.get(key, set()))
    
    async def smembers(self, key: str):
        return list(self.data.get(key, set()))
    
    async def hincrby(self, key: str, field: str, amount: int = 1):
        if key not in self.data:
            self.data[key] = {}
        current = int(self.data[key].get(field, 0))
        self.data[key][field] = str(current + amount)
        return current + amount

# ========== تنظیمات ==========
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GROUP_ID = int(os.getenv("GROUP_ID", 0))
    DOWNLOADER_BOT_ID = int(os.getenv("DOWNLOADER_BOT_ID", 0))
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    SPONSOR_CHANNELS = json.loads(os.getenv("SPONSOR_CHANNELS", "[]"))
    RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
    
    FREE_LIMIT = int(os.getenv("FREE_LIMIT", 3))
    PREMIUM_PRICE = os.getenv("PREMIUM_PRICE", "۲۰۰,۰۰۰ تومان")
    SUPPORT_ID = os.getenv("SUPPORT_ID", "admin")
    REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", 1))
    
    # کپشن ثابت برای همه فایل‌ها
    CUSTOM_CAPTION = "📥 ربات دانلود از اینستاگرام : @inmedia_robot"

# ========== راه‌اندازی ==========
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
db = TempDB()

# ========== سرویس مدیریت کاربر ==========
class UserService:
    @staticmethod
    async def get_user_data(user_id: int) -> dict:
        data = await db.hgetall(f"user:{user_id}")
        if not data:
            data = {
                "downloads": "0",
                "first_download_time": "0",
                "is_premium": "0",
                "referral_code": UserService.generate_referral_code(user_id),
                "referred_by": "0",
                "successful_referrals": "0",
                "bonus_downloads": "0",
                "join_date": str(int(time.time()))
            }
            await db.hset(f"user:{user_id}", data)
        return data
    
    @staticmethod
    def generate_referral_code(user_id: int) -> str:
        return f"REF{user_id}{secrets.token_hex(4)}".upper()
    
    @staticmethod
    async def check_download_limit(user_id: int) -> tuple:
        data = await UserService.get_user_data(user_id)
        
        if data.get("is_premium") == "1":
            return True, "♾️ بدون محدودیت (پریمیوم)", 999
        
        downloads = int(data.get("downloads", 0))
        first_time = int(data.get("first_download_time", 0))
        bonus = int(data.get("bonus_downloads", 0))
        
        now = int(time.time())
        if first_time == 0:
            return True, "✅ اولین دانلود", Config.FREE_LIMIT
        
        if now - first_time >= 86400:
            await UserService.reset_daily_limit(user_id)
            return True, "✅ سهمیه جدید", Config.FREE_LIMIT
        
        total_limit = Config.FREE_LIMIT + bonus
        remaining = total_limit - downloads
        
        if remaining > 0:
            return True, f"✅ {remaining} دانلود باقی مونده", remaining
        else:
            return False, "🚫 سهمیه دانلود رایگان امروز شما به پایان رسیده است.", 0
    
    @staticmethod
    async def reset_daily_limit(user_id: int):
        await db.hset(f"user:{user_id}", {
            "downloads": "0",
            "first_download_time": "0",
            "bonus_downloads": "0"
        })
    
    @staticmethod
    async def increment_download(user_id: int):
        data = await UserService.get_user_data(user_id)
        downloads = int(data.get("downloads", 0))
        first_time = int(data.get("first_download_time", 0))
        
        if first_time == 0:
            first_time = int(time.time())
        
        await db.hset(f"user:{user_id}", {
            "downloads": str(downloads + 1),
            "first_download_time": str(first_time)
        })
    
    @staticmethod
    async def add_referral_bonus(user_id: int):
        data = await UserService.get_user_data(user_id)
        bonus = int(data.get("bonus_downloads", 0))
        await db.hset(f"user:{user_id}", {"bonus_downloads": str(bonus + Config.REFERRAL_BONUS)})
    
    @staticmethod
    async def set_premium(user_id: int, status: bool):
        await db.hset(f"user:{user_id}", {"is_premium": "1" if status else "0"})
    
    @staticmethod
    async def get_stats(user_id: int) -> dict:
        data = await UserService.get_user_data(user_id)
        downloads = int(data.get("downloads", 0))
        first_time = int(data.get("first_download_time", 0))
        is_premium = data.get("is_premium") == "1"
        bonus = int(data.get("bonus_downloads", 0))
        
        remaining = Config.FREE_LIMIT + bonus - downloads
        if first_time > 0:
            elapsed = int(time.time()) - first_time
            reset_time = 86400 - elapsed
            if reset_time < 0:
                reset_time = 0
        else:
            reset_time = 0
        
        return {
            "downloads": downloads,
            "limit": Config.FREE_LIMIT + bonus,
            "remaining": max(0, remaining),
            "is_premium": is_premium,
            "bonus": bonus,
            "reset_in": reset_time,
            "referral_code": data.get("referral_code", ""),
            "successful_referrals": int(data.get("successful_referrals", 0)),
            "join_date": int(data.get("join_date", 0))
        }

# ========== پنل مدیریت ==========
class AdminPanel:
    @staticmethod
    async def get_main_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
            [InlineKeyboardButton("👑 مدیریت پریمیوم", callback_data="admin_premium_menu")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings")],
            [InlineKeyboardButton("📢 مدیریت کانال‌ها", callback_data="admin_channels")],
            [InlineKeyboardButton("📋 لیست کاربران", callback_data="admin_users")]
        ])
    
    @staticmethod
    async def get_premium_keyboard():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("➕ فعال‌سازی پریمیوم", callback_data="admin_premium_on")],
            [InlineKeyboardButton("➖ لغو پریمیوم", callback_data="admin_premium_off")],
            [InlineKeyboardButton("📋 لیست پریمیوم‌ها", callback_data="admin_list_premium")],
            [InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]
        ])

# ========== دستور پنل مدیریت ==========
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != Config.ADMIN_ID:
        await message.answer("❌ شما دسترسی به این بخش ندارید.")
        return
    
    keyboard = await AdminPanel.get_main_keyboard()
    
    total_users = len(await db.keys("user:*"))
    premium_count = 0
    for key in await db.keys("user:*"):
        data = await db.hgetall(key)
        if data.get("is_premium") == "1":
            premium_count += 1
    
    text = (
        f"🔧 **پنل مدیریت**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 ادمین: {message.from_user.first_name}\n"
        f"👥 کل کاربران: {total_users}\n"
        f"👑 کاربران پریمیوم: {premium_count}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 سهمیه رایگان: {Config.FREE_LIMIT} دانلود/روز\n"
        f"💰 قیمت اشتراک: {Config.PREMIUM_PRICE}\n"
        f"🎁 هدیه دعوت: {Config.REFERRAL_BONUS} دانلود\n"
    )
    
    await message.answer(text, reply_markup=keyboard)

# ========== هندلرهای پنل مدیریت ==========
@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    keyboard = await AdminPanel.get_main_keyboard()
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    all_users = await db.keys("user:*")
    total_users = len(all_users)
    
    premium_count = 0
    total_referrals = 0
    for key in all_users:
        data = await db.hgetall(key)
        if data.get("is_premium") == "1":
            premium_count += 1
        total_referrals += int(data.get("successful_referrals", 0))
    
    downloads_today = await db.scard(f"stats:downloads:{today}")
    
    new_users_today = 0
    for key in all_users:
        data = await db.hgetall(key)
        join_date = int(data.get("join_date", 0))
        if join_date > int(time.time()) - 86400:
            new_users_today += 1
    
    text = (
        f"📊 **آمار جامع ربات**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {total_users}\n"
        f"🆕 کاربران جدید امروز: {new_users_today}\n"
        f"👑 کاربران پریمیوم: {premium_count}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📥 دانلود امروز: {downloads_today}\n"
        f"🎁 کل دعوت‌ها: {total_referrals}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚙️ تنظیمات فعلی\n"
        f"• سهمیه رایگان: {Config.FREE_LIMIT} دانلود/روز\n"
        f"• قیمت اشتراک: {Config.PREMIUM_PRICE}\n"
        f"• هدیه دعوت: {Config.REFERRAL_BONUS} دانلود\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📅 تاریخ: {today}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_premium_menu")
async def admin_premium_menu(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    keyboard = await AdminPanel.get_premium_keyboard()
    premium_list = []
    for key in await db.keys("user:*"):
        data = await db.hgetall(key)
        if data.get("is_premium") == "1":
            user_id = key.split(":")[1]
            premium_list.append(user_id)
    
    text = (
        f"👑 **مدیریت پریمیوم**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"تعداد پریمیوم‌ها: {len(premium_list)}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📋 برای فعال‌سازی:\n"
        f"/premium [user_id] on\n\n"
        f"📋 برای لغو:\n"
        f"/premium [user_id] off"
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_premium_on")
async def admin_premium_on(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    await callback.message.answer(
        "👑 **فعال‌سازی پریمیوم**\n\n"
        "User ID کاربر رو وارد کنید:\n"
        "مثال: `123456789`"
    )
    await callback.answer()
    await db.set(f"admin_action:{callback.from_user.id}", "premium_on", ex=300)

@dp.callback_query(F.data == "admin_premium_off")
async def admin_premium_off(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    await callback.message.answer(
        "👑 **لغو پریمیوم**\n\n"
        "User ID کاربر رو وارد کنید:\n"
        "مثال: `123456789`"
    )
    await callback.answer()
    await db.set(f"admin_action:{callback.from_user.id}", "premium_off", ex=300)

@dp.callback_query(F.data == "admin_list_premium")
async def admin_list_premium(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    premium_list = []
    for key in await db.keys("user:*"):
        data = await db.hgetall(key)
        if data.get("is_premium") == "1":
            user_id = key.split(":")[1]
            try:
                user = await bot.get_chat(int(user_id))
                name = user.first_name or "بدون نام"
                premium_list.append(f"`{user_id}` - {name}")
            except:
                premium_list.append(f"`{user_id}`")
    
    if premium_list:
        text = "👑 **لیست کاربران پریمیوم**\n━━━━━━━━━━━━━━━\n" + "\n".join(premium_list[:50])
        if len(premium_list) > 50:
            text += f"\n... و {len(premium_list) - 50} نفر دیگر"
    else:
        text = "❌ هیچ کاربر پریمیومی وجود ندارد."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 برگشت", callback_data="admin_premium_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_settings")
async def admin_settings(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    text = (
        f"⚙️ **تنظیمات ربات**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 سهمیه رایگان: `{Config.FREE_LIMIT}` دانلود/روز\n"
        f"💰 قیمت اشتراک: `{Config.PREMIUM_PRICE}`\n"
        f"🎁 هدیه دعوت: `{Config.REFERRAL_BONUS}` دانلود\n"
        f"📝 کپشن ثابت: `{Config.CUSTOM_CAPTION}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💡 برای تغییر این مقادیر، متغیرهای مربوطه را در رندر آپدیت کنید.\n"
        f"⚠️ بعد از تغییر، ربات را ری‌استارت کنید."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔄 اعمال تغییرات", callback_data="admin_refresh_config")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_refresh_config")
async def admin_refresh_config(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    Config.FREE_LIMIT = int(os.getenv("FREE_LIMIT", 3))
    Config.PREMIUM_PRICE = os.getenv("PREMIUM_PRICE", "۲۰۰,۰۰۰ تومان")
    Config.REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", 1))
    Config.CUSTOM_CAPTION = os.getenv("CUSTOM_CAPTION", "📥 ربات دانلود از اینستاگرام : @inmedia_robot")
    
    await callback.message.answer(
        "✅ **تنظیمات بروزرسانی شد!**\n\n"
        f"📊 سهمیه رایگان: {Config.FREE_LIMIT}\n"
        f"💰 قیمت اشتراک: {Config.PREMIUM_PRICE}\n"
        f"🎁 هدیه دعوت: {Config.REFERRAL_BONUS}\n"
        f"📝 کپشن ثابت: {Config.CUSTOM_CAPTION}"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_channels")
async def admin_channels(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    text = "📢 **مدیریت کانال‌های اسپانسر**\n━━━━━━━━━━━━━━━\n"
    
    if Config.SPONSOR_CHANNELS:
        for channel in Config.SPONSOR_CHANNELS:
            text += f"• {channel.get('name', 'بدون نام')}: `{channel.get('id', '')}`\n"
    else:
        text += "❌ هیچ کانالی اضافه نشده است.\n"
    
    text += "\n💡 **اضافه کردن کانال:**\n"
    text += "/addchannel [id] [name]\n"
    text += "مثال: /addchannel -1001234567890 کانال فیلم"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: types.CallbackQuery):
    if callback.from_user.id != Config.ADMIN_ID:
        await callback.answer("❌ دسترسی ندارید!", show_alert=True)
        return
    
    all_users = await db.keys("user:*")
    total = len(all_users)
    
    recent_users = []
    for key in all_users[-10:]:
        data = await db.hgetall(key)
        user_id = key.split(":")[1]
        join_date = int(data.get("join_date", 0))
        if join_date > 0:
            date_str = datetime.fromtimestamp(join_date).strftime("%Y-%m-%d %H:%M")
        else:
            date_str = "نامشخص"
        
        try:
            user = await bot.get_chat(int(user_id))
            name = user.first_name or "بدون نام"
            recent_users.append(f"`{user_id}` - {name} ({date_str})")
        except:
            recent_users.append(f"`{user_id}` ({date_str})")
    
    text = (
        f"📋 **لیست کاربران**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {total}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 **۱۰ کاربر اخیر:**\n" + "\n".join(recent_users)
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔙 برگشت", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# ========== هندلر دریافت User ID برای پریمیوم ==========
@dp.message(F.text.regexp(r"^\d+$"))
async def handle_user_id_input(message: types.Message):
    user_id = message.from_user.id
    action = await db.get(f"admin_action:{user_id}")
    
    if not action:
        return
    
    target_user_id = int(message.text)
    
    if action == "premium_on":
        await UserService.set_premium(target_user_id, True)
        await message.answer(f"✅ کاربر {target_user_id} پریمیوم شد!")
        try:
            await bot.send_message(
                target_user_id,
                f"🎉 **تبریک!**\n\nاشتراک مادام‌العمر شما فعال شد.\n♾️ از این پس بدون محدودیت دانلود کنید."
            )
        except:
            pass
        
    elif action == "premium_off":
        await UserService.set_premium(target_user_id, False)
        await message.answer(f"✅ اشتراک کاربر {target_user_id} لغو شد!")
        try:
            await bot.send_message(
                target_user_id,
                f"⚠️ اشتراک شما لغو شد.\nاز این پس محدودیت {Config.FREE_LIMIT} دانلود در روز دارید."
            )
        except:
            pass
    
    await db.delete(f"admin_action:{user_id}")

# ========== میدلور عضویت اجباری ==========
@dp.message(F.chat.type == "private")
async def check_force_join(message: types.Message, next_handler):
    if not message.text or not any(x in message.text.lower() for x in ["instagram", "youtube", "tiktok", "facebook", "twitter", "x.com", "start"]):
        return await next_handler()
    
    if message.text.startswith("/"):
        return await next_handler()
    
    user_id = message.from_user.id
    
    for channel in Config.SPONSOR_CHANNELS:
        try:
            member = await bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(f"📢 عضویت در {channel['name']}", url=f"https://t.me/{channel['id'].replace('-100', '')}")],
                    [InlineKeyboardButton("🔄 بررسی مجدد", callback_data="check_join")]
                ])
                await message.answer(
                    f"🚨 لطفاً ابتدا در کانال {channel['name']} عضو شوید",
                    reply_markup=keyboard
                )
                return
        except:
            pass
    
    await next_handler()

# ========== میدلور چک محدودیت ==========
@dp.message(F.chat.type == "private")
async def check_limits_middleware(message: types.Message, next_handler):
    if not message.text or not any(x in message.text.lower() for x in ["instagram", "youtube", "tiktok", "facebook", "twitter", "x.com"]):
        return await next_handler()
    
    user_id = message.from_user.id
    
    can_download, msg, remaining = await UserService.check_download_limit(user_id)
    
    if not can_download:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("1️⃣ دعوت از دوستان +1 دانلود", callback_data=f"referral_{user_id}")],
            [InlineKeyboardButton("2️⃣ خرید اشتراک نامحدود", callback_data="buy_premium")]
        ])
        
        await message.answer(
            f"🚫 {msg}\n\n"
            f"📊 سهمیه رایگان: {Config.FREE_LIMIT} دانلود/روز\n"
            f"💰 قیمت اشتراک: {Config.PREMIUM_PRICE}\n\n"
            f"برای ادامه، یکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=keyboard
        )
        return
    
    if remaining <= 1:
        await message.answer(f"⚠️ {msg}\nبرای افزایش سهمیه از گزینه دعوت استفاده کنید.")
    
    await next_handler()

# ========== هندلر دعوت ==========
@dp.callback_query(F.data.startswith("referral_"))
async def handle_referral(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ این لینک برای شما نیست!", show_alert=True)
        return
    
    data = await UserService.get_user_data(user_id)
    referral_code = data.get("referral_code")
    
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📤 اشتراک‌گذاری", url=f"tg://msg?text={referral_link}")],
        [InlineKeyboardButton("📋 کپی لینک", callback_data=f"copy_link_{referral_code}")]
    ])
    
    await callback.message.edit_text(
        f"🎁 **لینک دعوت شما**\n\n"
        f"🔗 {referral_link}\n\n"
        f"📌 اگر ۱ نفر از طریق این لینک وارد شود، {Config.REFERRAL_BONUS} دانلود به سهمیه شما اضافه می‌شود.\n\n"
        f"✅ تعداد دعوت‌های موفق: {data.get('successful_referrals', 0)}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("copy_link_"))
async def copy_referral_link(callback: types.CallbackQuery):
    await callback.answer("لینک کپی شد! ✅", show_alert=True)

# ========== هندلر خرید اشتراک ==========
@dp.callback_query(F.data == "buy_premium")
async def handle_buy_premium(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📞 ارتباط با پشتیبانی", url=f"https://t.me/{Config.SUPPORT_ID}")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        f"♾ **اشتراک نامحدود مادام‌العمر**\n\n"
        f"با خرید اشتراک مادام‌العمر، بدون هیچ محدودیتی از ربات استفاده کنید.\n\n"
        f"💰 هزینه اشتراک: {Config.PREMIUM_PRICE}\n\n"
        f"✅ پس از خرید، اشتراک شما فعال می‌شود.",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# ========== هندلر استارت ==========
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    await UserService.get_user_data(user_id)
    
    if len(args) > 1 and args[1].startswith("ref_"):
        referral_code = args[1].replace("ref_", "")
        
        for key in await db.keys("user:*"):
            data = await db.hgetall(key)
            if data.get("referral_code") == referral_code:
                referrer_id = int(key.split(":")[1])
                
                if referrer_id != user_id:
                    user_data = await UserService.get_user_data(user_id)
                    if user_data.get("referred_by") == "0":
                        await UserService.add_referral_bonus(referrer_id)
                        await db.hset(f"user:{user_id}", {"referred_by": str(referrer_id)})
                        await db.hincrby(f"user:{referrer_id}", "successful_referrals", 1)
                        
                        await message.answer("🎉 **تبریک!** شما با موفقیت دعوت شدید!")
                        
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"🎉 **دعوت موفق!**\nکاربر {message.from_user.first_name} وارد شد.\n✅ {Config.REFERRAL_BONUS} دانلود به سهمیه شما اضافه شد."
                            )
                        except:
                            pass
                        break
    
    welcome = (
        f"🎯 **به ربات دانلودر خوش آمدید!**\n\n"
        f"📥 لینک خود را ارسال کنید تا فایل را برایتان دانلود کنم.\n\n"
        f"🔹 پشتیبانی از:\n"
        f"• اینستاگرام\n• یوتیوب\n• تیک‌تاک\n• فیسبوک\n• توییتر/X\n\n"
        f"📊 سهمیه رایگان: {Config.FREE_LIMIT} دانلود در ۲۴ ساعت\n"
        f"💰 قیمت اشتراک: {Config.PREMIUM_PRICE}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📊 وضعیت من", callback_data="my_status")]
    ])
    
    await message.answer(welcome, reply_markup=keyboard)

# ========== وضعیت کاربر ==========
@dp.callback_query(F.data == "my_status")
async def show_status(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    stats = await UserService.get_stats(user_id)
    
    status_text = "👑 **پریمیوم**" if stats["is_premium"] else "🆓 **رایگان**"
    
    text = (
        f"📊 **وضعیت شما**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 کاربر: {callback.from_user.first_name}\n"
        f"📌 وضعیت: {status_text}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📥 دانلود امروز: {stats['downloads']}\n"
        f"📈 سقف مجاز: {stats['limit']}\n"
        f"✅ باقی‌مانده: {stats['remaining']}\n"
    )
    
    if not stats["is_premium"]:
        reset_minutes = stats['reset_in'] // 60
        reset_hours = reset_minutes // 60
        text += f"⏰ زمان ریست: {reset_hours} ساعت دیگر\n"
        text += f"🎁 دانلود هدیه: {stats['bonus']}\n"
        text += f"👥 دعوت موفق: {stats['successful_referrals']}\n"
    
    text += f"━━━━━━━━━━━━━━━\n"
    text += f"🔑 کد دعوت: `{stats['referral_code']}`"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎁 دریافت لینک دعوت", callback_data=f"referral_{user_id}")],
        ([InlineKeyboardButton("♾️ خرید اشتراک", callback_data="buy_premium")] if not stats["is_premium"] else [])
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# ========== هندلر لینک ==========
@dp.message(F.text & (F.text.contains("instagram.com") | F.text.contains("youtube.com") | 
                       F.text.contains("tiktok.com") | F.text.contains("facebook.com") | 
                       F.text.contains("twitter.com") | F.text.contains("x.com")))
async def handle_link(message: types.Message):
    user_id = message.from_user.id
    link = message.text
    request_id = f"req_{user_id}_{int(time.time())}"
    
    await UserService.increment_download(user_id)
    
    await db.hset(f"request:{request_id}", {
        "user_id": user_id,
        "link": link,
        "status": "pending",
        "timestamp": time.time()
    })
    
    await message.answer("⏳ در حال پردازش لینک شما...")
    
    group_msg = await bot.send_message(
        chat_id=Config.GROUP_ID,
        text=f"📥 {link}"
    )
    
    await db.set(f"group_msg:{group_msg.message_id}", request_id, ex=120)
    asyncio.create_task(timeout_handler(request_id, user_id, group_msg.message_id))

# ========== تایم‌اوت ==========
async def timeout_handler(request_id: str, user_id: int, msg_id: int):
    await asyncio.sleep(120)
    status = await db.hget(f"request:{request_id}", "status")
    if status == "pending":
        await bot.send_message(user_id, "⏰ زمان دانلود تمام شد. لطفاً دوباره تلاش کنید.")
        await db.delete(f"request:{request_id}")
        await db.delete(f"group_msg:{msg_id}")
        try:
            await bot.delete_message(Config.GROUP_ID, msg_id)
        except:
            pass

# ========== گوش دادن به گروه ==========
@dp.message(F.chat.id == Config.GROUP_ID)
async def handle_group(message: types.Message):
    # فقط پیام‌های دانلودر
    if message.from_user.id != Config.DOWNLOADER_BOT_ID:
        return
    
    if not message.reply_to_message:
        return
    
    replied_id = message.reply_to_message.message_id
    request_id = await db.get(f"group_msg:{replied_id}")
    if not request_id:
        return
    
    request_data = await db.hgetall(f"request:{request_id}")
    if not request_data:
        return
    
    user_id = int(request_data["user_id"])
    
    # خطا؟
    if message.text and ("error" in message.text.lower() or "❌" in message.text):
        await bot.send_message(user_id, f"❌ خطا: {message.text}")
        await cleanup(request_id, replied_id, message.message_id)
        return
    
    # ========== کپشن ثابت شما ==========
    custom_caption = Config.CUSTOM_CAPTION
    
    try:
        if message.video:
            await bot.send_video(user_id, message.video.file_id, caption=custom_caption)
        elif message.photo:
            await bot.send_photo(user_id, message.photo[-1].file_id, caption=custom_caption)
        elif message.document:
            await bot.send_document(user_id, message.document.file_id, caption=custom_caption)
        elif message.audio:
            await bot.send_audio(user_id, message.audio.file_id, caption=custom_caption)
        elif message.voice:
            await bot.send_voice(user_id, message.voice.file_id)
        elif message.animation:
            await bot.send_animation(user_id, message.animation.file_id, caption=custom_caption)
        else:
            await bot.send_message(user_id, "⚠️ فرمت فایل پشتیبانی نمی‌شود")
            return
        
        # ثبت آمار
        today = datetime.now().strftime('%Y-%m-%d')
        await db.sadd(f"stats:downloads:{today}", user_id)
        
    except Exception as e:
        await bot.send_message(user_id, f"❌ خطا در ارسال فایل: {str(e)}")
    
    await cleanup(request_id, replied_id, message.message_id)

# ========== پاک‌سازی ==========
async def cleanup(request_id: str, link_msg_id: int, downloader_msg_id: int):
    await db.delete(f"request:{request_id}")
    await db.delete(f"group_msg:{link_msg_id}")
    try:
        await bot.delete_message(Config.GROUP_ID, link_msg_id)
        await bot.delete_message(Config.GROUP_ID, downloader_msg_id)
    except:
        pass

# ========== هندلرهای عضویت ==========
@dp.callback_query(F.data == "check_join")
async def check_join_callback(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    all_joined = True
    for channel in Config.SPONSOR_CHANNELS:
        try:
            member = await bot.get_chat_member(channel["id"], user_id)
            if member.status in ["left", "kicked"]:
                all_joined = False
                break
        except:
            all_joined = False
    
    if all_joined:
        await callback.message.edit_text("✅ عضویت شما تأیید شد!")
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("❌ هنوز عضو نشدید!", show_alert=True)

# ========== دستورات ادمین ==========
@dp.message(Command("premium"))
async def set_premium(message: types.Message):
    if message.from_user.id != Config.ADMIN_ID:
        await message.answer("❌ شما دسترسی به این دستور ندارید.")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "❌ فرمت: /premium <user_id> [on/off]\n"
            "مثال: /premium 123456789 on"
        )
        return
    
    user_id = int(parts[1])
    status = parts[2].lower() if len(parts) > 2 else "on"
    
    await UserService.set_premium(user_id, status == "on")
    
    try:
        if status == "on":
            await bot.send_message(
                user_id,
                f"🎉 **تبریک!**\n\nاشتراک مادام‌العمر شما فعال شد.\n♾️ از این پس بدون محدودیت دانلود کنید."
            )
        else:
            await bot.send_message(
                user_id,
                f"⚠️ اشتراک شما لغو شد.\nاز این پس محدودیت {Config.FREE_LIMIT} دانلود در روز دارید."
            )
    except:
        pass
    
    await message.answer(f"✅ وضعیت کاربر {user_id}: {'فعال' if status == 'on' else 'غیرفعال'}")

@dp.message(Command("addchannel"))
async def add_channel(message: types.Message):
    if message.from_user.id != Config.ADMIN_ID:
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("❌ فرمت: /addchannel <id> <نام>")
        return
    
    await message.answer(
        f"✅ کانال اضافه شد!\n\n"
        f"⚠️ متغیر `SPONSOR_CHANNELS` رو در رندر آپدیت کنید:\n"
        f"```json\n{json.dumps([*Config.SPONSOR_CHANNELS, {'id': parts[1], 'name': parts[2]}], ensure_ascii=False)}\n```",
        parse_mode="Markdown"
    )

# ========== راه‌اندازی ==========
async def on_startup():
    webhook_url = f"{Config.RENDER_EXTERNAL_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    print(f"✅ Bot started!")
    print(f"📢 Group ID: {Config.GROUP_ID}")
    print(f"📊 Free Limit: {Config.FREE_LIMIT} downloads/day")
    print(f"💰 Premium Price: {Config.PREMIUM_PRICE}")
    print(f"📝 Custom Caption: {Config.CUSTOM_CAPTION}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    aiohttp_server.run_app(
        dispatcher=dp,
        host="0.0.0.0",
        port=port,
        on_startup=on_startup
    )

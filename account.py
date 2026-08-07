from pyrogram import Client, filters
import re
import os

# ============================================
# 🔧 خواندن تنظیمات از متغیرهای محیطی (رندر)
# ============================================
API_ID = int(os.environ.get("API_ID", 1234567))
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "+989123456789")
GROUP_ID = int(os.environ.get("GROUP_ID", -1001234567890))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MyInstaDownloaderBot")
# ============================================

# ساخت کلاینت
app = Client(
    "my_account",
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE_NUMBER
)

@app.on_message(filters.private & filters.text)
async def forward_to_group(client, message):
    if message.sender.username != BOT_USERNAME:
        return
    
    text = message.text
    code_match = re.search(r'🆔 کد:\s*(\S+)', text)
    link_match = re.search(r'🔗 لینک:\s*(https?://\S+)', text)
    
    if code_match and link_match:
        code = code_match.group(1)
        link = link_match.group(1)
        
        try:
            await client.send_message(
                chat_id=GROUP_ID,
                text=f"{code}\n{link}"
            )
            print(f"✅ ارسال شد به گروه | کد: {code}")
        except Exception as e:
            print(f"❌ خطا: {e}")

print("👤 اکانت شخصی شروع به کار کرد...")
print(f"📋 گروه: {GROUP_ID}")
print(f"🤖 ربات: @{BOT_USERNAME}")
print("=" * 40)

app.run()

import subprocess
import sys
import time

print("🚀 در حال اجرا...")
print("=" * 40)

p1 = subprocess.Popen([sys.executable, "account.py"])
print("✅ اکانت شخصی روشن شد")

time.sleep(2)

p2 = subprocess.Popen([sys.executable, "bot.py"])
print("✅ ربات اصلی روشن شد")

print("=" * 40)
print("✅ همه چیز اجرا شد!")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n⏹️ در حال خاموش کردن...")
    p1.terminate()
    p2.terminate()

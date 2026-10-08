"""
Script đăng ký Helius Webhook để theo dõi token mới.
Chạy 1 lần: python setup_webhook.py
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_PUBLIC_URL", "").strip()  # URL công khai của bot

if not HELIUS_API_KEY:
    print("❌ Chưa có HELIUS_API_KEY trong .env")
    exit(1)

if not WEBHOOK_URL:
    print("❌ Chưa có WEBHOOK_PUBLIC_URL trong .env")
    print("   Ví dụ: WEBHOOK_PUBLIC_URL=https://abc123.ngrok.io/webhook/helius")
    exit(1)

url = f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={HELIUS_API_KEY}"

payload = {
    "webhookURL": WEBHOOK_URL,
    "transactionTypes": ["TOKEN_MINT"],
    "accountAddresses": [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # SPL Token Program
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun Program
    ],
    "webhookType": "enhanced",
    "authHeader": "",  # Tùy chọn: thêm secret để bảo mật
}

print(f"📡 Đang đăng ký webhook tại: {WEBHOOK_URL}")
try:
    r = httpx.post(url, json=payload, timeout=20)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
    if r.status_code in (200, 201):
        print("✅ Webhook đã được đăng ký thành công!")
    else:
        print("❌ Có lỗi xảy ra")
except Exception as e:
    print(f"❌ Lỗi: {e}")
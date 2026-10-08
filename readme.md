🤖 Meme Trading Bot
Bot tự động giao dịch meme coin trên Solana, tích hợp AI phân tích, theo dõi KOL, webhook token mới, và giao dịch qua GMGN.

📋 Mục lục
Tính năng chính

Kiến trúc hệ thống

Yêu cầu hệ thống

Cài đặt

Cấu hình .env

Chạy bot

Truy cập Dashboard

Cấu hình Telegram Bot

Cấu hình GMGN (giao dịch thật)

Cấu hình Helius Webhook

Cấu hình Gemini AI

Cấu hình Twitter Scraper

Profiles theo vốn

Cấu trúc thư mục

Chiến lược giao dịch

Câu lệnh API

Khắc phục sự cố

Bảo mật

Roadmap

✨ Tính năng chính
Tính năng	Mô tả
🔍 Phát hiện token mới	Theo dõi DexScreener, GeckoTerminal, Helius Webhook theo thời gian thực
🛡️ Lọc token rác	RugCheck + DexScreener: mint/freeze authority, LP lock, top holder
🐦 Theo dõi KOL Twitter	Scrape tweet từ 10+ KOL crypto mà không cần API key
🤖 Phân tích AI	Google Gemini chấm điểm token và đưa ra quyết định BUY/SKIP
💰 Giao dịch tự động	Paper trading (mô phỏng) hoặc GMGN live (mainnet thật)
📱 Thông báo Telegram	Nhận tin nhắn và bấm nút Hold/Sell ngay trên Telegram
📊 Dashboard web	Theo dõi vị thế, log, tin tức, candidates theo thời gian thực
🎯 Chống trượt giá	Slippage bảo vệ (mặc định 30%) cho mọi giao dịch
💎 Quản lý vị thế	Đóng từng phần (25%/50%/100%) trực tiếp từ dashboard
⚡ Tối ưu tài nguyên	Pre-score, cache, adaptive polling cho vốn nhỏ
🏗️ Kiến trúc hệ thống
text
┌──────────────────────────────────────────────────────────┐
│  NGUỒN DỮ LIỆU                                            │
│  ├─ Helius Webhook (token mới - realtime)                │
│  ├─ DexScreener API (token profiles + boosts)            │
│  ├─ GeckoTerminal API (pool mới)                         │
│  ├─ Twitter Scraper (KOL shill)                          │
│  └─ cryptocurrency.cv (tin tức)                          │
└──────────────────┬───────────────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────────────┐
│  PIPELINE XỬ LÝ                                           │
│  1. Lọc rác (RugCheck + DexScreener)                     │
│  2. Chấm shill score (từ KOL mentions)                   │
│  3. Pre-score local → chỉ gọi AI nếu vượt ngưỡng         │
│  4. Gemini phân tích → BUY/SKIP                          │
│  5. Execute buy qua GMGN hoặc Paper                      │
└──────────────────┬───────────────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────────────┐
│  GIÁM SÁT & QUYẾT ĐỊNH                                    │
│  ├─ Price watcher (mỗi 3-15s)                            │
│  ├─ TP tự động (+40%) cho x1.5                           │
│  ├─ Hỏi user cho x2/x3 đạt +40%                          │
│  └─ SL tự động (-35%)                                    │
└──────────────────┬───────────────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────────────┐
│  GIAO DIỆN                                                │
│  ├─ Dashboard (localhost:8000)                           │
│  └─ Telegram Bot (nút Hold/Sell + commands)              │
└──────────────────────────────────────────────────────────┘
💻 Yêu cầu hệ thống
Thành phần	Tối thiểu	Khuyến nghị
OS	Windows 10, macOS 11, Ubuntu 20.04	Windows 11 / macOS 13+
Python	3.10	3.11 hoặc 3.12
Node.js	18	20 LTS (cho gmgn-cli)
RAM	2 GB	4 GB
Ổ cứng	500 MB	1 GB
Mạng	Ổn định, không chặn Telegram	—
🚀 Cài đặt
1. Clone hoặc tạo thư mục dự án
powershell
mkdir D:\meme-bot
cd D:\meme-bot
2. Tạo môi trường ảo
Windows (PowerShell):

powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
Windows (CMD):

cmd
python -m venv venv
venv\Scripts\activate.bat
Linux/macOS:

bash
python3 -m venv venv
source venv/bin/activate
⚠️ Nếu PowerShell báo lỗi execution policy, chạy 1 lần:

powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
3. Cài đặt dependencies
powershell
pip install -r requirements.txt
Nếu gặp xung đột, cài từng cái:

powershell
pip install fastapi uvicorn jinja2 python-dotenv google-generativeai httpx websockets solana solders base58 twifork
4. Tạo file .env
Copy file mẫu và điền thông tin của bạn:

powershell
Copy-Item .env.example .env
notepad .env
5. Cài Node.js + gmgn-cli (chỉ khi giao dịch thật)
Cài Node 20 qua nvm (khuyến nghị):

bash
# Linux/macOS
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
Windows: Tải nvm-windows tại https://github.com/coreybutler/nvm-windows/releases

Cài gmgn-cli:

powershell
npm install -g gmgn-cli
gmgn-cli config --apply YOUR_GMGN_API_KEY
gmgn-cli config --check
⚙️ Cấu hình .env
Tạo file .env trong thư mục gốc dự án với nội dung:

env
# ==================================================
# PROFILE VỐN (small | medium | large)
# ==================================================
BOT_PROFILE=small

# ==================================================
# GOOGLE GEMINI (miễn phí, ~30 calls/ngày)
# Lấy tại: https://aistudio.google.com/app/apikey
# ==================================================
GEMINI_API_KEY=

# ==================================================
# TELEGRAM (nhận thông báo + nút Hold/Sell)
# Tạo bot với @BotFather, lấy chat_id từ getUpdates
# ==================================================
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ==================================================
# HELIUS (webhook token mới, miễn phí 1M credits/tháng)
# Lấy tại: https://dev.helius.xyz/dashboard/app
# ==================================================
HELIUS_API_KEY=

# ==================================================
# TWITTER SCRAPER (auth_token từ browser, không cần API key)
# F12 trên X → Application → Cookies → auth_token
# ==================================================
TWITTER_AUTH_TOKEN=

# ==================================================
# GMGN (giao dịch thật trên mainnet)
# Lấy tại: https://gmgn.ai → Settings → API
# ==================================================
GMGN_API_KEY=

# ==================================================
# VÍ SOLANA (chỉ khi giao dịch thật)
# Export từ Phantom: Settings → Security → Export Private Key
# ⚠️ DÙNG VÍ PHỤ, KHÔNG DÙNG VÍ CHÍNH
# ==================================================
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
WALLET_PRIVATE_KEY=

# ==================================================
# WEBHOOK (dùng ngrok để có URL công khai)
# ==================================================
WEBHOOK_PUBLIC_URL=
WEBHOOK_SECRET=
Bảng mô tả biến môi trường
Biến	Bắt buộc	Mô tả
BOT_PROFILE	✅	small / medium / large tùy vốn
GEMINI_API_KEY	Khuyến nghị	Nếu trống → dùng heuristic
TELEGRAM_BOT_TOKEN	Tùy chọn	Không có → bot chạy không thông báo
TELEGRAM_CHAT_ID	Tùy chọn	Đi kèm với token
HELIUS_API_KEY	Khuyến nghị	Có → nhận webhook token mới
TWITTER_AUTH_TOKEN	Tùy chọn	Có → theo dõi KOL shill
GMGN_API_KEY	Chỉ khi giao dịch thật	Không có → paper trading
WALLET_PRIVATE_KEY	Chỉ khi giao dịch thật	Bắt buộc cho GMGN live
WEBHOOK_PUBLIC_URL	Tùy chọn	Dùng với Helius webhook
▶️ Chạy bot
powershell
python app.py
Log khởi động mong đợi:

text
[INIT] 🚀 Bot khởi động | profile=small | max_pos=5
[INIT] GMGN: ⚠️ chưa config
[WARN] Chưa có GMGN_API_KEY → paper trading
[WARN] Chưa có GEMINI_API_KEY → fallback heuristic
[INIT] 📱 Telegram polling đã bật
[TG] Polling bắt đầu
INFO:     Uvicorn running on http://127.0.0.1:8000
Bot sẽ chạy liên tục. Nhấn Ctrl + C để dừng.

Chạy lại bot sạch (khi port bị chiếm)
Windows:

powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
python app.py
Linux/macOS:

bash
pkill -f "python app.py"
sleep 2
python app.py
📊 Truy cập Dashboard
Mở trình duyệt: http://127.0.0.1:8000

Bố cục dashboard
text
┌──────────────────────────────────────────────────────────┐
│  HEADER: Ví USDC | Tổng giá trị | PnL | Vị thế mở       │
├───────────────┬─────────────────────┬────────────────────┤
│  Cột 1        │  Cột 2              │  Cột 3             │
│  ├─ Stats     │  ├─ Decisions       │  ├─ News feed      │
│  └─ Log       │  ├─ Candidates      │  │                 │
│               │  ├─ Positions       │  │                 │
│               │  └─ Trades          │  │                 │
└───────────────┴─────────────────────┴────────────────────┘
Các card chính
Card	Nội dung
Hiệu suất tối ưu	Số token detected, filtered, Gemini calls, cache hits
Log	60 dòng log gần nhất, màu theo level
Cần quyết định	Token đạt +40% cần bạn chọn Hold/Sell
Token theo dõi	Candidates đang chờ AI phân tích
Vị thế mở	Các token đang nắm giữ + nút đóng 25/50/100%
Giao dịch	Lịch sử 30 giao dịch gần nhất
News feed	Tin tức crypto + phân tích AI
Nút đóng vị thế
Mỗi vị thế có 3 nút:

Đóng 25% — chốt lời từng phần

Đóng 50% — giảm rủi ro

Đóng hết — thoát hoàn toàn

📱 Cấu hình Telegram Bot
Bước 1: Tạo bot
Mở Telegram → tìm @BotFather

Gõ /newbot → đặt tên → nhận token dạng 7123456789:AAH...

Copy token

Bước 2: Lấy chat ID
Nhắn tin bất kỳ cho bot vừa tạo (ví dụ: hi)

Mở URL: https://api.telegram.org/bot<TOKEN>/getUpdates

Tìm "chat":{"id":123456789 → đó là chat ID

Bước 3: Thêm vào .env
env
TELEGRAM_BOT_TOKEN=7123456789:AAH...
TELEGRAM_CHAT_ID=123456789
Bước 4: Test
Restart bot, sau đó chạy:

powershell
curl.exe -X POST http://127.0.0.1:8000/api/test/telegram
Bạn sẽ nhận tin 🧪 Test từ Meme Bot.

Commands trên Telegram
Lệnh	Chức năng
/status	Xem số dư + số vị thế + số trades
/positions	Danh sách vị thế đang mở
/pending	Xem lại các quyết định đang chờ
Nút bấm khi token đạt target
text
❓ BONK đạt +55.0%
Entry: $0.000012 → Now: $0.000019
Tiềm năng: x2
Shill: 65
_Meme coin với LP locked 95%, 3 KOL lớn shill_

Giữ tiếp hay chốt lời?

[💎 GIỮ TIẾP]  [💰 CHỐT LỜI]
Bấm nút → bot xử lý và sửa tin nhắn gốc.

💰 Cấu hình GMGN (giao dịch thật)
Bước 1: Lấy GMGN API key
Đăng ký https://gmgn.ai

Vào Settings → API hoặc https://gmgn.ai/ai

Nhấn Generate API Key → copy

Bước 2: Cấu hình gmgn-cli
powershell
gmgn-cli config --apply YOUR_GMGN_API_KEY
gmgn-cli config --check
Nếu config --check không báo lỗi → OK.

Bước 3: Thêm vào .env
env
GMGN_API_KEY=your_actual_key
WALLET_PRIVATE_KEY=your_base58_private_key
Bước 4: Restart bot
Log sẽ đổi từ:

text
[INIT] GMGN: ⚠️ chưa config
thành:

text
[INIT] GMGN: ✅ OK
Bước 5: Test giao dịch thật
⚠️ CHỈ LÀM KHI ĐÃ TEST PAPER TRADING ÍT NHẤT 3 NGÀY

powershell
curl.exe -X POST http://127.0.0.1:8000/api/test/force-buy
Theo dõi log để xem lệnh có được thực thi trên mainnet không.

Chuyển đổi paper ↔ live
Trong .env:

Paper trading: để trống GMGN_API_KEY và WALLET_PRIVATE_KEY

Live trading: điền cả hai

📡 Cấu hình Helius Webhook
Để không bỏ lỡ token mới, dùng Helius webhook.

Bước 1: Cài ngrok
Tải tại https://ngrok.com/download → giải nén → thêm vào PATH.

powershell
ngrok config add-authtoken YOUR_NGROK_TOKEN
Bước 2: Chạy ngrok
powershell
# Terminal riêng
ngrok http 8000
Copy URL: https://abc123.ngrok-free.app

Bước 3: Cập nhật .env
env
WEBHOOK_PUBLIC_URL=https://abc123.ngrok-free.app/webhook/helius
Bước 4: Đăng ký webhook
Tạo file setup_webhook.py:

python
import os, httpx
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("HELIUS_API_KEY", "").strip()
URL = os.getenv("WEBHOOK_PUBLIC_URL", "").strip()

if not API_KEY or not URL:
    print("❌ Thiếu HELIUS_API_KEY hoặc WEBHOOK_PUBLIC_URL")
    exit(1)

endpoint = f"https://api-mainnet.helius-rpc.com/v0/webhooks?api-key={API_KEY}"
payload = {
    "webhookURL": URL,
    "transactionTypes": ["TOKEN_MINT"],
    "accountAddresses": [
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    ],
    "webhookType": "enhanced",
}
r = httpx.post(endpoint, json=payload, timeout=20)
print(f"Status: {r.status_code}")
print(r.text[:300])
Chạy:

powershell
python setup_webhook.py
Bước 5: Kiểm tra
Log bot sẽ hiện:

text
[WEBHOOK] 📥 Nhận webhook: 3 sự kiện
[WEBHOOK] 🔍 Token mới từ webhook: 7xKXtg2C...
🤖 Cấu hình Gemini AI
Lấy API key miễn phí tại https://aistudio.google.com/app/apikey

Copy key (bắt đầu bằng AIza...)

Thêm vào .env:

env
GEMINI_API_KEY=AIzaSy...
Giới hạn free tier
Model	RPM	RPD
gemini-2.0-flash	15	1500
gemini-1.5-flash	15	1500
Bot tự động retry sang model 2 nếu model 1 hết quota. Nếu cả 2 fail → cooldown 15 phút → dùng heuristic.

Test Gemini
powershell
python -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
m = genai.GenerativeModel('gemini-2.0-flash')
print(m.generate_content('Trả lời OK').text)
"
🐦 Cấu hình Twitter Scraper
Bot scrape tweet từ các KOL mà không cần API key trả phí.

Bước 1: Lấy auth_token
Đăng nhập X (Twitter) trên browser

Nhấn F12 → tab Application

Cookies → https://x.com

Tìm cookie auth_token → copy giá trị

Bước 2: Thêm vào .env
env
TWITTER_AUTH_TOKEN=abc123def456...
Danh sách KOL mặc định
Sửa trong config.py — biến DEFAULT_KOLS:

python
DEFAULT_KOLS = [
    "elonmusk", "cz_binance", "VitalikButerin",
    "MustStopMurad", "blknoiz06", ...
]
📊 Profiles theo vốn
Bot có 3 profile tự động điều chỉnh tham số. Đổi trong .env:

env
BOT_PROFILE=small   # vốn $50-200
BOT_PROFILE=medium  # vốn $200-1000
BOT_PROFILE=large   # vốn > $1000
Tham số	small	medium	large
Max positions	5	5	10
Trade amount	$10	$20	$50
Profit target	+40%	+50%	+60%
Stop loss	-35%	-40%	-40%
Gemini min score	70	60	50
Poll interval	30s	15s	10s
Price watcher idle	60s	30s	15s
Đổi thủ công
Trong dashboard, nhấn vào ô Cài đặt để sửa trực tiếp. Hoặc gọi API:

powershell
curl.exe -X POST http://127.0.0.1:8000/api/settings ^
  -H "Content-Type: application/json" ^
  -d "{\"max_positions\": 3, \"trade_amount_usd\": 5}"
📁 Cấu trúc thư mục
text
meme-bot/
├── .env                      # Cấu hình (KHÔNG commit)
├── .env.example              # Mẫu .env
├── .gitignore
├── requirements.txt
├── README.md                 # File này
├── app.py                    # Backend chính
├── config.py                 # Profiles + hằng số
├── setup_webhook.py          # Script đăng ký Helius webhook
├── modules/
│   ├── __init__.py
│   ├── leak_detector.py      # Phát hiện token mới
│   ├── token_filter.py       # Lọc token rác
│   ├── shill_detector.py     # Scrape KOL Twitter
│   ├── wallet_manager.py     # Kết nối ví Solana
│   ├── gmgn_trader.py        # Wrapper gmgn-cli
│   ├── telegram_bot.py       # Bot Telegram tương tác
│   └── optimizer.py          # Cache + adaptive interval
└── templates/
    └── index.html            # Dashboard UI
🎯 Chiến lược giao dịch
Quy trình xử lý token
text
[Token mới] → [Lọc rác] → [Shill score] → [Pre-score] → [Gemini AI] → [Buy/Skip]
              ↓ reject     ↓ reject        ↓ skip       ↓ skip
Điều kiện mua
Bot CHỈ mua khi đồng thời:

✅ auto_trade = True

✅ Token qua lọc rác (mint/freeze revoked, LP lock, liquidity ≥ $5k)

✅ pre_score ≥ 70 (profile small)

✅ Gemini trả về BUY (hoặc heuristic ≥ 75)

✅ len(positions) < max_positions

✅ Đủ USDC/SOL

Điều kiện bán
Điều kiện	Hành động
Lãi ≥ 40% VÀ potential = x1.5	Bán tự động
Lãi ≥ 40% VÀ potential = x2/x3	Hỏi user qua dashboard + Telegram
Lỗ ≤ -35%	Bán tự động (stop loss)
User bấm "Chốt lời"	Bán ngay
User bấm "Đóng 25/50%"	Bán một phần
Chống trượt giá
Slippage mặc định: 30%

Có thể đổi trong .env hoặc dashboard

Với token biến động mạnh, có thể tăng lên 50%

🔌 Câu lệnh API
State & thông tin
powershell
# Xem toàn bộ state
curl.exe http://127.0.0.1:8000/api/state

# Xem ví
curl.exe http://127.0.0.1:8000/api/wallet
Test
powershell
# Test Telegram
curl.exe -X POST http://127.0.0.1:8000/api/test/telegram

# Test force buy
curl.exe -X POST http://127.0.0.1:8000/api/test/force-buy

# Test decision (gửi nút Telegram)
curl.exe -X POST http://127.0.0.1:8000/api/test/decision
Quản lý vị thế
powershell
# Đóng toàn bộ
curl.exe -X POST "http://127.0.0.1:8000/api/position/MINT_ADDRESS/close?percentage=100"

# Đóng 50%
curl.exe -X POST "http://127.0.0.1:8000/api/position/MINT_ADDRESS/close?percentage=50"

# Đóng 25%
curl.exe -X POST "http://127.0.0.1:8000/api/position/MINT_ADDRESS/close?percentage=25"
Settings
powershell
# Đổi max positions + trade amount
curl.exe -X POST http://127.0.0.1:8000/api/settings ^
  -H "Content-Type: application/json" ^
  -d "{\"max_positions\": 5, \"trade_amount_usd\": 10}"

# Bật/tắt auto trade
curl.exe -X POST http://127.0.0.1:8000/api/settings ^
  -H "Content-Type: application/json" ^
  -d "{\"auto_trade\": false}"
Reset
powershell
# Reset ví paper về $100
curl.exe -X POST http://127.0.0.1:8000/api/reset
Quyết định từ dashboard
powershell
# Giữ tiếp
curl.exe -X POST "http://127.0.0.1:8000/api/decision/DEC_ID/hold"

# Chốt lời
curl.exe -X POST "http://127.0.0.1:8000/api/decision/DEC_ID/sell"
🔧 Khắc phục sự cố
Port 8000 đã bị chiếm
powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
python app.py
ModuleNotFoundError
powershell
# Đảm bảo đang trong venv (thấy (venv) ở đầu prompt)
pip install -r requirements.txt

# Hoặc cài từng cái
pip install fastapi uvicorn jinja2 python-dotenv google-generativeai httpx websockets solana solders base58 twifork
Bot chạy nhưng không có log
Windows console có thể không hiển thị Unicode. Đã fix sẵn bằng sys.stdout = io.TextIOWrapper(...). Nếu vẫn lỗi:

powershell
$env:PYTHONIOENCODING = "utf-8"
python app.py
Telegram WinError 10054
ISP chặn Telegram. Cài Cloudflare WARP tại https://1.1.1.1/ → bật WARP → thử lại.

Gemini 429 (hết quota)
Đợi 15 phút (bot tự cooldown) hoặc nâng cấp Gemini paid. Hoặc giảm số token gọi Gemini bằng cách tăng gemini_min_pre_score.

Token không có symbol (UNKNOWN)
DexScreener chưa update. Đợi 5-10 phút, bot sẽ tự enrich lại.

gmgn-cli lỗi EACCES
powershell
mkdir ~/.npm-global
npm config set prefix ~/.npm-global
# Thêm vào PATH: ~/.npm-global/bin
npm install -g gmgn-cli
Webhook không nhận dữ liệu
Kiểm tra ngrok còn chạy không

Kiểm tra URL trong .env có /webhook/helius không

Test thủ công:

powershell
curl.exe -X POST http://127.0.0.1:8000/webhook/helius ^
  -H "Content-Type: application/json" ^
  -d "[{\"type\":\"TOKEN_MINT\",\"tokenTransfers\":[{\"mint\":\"test123\"}]}]"
🔐 Bảo mật
Nguyên tắc vàng
KHÔNG BAO GIỜ chia sẻ WALLET_PRIVATE_KEY với bất kỳ ai

KHÔNG BAO GIỜ commit file .env lên GitHub

KHÔNG BAO GIỜ dùng ví chính cho bot — luôn dùng ví phụ

CHỈ nạp số tiền bạn sẵn sàng mất (meme coin rủi ro cao)

File .gitignore bắt buộc
gitignore
.env
venv/
__pycache__/
*.pyc
*.log
telegram_failed.log
run.log
bot.log
Ví phụ an toàn
Tạo ví Phantom mới

Nạp $50-100 SOL

Export private key → paste vào .env

Test paper trading 3 ngày

Chỉ bật GMGN live khi đã hiểu rõ logic

🗺️ Roadmap
Đã có ✅
Phát hiện token đa nguồn (DexScreener, GeckoTerminal, Helius)

Lọc rác với RugCheck

AI phân tích Gemini

Telegram với nút bấm

Dashboard web

GMGN integration

Đóng vị thế từng phần

Sắp tới 🚧
□ Auto-trailing stop
□ Multi-chain (BSC, Base)
□ Backtesting mode
□ Ví theo dõi KOL on-chain (CabalSpy/MadeOnSol)
□ Chart realtime trên dashboard
□ Export báo cáo PnL ra CSV
Ý tưởng 💡
□ Machine learning dự đoán rug pull
□ Copy trade ví whale
□ Discord integration
□ Mobile app
📞 Hỗ trợ
Nếu gặp vấn đề:

Kiểm tra log trong terminal và dashboard

Chạy các lệnh test API ở trên

Xem mục Khắc phục sự cố

Kiểm tra .env đã đầy đủ chưa

⚠️ Tuyên bố miễn trách
Bot này được cung cấp "nguyên trạng" cho mục đích học tập và nghiên cứu.

Giao dịch meme coin CỰC KỲ RỦI RO. Bạn có thể mất 100% vốn.

Tác giả KHÔNG CHỊU TRÁCH NHIỆM cho bất kỳ tổn thất nào.

KHÔNG BAO GIỜ đầu tư số tiền bạn không thể mất.

Luôn kiểm tra code trước khi chạy bằng tiền thật.

Đây không phải lời khuyên đầu tư.

Made with ❤️ for meme coin degens

Version 0.1.0 — Cập nhật: 2026

Phản hồi này do AI tạo ra, chỉ mang tính tham khảo.

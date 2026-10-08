"""
Cấu hình theo mức vốn. Đổi BOT_PROFILE trong .env để chuyển.
"""
import os

PROFILES = {
    "small": {
        # Polling
        "poll_interval_base": 30,
        "poll_interval_min": 20,
        "poll_interval_max": 180,
        # Gemini
        "gemini_min_pre_score": 70,
        "gemini_cache_ttl": 7200,
        # Twitter
        "twitter_kols_to_scan": 3,
        "twitter_scan_interval": 600,
        # Price watcher
        "price_watcher_idle": 60,
        "price_watcher_active": 15,
        # Position
        "max_positions": 5,
        "trade_amount_usd": 10.0,
        "profit_target_pct": 40.0,
        "stop_loss_pct": -35.0,
    },
    "medium": {
        "poll_interval_base": 15,
        "poll_interval_min": 10,
        "poll_interval_max": 90,
        "gemini_min_pre_score": 60,
        "gemini_cache_ttl": 3600,
        "twitter_kols_to_scan": 5,
        "twitter_scan_interval": 300,
        "price_watcher_idle": 30,
        "price_watcher_active": 8,
        "max_positions": 5,
        "trade_amount_usd": 20.0,
        "profit_target_pct": 50.0,
        "stop_loss_pct": -40.0,
    },
    "large": {
        "poll_interval_base": 10,
        "poll_interval_min": 5,
        "poll_interval_max": 60,
        "gemini_min_pre_score": 50,
        "gemini_cache_ttl": 1800,
        "twitter_kols_to_scan": 10,
        "twitter_scan_interval": 120,
        "price_watcher_idle": 15,
        "price_watcher_active": 3,
        "max_positions": 10,
        "trade_amount_usd": 50.0,
        "profit_target_pct": 60.0,
        "stop_loss_pct": -40.0,
    },
}

ACTIVE_PROFILE_NAME = os.getenv("BOT_PROFILE", "small")
ACTIVE_PROFILE = PROFILES.get(ACTIVE_PROFILE_NAME, PROFILES["small"])

# Hằng số chung
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LAMPORTS_PER_SOL = 1_000_000_000

# KOLs mặc định
DEFAULT_KOLS = [
    "elonmusk", "cz_binance", "VitalikButerin", "aeyakovenko",
    "MustStopMurad", "blknoiz06", "notthreadguy", "CryptoHayes",
    "Rewkang", "Pentosh1",
]
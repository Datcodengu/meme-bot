"""
Tiện ích tối ưu tài nguyên: cache, adaptive interval, pre-score.
"""
import time
from typing import Dict, Optional


class AdaptiveInterval:
    """
    Tự điều chỉnh interval dựa trên hoạt động.
    Khi có event → giảm interval. Khi idle lâu → tăng interval.
    """
    def __init__(self, base: int, min_interval: int, max_interval: int):
        self.base = base
        self.min = min_interval
        self.max = max_interval
        self.current = base
        self.last_event = time.time()

    def on_event(self):
        self.last_event = time.time()
        self.current = max(self.min, int(self.current * 0.7))

    def on_idle(self):
        idle_min = (time.time() - self.last_event) / 60
        if idle_min > 30:
            self.current = min(self.max, int(self.current * 1.3))
        elif idle_min > 10:
            self.current = min(self.max, int(self.current * 1.1))

    def get(self) -> int:
        return self.current


class TTLCache:
    """Cache đơn giản với TTL, dùng cho Gemini và các API khác."""
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._data: Dict[str, tuple] = {}  # key -> (value, timestamp)

    def get(self, key: str) -> Optional[dict]:
        if key not in self._data:
            return None
        value, ts = self._data[key]
        if time.time() - ts > self.ttl:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: dict):
        self._data[key] = (value, time.time())

    def cleanup(self):
        now = time.time()
        expired = [k for k, (_, ts) in self._data.items() if now - ts > self.ttl]
        for k in expired:
            del self._data[k]
        return len(expired)


def pre_score(candidate: dict) -> int:
    """
    Chấm điểm sơ bộ 0-100 bằng dữ liệu local (không gọi API).
    Chỉ token vượt ngưỡng mới được đưa vào Gemini.
    """
    f = candidate.get("filter", {})
    s = candidate.get("shill", {})
    m = f.get("metrics", {})
    score = 0

    # Thanh khoản (0-25)
    liq = m.get("liquidity", 0)
    if liq >= 50_000: score += 25
    elif liq >= 20_000: score += 20
    elif liq >= 10_000: score += 15
    elif liq >= 5_000: score += 10

    # Volume (0-20)
    vol = m.get("volume_24h", 0)
    if vol >= 100_000: score += 20
    elif vol >= 50_000: score += 15
    elif vol >= 20_000: score += 10
    elif vol >= 10_000: score += 5

    # Risk score (0-25)
    risk = f.get("score", 100)
    if risk <= 10: score += 25
    elif risk <= 20: score += 20
    elif risk <= 30: score += 15
    elif risk <= 40: score += 5

    # Shill (0-30)
    score += min(s.get("score", 0), 30)

    # Bonus
    if m.get("lp_locked_pct", 0) >= 90: score += 5
    if m.get("top_holder_pct", 100) <= 10: score += 5

    return min(score, 100)
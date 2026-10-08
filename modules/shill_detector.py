import re
import asyncio
import time
from datetime import datetime, timedelta
from collections import defaultdict

from config import ACTIVE_PROFILE, DEFAULT_KOLS


class ShillDetector:
    """
    Scrape X qua twikit. Chỉ scan khi có yêu cầu (on-demand) để tiết kiệm tài nguyên.
    """
    def __init__(self, auth_token: str = "", window_minutes: int = 60):
        self.auth_token = auth_token
        self.window = timedelta(minutes=window_minutes)
        self.mentions: dict = defaultdict(list)
        self.seen_tweet_ids: set = set()
        self._client = None
        self.scan_cache: dict = {}   # handle -> last_scan_ts
        self.queue: asyncio.Queue = asyncio.Queue()

    def _get_client(self):
        if self._client is None:
            try:
                from twikit import Client
                self._client = Client("en-US")
            except Exception as e:
                print(f"[Shill] twikit error: {e}")
        return self._client

    def _extract_cashtags(self, text: str):
        return re.findall(r"\$([A-Za-z]{2,12})", text)

    def _extract_addresses(self, text: str):
        return re.findall(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text)

    async def _scan_user(self, handle: str) -> list:
        client = self._get_client()
        if not client:
            return []
        signals = []
        try:
            if self.auth_token and not getattr(client, "_logged_in", False):
                try:
                    await client.login(auth_info_1=self.auth_token)
                    client._logged_in = True
                except Exception as e:
                    print(f"[Shill] login error: {e}")
                    return []

            user = await client.get_user_by_screen_name(handle)
            if not user:
                return []
            tweets = await client.get_user_tweets(user.id, "Tweets", count=10)

            for t in tweets or []:
                tid = str(t.id)
                if tid in self.seen_tweet_ids:
                    continue
                self.seen_tweet_ids.add(tid)

                text = t.text or ""
                tags = self._extract_cashtags(text)
                addrs = self._extract_addresses(text)
                if not tags and not addrs:
                    continue

                likes = getattr(t, "favorite_count", 0) or 0
                signals.append({
                    "kol": handle, "text": text[:200],
                    "cashtags": tags, "addresses": addrs,
                    "likes": likes,
                    "time": datetime.now().strftime("%H:%M:%S"),
                })

                for addr in addrs:
                    self.mentions[addr].append(
                        {"kol": handle, "time": datetime.now(), "likes": likes}
                    )
                for tag in tags:
                    self.mentions[f"${tag.upper()}"].append(
                        {"kol": handle, "time": datetime.now(), "likes": likes}
                    )
        except Exception as e:
            print(f"[Shill] {handle}: {str(e)[:80]}")
        return signals

    def get_shill_score(self, key: str) -> dict:
        now = datetime.now()
        recent = [m for m in self.mentions.get(key, []) if now - m["time"] <= self.window]
        if not recent:
            return {"count": 0, "unique_kols": 0, "total_likes": 0, "score": 0, "kols": []}
        unique_kols = len(set(m["kol"] for m in recent))
        total_likes = sum(m["likes"] for m in recent)
        score = min(unique_kols * 20, 40) + min(len(recent) * 5, 30) + min(total_likes / 100, 30)
        return {
            "count": len(recent), "unique_kols": unique_kols,
            "total_likes": total_likes, "score": round(score, 1),
            "kols": list(set(m["kol"] for m in recent)),
        }

    async def request_scan(self, symbol: str, mint: str):
        """Gọi khi có candidate cần check shill."""
        await self.queue.put({"symbol": symbol, "mint": mint})

    async def _worker(self):
        """Worker chạy nền, chỉ xử lý khi queue có item."""
        while True:
            try:
                req = await self.queue.get()
                handle_limit = ACTIVE_PROFILE["twitter_kols_to_scan"]
                min_interval = ACTIVE_PROFILE["twitter_scan_interval"]

                for handle in DEFAULT_KOLS[:handle_limit]:
                    last = self.scan_cache.get(handle, 0)
                    if time.time() - last < min_interval:
                        continue
                    await self._scan_user(handle)
                    self.scan_cache[handle] = time.time()
                    await asyncio.sleep(3)  # delay giữa các KOL
                self.queue.task_done()
            except Exception as e:
                print(f"[Shill] worker: {e}")

    def start_worker(self):
        asyncio.create_task(self._worker())
import asyncio
import json
import re
import httpx
from datetime import datetime
from typing import Callable, Optional, Dict

from config import ACTIVE_PROFILE
from modules.optimizer import AdaptiveInterval

HELIUS_WS_TEMPLATE = "wss://mainnet.helius-rpc.com/?api-key={key}"

DEXSCREENER_PROFILES = "https://api.dexscreener.com/token-profiles/latest/v1"
DEXSCREENER_BOOSTS = "https://api.dexscreener.com/token-boosts/latest/v1"
DEXSCREENER_TOKEN = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
GECKO_NEW_POOLS = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"

PROGRAMS = {
    "pumpfun": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "raydium_amm": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "raydium_cpmm": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Cache info theo mint để tránh gọi lại
_info_cache: Dict[str, dict] = {}


async def fetch_token_info(mint: str) -> dict:
    """Lấy symbol, name, price, liq từ DexScreener cho 1 mint. Có cache."""
    if mint in _info_cache:
        return _info_cache[mint]

    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                DEXSCREENER_TOKEN.format(mint=mint),
                headers=HEADERS,
            )
            if r.status_code != 200:
                _info_cache[mint] = {}
                return {}

            data = r.json()
            pairs = data.get("pairs") or []
            if not pairs:
                _info_cache[mint] = {}
                return {}

            # Chọn pair có liquidity cao nhất
            pair = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0)
            base = pair.get("baseToken") or {}
            quote = pair.get("quoteToken") or {}

            info = {
                "symbol": base.get("symbol", "UNKNOWN"),
                "name": base.get("name", ""),
                "price": float(pair.get("priceUsd") or 0),
                "liquidity": float((pair.get("liquidity") or {}).get("usd", 0) or 0),
                "volume_24h": float((pair.get("volume") or {}).get("h24", 0) or 0),
                "pair_address": pair.get("pairAddress"),
                "dex": pair.get("dexId"),
                "quote_symbol": quote.get("symbol", "SOL"),
            }
            _info_cache[mint] = info
            return info
    except Exception as e:
        print(f"[Leak] fetch_token_info({mint[:8]}): {str(e)[:100]}", flush=True)
        _info_cache[mint] = {}
        return {}


class LeakDetector:
    def __init__(self, api_key: str, on_token: Callable):
        self.api_key = api_key
        self.on_token = on_token
        self.seen_mints: set = set()
        self.running = False
        self.poll = AdaptiveInterval(
            base=ACTIVE_PROFILE["poll_interval_base"],
            min_interval=ACTIVE_PROFILE["poll_interval_min"],
            max_interval=ACTIVE_PROFILE["poll_interval_max"],
        )

    async def _emit_token(self, source: str, mint: str, extra: dict = None):
        """Enrich token info rồi gửi vào pipeline."""
        info = await fetch_token_info(mint)
        payload = {
            "source": source,
            "mint": mint,
            "symbol": (info.get("symbol") or "UNKNOWN").upper(),
            "name": info.get("name", ""),
            "price": info.get("price") or (extra or {}).get("price"),
            "liquidity": info.get("liquidity") or (extra or {}).get("liquidity", 0),
            "volume_24h": info.get("volume_24h", 0),
            "dex": info.get("dex", ""),
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        if extra:
            payload.update({k: v for k, v in extra.items() if k not in payload})
        await self.on_token(payload)

    # =========================================================
    # NGUỒN 1: DexScreener profiles
    # =========================================================
    async def _dexscreener_profiles(self):
        await asyncio.sleep(3)
        while self.running:
            found = False
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(DEXSCREENER_PROFILES, headers=HEADERS)
                    print(f"[Leak] profiles: {r.status_code} len={len(r.text)}", flush=True)
                    if r.status_code == 200:
                        data = r.json()
                        new_mints = []
                        for tok in data if isinstance(data, list) else []:
                            if tok.get("chainId") != "solana":
                                continue
                            mint = tok.get("tokenAddress")
                            if mint and mint not in self.seen_mints:
                                self.seen_mints.add(mint)
                                new_mints.append(mint)

                        for mint in new_mints[:5]:
                            await self._emit_token("dexscreener_profile", mint)
                            found = True
                            await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[Leak] profiles error: {str(e)[:120]}", flush=True)

            if found:
                self.poll.on_event()
            else:
                self.poll.on_idle()
            await asyncio.sleep(self.poll.get())

    # =========================================================
    # NGUỒN 2: DexScreener boosts
    # =========================================================
    async def _dexscreener_boosts(self):
        await asyncio.sleep(5)
        while self.running:
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(DEXSCREENER_BOOSTS, headers=HEADERS)
                    print(f"[Leak] boosts: {r.status_code} len={len(r.text)}", flush=True)
                    if r.status_code == 200:
                        data = r.json()
                        for tok in data if isinstance(data, list) else []:
                            if tok.get("chainId") != "solana":
                                continue
                            mint = tok.get("tokenAddress")
                            if mint and mint not in self.seen_mints:
                                self.seen_mints.add(mint)
                                await self._emit_token(
                                    "dexscreener_boost", mint,
                                    {"is_boosted": True},
                                )
                                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[Leak] boosts error: {str(e)[:120]}", flush=True)
            await asyncio.sleep(120)

    # =========================================================
    # NGUỒN 3: GeckoTerminal new pools
    # =========================================================
    async def _geckoterminal_new_pools(self):
        await asyncio.sleep(7)
        while self.running:
            found = False
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(
                        GECKO_NEW_POOLS,
                        headers={**HEADERS, "Accept": "application/json;version=20230302"},
                    )
                    print(f"[Leak] gecko: {r.status_code} len={len(r.text)}", flush=True)
                    if r.status_code == 200:
                        data = r.json()
                        pools = data.get("data", []) if isinstance(data, dict) else []
                        for pool in pools[:10]:
                            attrs = pool.get("attributes", {})
                            base_id = None

                            # Parse từ relationships
                            rels = pool.get("relationships", {}).get("base_token", {})
                            if rels:
                                rid = rels.get("data", {}).get("id", "")
                                if "_" in rid:
                                    base_id = rid.split("_", 1)[1]

                            # Fallback: parse từ pool id
                            if not base_id:
                                pid = pool.get("id", "")
                                if "_" in pid:
                                    base_id = pid.split("_", 1)[1]

                            if base_id and base_id not in self.seen_mints:
                                self.seen_mints.add(base_id)
                                found = True
                                await self._emit_token(
                                    "geckoterminal_new_pool", base_id,
                                    {"price": attrs.get("base_token_price_usd")},
                                )
                                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[Leak] gecko error: {str(e)[:120]}", flush=True)

            if found:
                self.poll.on_event()
            else:
                self.poll.on_idle()
            await asyncio.sleep(self.poll.get())

    # =========================================================
    # NGUỒN 4: Helius WebSocket
    # =========================================================
    async def _helius_stream(self):
        try:
            import websockets
        except ImportError:
            return
        if not self.api_key:
            return

        ws_url = HELIUS_WS_TEMPLATE.format(key=self.api_key)
        sub_msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": list(PROGRAMS.values())},
                {"commitment": "confirmed"},
            ],
        }

        while self.running:
            try:
                async with websockets.connect(ws_url, ping_interval=30) as ws:
                    await ws.send(json.dumps(sub_msg))
                    print("[Leak] Helius WS connected", flush=True)
                    async for raw in ws:
                        msg = json.loads(raw)
                        logs = msg.get("params", {}).get("result", {}).get("value", {})
                        if not logs:
                            continue
                        mint = self._extract_mint(logs)
                        if mint and mint not in self.seen_mints:
                            self.seen_mints.add(mint)
                            self.poll.on_event()
                            await self._emit_token("helius_ws", mint)
            except Exception as e:
                print(f"[Leak] WS error: {str(e)[:120]}", flush=True)
                await asyncio.sleep(5)

    def _extract_mint(self, logs: dict) -> Optional[str]:
        for line in logs.get("logs", []):
            m = re.findall(r"[1-9A-HJ-NP-Za-km-z]{32,44}", line)
            if m:
                return m[0]
        return None

    async def run(self):
        self.running = True
        tasks = [
            self._dexscreener_profiles(),
            self._geckoterminal_new_pools(),
            self._dexscreener_boosts(),
        ]
        if self.api_key:
            tasks.append(self._helius_stream())
        await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self):
        self.running = False
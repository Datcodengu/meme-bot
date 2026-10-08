import httpx
import asyncio

RUGCHECK_BASE = "https://api.rugcheck.xyz/v1"
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"


class TokenFilter:
    def __init__(self, settings: dict):
        self.settings = settings

    async def _rugcheck(self, mint: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{RUGCHECK_BASE}/tokens/{mint}/report")
                if r.status_code != 200:
                    return {"safe": False, "reason": f"RugCheck HTTP {r.status_code}"}
                return r.json()
        except Exception as e:
            return {"safe": False, "reason": f"RugCheck: {str(e)[:60]}"}

    async def _dexscreener(self, mint: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{DEXSCREENER_BASE}/tokens/{mint}")
                data = r.json()
            pairs = data.get("pairs") or []
            if not pairs:
                return {"safe": False, "reason": "Không có pair"}
            pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
            return {
                "safe": True,
                "price": pair.get("priceUsd"),
                "liquidity": pair.get("liquidity", {}).get("usd", 0),
                "volume_24h": pair.get("volume", {}).get("h24", 0),
                "price_change_1h": pair.get("priceChange", {}).get("h1", 0),
                "pair_address": pair.get("pairAddress"),
            }
        except Exception as e:
            return {"safe": False, "reason": f"DexScreener: {str(e)[:60]}"}

    async def is_safe(self, mint: str) -> dict:
        rug, dex = await asyncio.gather(
            self._rugcheck(mint),
            self._dexscreener(mint),
        )

        if not dex.get("safe"):
            return {"safe": False, "reason": dex.get("reason"), "metrics": dex}

        score = rug.get("score_normalised", 100)
        mint_auth = rug.get("mint_authority")
        freeze_auth = rug.get("freeze_authority")
        lp_locked = rug.get("lp_locked_pct", 0)
        top_holder = rug.get("top_holder_pct", 100)

        s = self.settings
        checks = {
            "risk_ok": score <= s.get("max_risk_score", 30),
            "mint_revoked": mint_auth is None,
            "freeze_revoked": freeze_auth is None,
            "liquidity_ok": dex["liquidity"] >= s.get("min_liquidity_usd", 5000),
            "volume_ok": dex["volume_24h"] >= s.get("min_volume_24h_usd", 10000),
            "top_holder_ok": top_holder <= s.get("max_top_holder_pct", 25),
            "lp_locked_ok": lp_locked >= s.get("min_lp_lock_pct", 70),
        }

        critical = ["mint_revoked", "freeze_revoked", "liquidity_ok"]
        critical_ok = all(checks[c] for c in critical)

        return {
            "safe": critical_ok and sum(checks.values()) >= 5,
            "checks": checks,
            "score": score,
            "metrics": {
                "liquidity": dex["liquidity"],
                "volume_24h": dex["volume_24h"],
                "price": dex["price"],
                "price_change_1h": dex["price_change_1h"],
                "lp_locked_pct": lp_locked,
                "top_holder_pct": top_holder,
                "mint_authority": mint_auth,
                "freeze_authority": freeze_auth,
            },
        }
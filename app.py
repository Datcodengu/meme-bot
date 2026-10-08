"""
Meme Trading Bot — Tối ưu tài nguyên cho vốn nhỏ.
"""
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
import json
import asyncio
import random
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
import httpx

from config import ACTIVE_PROFILE, ACTIVE_PROFILE_NAME
from modules.leak_detector import LeakDetector
from modules.token_filter import TokenFilter
from modules.shill_detector import ShillDetector
from modules.wallet_manager import WalletManager
from modules.gmgn_trader import GMGNTrader
from modules.telegram_bot import TelegramBot
from modules.optimizer import TTLCache, pre_score

load_dotenv()

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ============================================================
# STATE
# ============================================================
class State:
    def __init__(self):
        self.paper_usdc = 100.0
        self.initial_usdc = 100.0
        self.positions: Dict[str, dict] = {}
        self.trades: List[dict] = []
        self.logs: List[dict] = []
        self.pending_decisions: List[dict] = []
        self.candidate_tokens: List[dict] = []
        self.news_feed: List[dict] = []
        self.gemini_cache = TTLCache(ttl_seconds=ACTIVE_PROFILE["gemini_cache_ttl"])

        self.settings = {
            "trade_amount_usd": ACTIVE_PROFILE["trade_amount_usd"],
            "profit_target_pct": 50.0,   # ← đổi thành 50 để milestone là 50/100/150
            "stop_loss_pct": ACTIVE_PROFILE["stop_loss_pct"],
            "slippage_pct": 30.0,
            "auto_trade": True,
            "use_gmgn": True,
            "chain": "sol",
            "max_positions": 5,
            "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
            "helius_api_key": os.getenv("HELIUS_API_KEY", ""),
            "twitter_auth_token": os.getenv("TWITTER_AUTH_TOKEN", ""),
            "gmgn_api_key": os.getenv("GMGN_API_KEY", ""),
            "max_risk_score": 30,
            "min_liquidity_usd": 5000,
            "min_volume_24h_usd": 10000,
            "min_lp_lock_pct": 70,
            "max_top_holder_pct": 25,
            "min_shill_score": 30,
            "shill_window_minutes": 60,
            "gemini_min_pre_score": ACTIVE_PROFILE["gemini_min_pre_score"],
        }

        self.stats = {
            "tokens_detected": 0,
            "tokens_filtered": 0,
            "tokens_pre_skip": 0,
            "gemini_calls": 0,
            "gemini_cache_hits": 0,
            "trades_executed": 0,
        }

    def log(self, level: str, message: str):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level, "message": message,
        }
        self.logs.insert(0, entry)
        self.logs = self.logs[:200]
        print(f"[{entry['time']}] [{level}] {message}", flush=True)


state = State()
wallet = WalletManager()


# ============================================================
# TOKEN PIPELINE
# ============================================================
class TokenPipeline:
    def __init__(self, state: State, wallet: WalletManager):
        self.state = state
        self.wallet = wallet
        self.filter = TokenFilter(state.settings)
        self.shill = ShillDetector(
            auth_token=state.settings.get("twitter_auth_token", ""),
            window_minutes=state.settings.get("shill_window_minutes", 60),
        )
        self.leak = LeakDetector(
            api_key=state.settings.get("helius_api_key", ""),
            on_token=self.on_leak,
        )
        self.trader = GMGNTrader(
            api_key=state.settings.get("gmgn_api_key", ""),
            chain="sol",
        )
        self.tg = TelegramBot(
            token=state.settings.get("telegram_bot_token", ""),
            chat_id=state.settings.get("telegram_chat_id", ""),
        )
        self.tg.on_callback = self.handle_telegram_callback
        self.tg.on_command = self.handle_telegram_command

    # ---------------------------------------------------------
    # PIPELINE
    # ---------------------------------------------------------
    async def on_leak(self, token: dict):
        mint = token["mint"]
        symbol = token.get("symbol", "?")
        self.state.stats["tokens_detected"] += 1

        filter_result = await self.filter.is_safe(mint)
        if not filter_result.get("safe"):
            self.state.stats["tokens_filtered"] += 1
            self.state.log("FILTER",
                f"❌ {symbol} bị lọc: "
                f"{filter_result.get('reason') or 'vi phạm tiêu chí an toàn'}")
            return

        if symbol == "UNKNOWN" or not symbol:
            try:
                from modules.leak_detector import fetch_token_info
                info = await fetch_token_info(mint)
                if info.get("symbol") and info["symbol"] != "UNKNOWN":
                    symbol = info["symbol"].upper()
                    token["symbol"] = symbol
                    token["name"] = info.get("name", "")
            except Exception:
                pass

        metrics = filter_result.get("metrics", {})
        self.state.log("FILTER",
            f"✅ {symbol} qua lọc | liq=${metrics.get('liquidity',0):,.0f} "
            f"vol=${metrics.get('volume_24h',0):,.0f} "
            f"risk={filter_result.get('score')}")

        shill = self.shill.get_shill_score(mint)
        if token.get("symbol"):
            by_tag = self.shill.get_shill_score(f"${symbol.upper()}")
            if by_tag["score"] > shill["score"]:
                shill = by_tag

        if shill["score"] < self.state.settings["min_shill_score"] and self.state.settings.get("twitter_auth_token"):
            await self.shill.request_scan(symbol, mint)

        candidate = {
            **token,
            "filter": filter_result,
            "shill": shill,
            "detected_at": datetime.now().strftime("%H:%M:%S"),
            "analysis": None,
        }
        self.state.candidate_tokens.insert(0, candidate)
        self.state.candidate_tokens = self.state.candidate_tokens[:50]

        pre = pre_score(candidate)
        candidate["pre_score"] = pre
        threshold = self.state.settings["gemini_min_pre_score"]

        if pre < threshold:
            self.state.stats["tokens_pre_skip"] += 1
            self.state.log("SKIP",
                f"⏭️ {symbol} pre_score={pre} < {threshold} → bỏ qua")
            return

        self.state.log("PRE", f"⭐ {symbol} pre_score={pre} → gọi AI")

        analysis = await self.analyze_with_gemini(candidate)
        candidate["analysis"] = analysis

        self.state.news_feed.insert(0, {
            "id": mint[:10],
            "time": candidate["detected_at"],
            "source": token["source"],
            "kol": ", ".join(shill["kols"][:3]) if shill["kols"] else "—",
            "text": (f"[{token['source']}] {symbol} — "
                     f"liq=${metrics.get('liquidity',0):,.0f}, "
                     f"shill={shill['score']}, risk={filter_result.get('score')}"),
            "token_symbol": symbol,
            "token_address": mint,
            "initial_price": float(metrics.get("price") or 0.0001),
            "analysis": analysis,
            "shill": shill,
            "filter": filter_result,
            "pre_score": pre,
        })
        self.state.news_feed = self.state.news_feed[:50]

        self.state.log("AI",
            f"🤖 {symbol} → {analysis['decision']} "
            f"(score {analysis['score']}, {analysis['potential']}) — {analysis['reasoning']}")

        if analysis["decision"] == "BUY" and self.state.settings["auto_trade"]:
            await self.execute_buy(candidate, analysis)

    # ---------------------------------------------------------
    # GEMINI
    # ---------------------------------------------------------
    async def analyze_with_gemini(self, candidate: dict) -> dict:
        mint = candidate.get("mint", "")
        api_key = self.state.settings.get("gemini_api_key", "").strip()

        cached = self.state.gemini_cache.get(mint)
        if cached:
            self.state.stats["gemini_cache_hits"] += 1
            cached = cached.copy()
            cached["cached"] = True
            return cached

        if not api_key or not GEMINI_AVAILABLE:
            return self._fallback_analysis(candidate)

        if getattr(self, "_gemini_cooldown_until", 0) > time.time():
            remaining = int(self._gemini_cooldown_until - time.time())
            self.state.log("AI", f"⏸️ Gemini cooldown còn {remaining}s")
            return self._fallback_analysis(candidate)

        try:
            self.state.stats["gemini_calls"] += 1
            genai.configure(api_key=api_key)
            models = ["gemini-2.0-flash", "gemini-1.5-flash"]
            last_error = None

            for model_name in models:
                try:
                    model = genai.GenerativeModel(model_name)
                    m = candidate.get("filter", {}).get("metrics", {})
                    s = candidate.get("shill", {})
                    lp_str = f"{m.get('lp_locked_pct')}%" if m.get('lp_locked_pct') is not None else "không có dữ liệu"
                    top_str = f"{m.get('top_holder_pct')}%" if m.get('top_holder_pct') is not None else "không có dữ liệu"

                    prompt = f"""Phân tích meme coin Solana. Chỉ trả JSON.

Token: {candidate.get('symbol')} ({candidate.get('name')})
Mint: {candidate.get('mint')}
Nguồn: {candidate.get('source')}

AN TOÀN:
- Risk: {candidate.get('filter',{}).get('score')}/100
- Liq: ${m.get('liquidity',0):,.0f} | Vol24h: ${m.get('volume_24h',0):,.0f}
- LP locked: {lp_str}
- Top holder: {top_str}
- Mint revoked: {m.get('mint_authority') is None}
- Freeze revoked: {m.get('freeze_authority') is None}

SHILL:
- Score: {s.get('score',0)}/100 | KOLs: {s.get('unique_kols',0)} | Mentions: {s.get('count',0)}

LƯU Ý: Nếu trường nào ghi "không có dữ liệu", ĐỪNG tự bịa số.

Trả JSON: {{"score": <0-100>, "decision": "BUY"|"SKIP", "potential": "x1.5"|"x2"|"x3", "reasoning": "<tiếng Việt <150 ký tự>", "confidence": <0-100>}}"""

                    resp = await asyncio.to_thread(model.generate_content, prompt)
                    txt = resp.text.strip()
                    if "```" in txt:
                        txt = txt.split("```")[1]
                        if txt.startswith("json"):
                            txt = txt[4:]
                    result = json.loads(txt.strip())
                    result["engine"] = f"gemini/{model_name}"
                    result["cached"] = False
                    self.state.gemini_cache.set(mint, result)
                    self.state.log("AI",
                        f"✅ {model_name}: {result['decision']} score={result['score']} "
                        f"| {result['reasoning'][:70]}")
                    return result
                except Exception as e:
                    err_str = str(e)
                    last_error = err_str
                    if "429" in err_str or "quota" in err_str.lower():
                        self.state.log("WARN", f"⚠️ {model_name} hết quota, thử model khác...")
                        continue
                    break

            self._gemini_cooldown_until = time.time() + 900
            self.state.log("ERROR", f"❌ Gemini thất bại: {str(last_error)[:150]}")
            return self._fallback_analysis(candidate)

        except Exception as e:
            self.state.log("ERROR", f"❌ Gemini: {str(e)[:200]}")
            return self._fallback_analysis(candidate)

    def _fallback_analysis(self, candidate: dict) -> dict:
        shill = candidate.get("shill", {}).get("score", 0)
        risk = candidate.get("filter", {}).get("score", 100)
        liq = candidate.get("filter", {}).get("metrics", {}).get("liquidity", 0)

        score = 50
        if shill >= 50: score += 20
        elif shill >= 30: score += 10
        if risk <= 15: score += 20
        elif risk <= 30: score += 10
        if liq >= 30_000: score += 10
        elif liq >= 10_000: score += 5
        score = min(score, 95)

        result = {
            "score": score,
            "decision": "BUY" if score >= 75 else "SKIP",
            "potential": "x3" if score >= 88 else ("x2" if score >= 80 else "x1.5"),
            "reasoning": f"[Heuristic] shill={shill} risk={risk} liq=${liq:,.0f}",
            "confidence": score,
            "engine": "heuristic",
            "cached": False,
        }
        self.state.gemini_cache.set(candidate.get("mint", ""), result)
        return result

    # ---------------------------------------------------------
    # BUY
    # ---------------------------------------------------------
    async def execute_buy(self, candidate: dict, analysis: dict) -> Optional[dict]:
        mint = candidate["mint"]
        symbol = candidate.get("symbol", "?")

        self.state.log("BUY?",
            f"🔔 Thử mua {symbol} | positions={len(self.state.positions)}/"
            f"{self.state.settings['max_positions']} | "
            f"paper=${self.state.paper_usdc:.2f}")

        max_pos = self.state.settings["max_positions"]
        if len(self.state.positions) >= max_pos:
            self.state.log("SKIP",
                f"⏸️ Đã có {len(self.state.positions)}/{max_pos} vị thế → bỏ qua {symbol}")
            return None

        if mint in self.state.positions:
            self.state.log("SKIP", f"⏸️ Đã có vị thế {symbol}")
            return None

        amount_usd = self.state.settings["trade_amount_usd"]
        slippage = self.state.settings["slippage_pct"]
        use_gmgn = self.state.settings.get("use_gmgn", True)
        price = float(candidate.get("filter", {}).get("metrics", {}).get("price") or 0.0001)

        if use_gmgn and self.state.settings.get("gmgn_api_key"):
            amount_sol = amount_usd / 150.0
            result = await self.trader.buy(mint, amount_sol, slippage)
            if not result["ok"]:
                self.state.log("ERROR",
                    f"❌ GMGN buy {symbol}: {result.get('error','')[:120]}")
                return None
            mode = "GMGN"
        else:
            if self.state.paper_usdc < amount_usd:
                self.state.log("WARN", f"Không đủ USDC paper cho {symbol}")
                return None
            self.state.paper_usdc -= amount_usd
            mode = "PAPER"
            amount_sol = amount_usd / 150.0

        pos = {
            "token_address": mint,
            "symbol": symbol,
            "name": candidate.get("name", ""),
            "entry_price": price,
            "amount_usd": amount_usd,
            "amount_sol": amount_sol,
            "tokens_held": amount_usd / price if price else 0,
            "current_price": price,
            "highest_price": price,
            "opened_at": datetime.now().strftime("%H:%M:%S"),
            "potential": analysis.get("potential", "x1.5"),
            "analysis": analysis,
            "shill_score": candidate.get("shill", {}).get("score", 0),
            "risk_score": candidate.get("filter", {}).get("score", 100),
            "pre_score": candidate.get("pre_score", 0),
            "source": candidate.get("source"),
            "mode": mode,
            "awaiting_user": False,
            "last_alert_milestone": 0.0,   # ← mốc đã alert gần nhất
        }
        self.state.positions[mint] = pos
        self.state.stats["trades_executed"] += 1

        self.state.trades.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": "BUY", "symbol": symbol,
            "price": price, "amount_usd": amount_usd,
            "slippage_pct": slippage,
            "status": "FILLED", "mode": mode,
        })

        self.state.log("BUY",
            f"✅ [{mode}] MUA ${amount_usd:.0f} {symbol} @ ${price:.6f} "
            f"| shill={pos['shill_score']} risk={pos['risk_score']} pre={pos['pre_score']}")

        await self.notify_telegram(
            f"🟢 *BUY ({mode})* {symbol}\n"
            f"Entry: ${price:.6f} | Size: ${amount_usd:.0f}\n"
            f"Potential: {pos['potential']} | Shill: {pos['shill_score']}\n"
            f"_{analysis['reasoning']}_"
        )
        return pos

    # ---------------------------------------------------------
    # SELL
    # ---------------------------------------------------------
    async def execute_sell(self, addr: str, reason: str = "TP") -> Optional[dict]:
        pos = self.state.positions.get(addr)
        if not pos:
            return None
        symbol = pos["symbol"]
        slippage = self.state.settings["slippage_pct"]

        if pos.get("mode") == "GMGN" and self.state.settings.get("gmgn_api_key"):
            result = await self.trader.sell(addr, 100.0, slippage)
            if not result["ok"]:
                self.state.log("ERROR",
                    f"❌ GMGN sell {symbol}: {result.get('error','')[:120]}")
                return None

        sell_price = pos["current_price"]
        pnl_pct = (sell_price - pos["entry_price"]) / pos["entry_price"] * 100
        pnl = pos["amount_usd"] * pnl_pct / 100

        if pos.get("mode") != "GMGN":
            self.state.paper_usdc += pos["amount_usd"] + pnl

        del self.state.positions[addr]
        self.state.trades.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": "SELL", "symbol": symbol,
            "price": sell_price, "amount_usd": pos["amount_usd"] + pnl,
            "pnl": pnl, "pnl_pct": pnl_pct,
            "reason": reason, "status": "FILLED",
            "mode": pos.get("mode", "PAPER"),
        })

        self.state.log("SELL" if pnl >= 0 else "LOSS",
            f"{'🟢' if pnl >= 0 else '🔴'} [{pos.get('mode')}] BÁN {symbol} "
            f"@ ${sell_price:.6f} | PnL ${pnl:+.2f} ({pnl_pct:+.1f}%) | {reason}")

        await self.notify_telegram(
            f"{'🟢' if pnl >= 0 else '🔴'} *SELL* {symbol}\n"
            f"PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%) | {reason}"
        )
        return {"pnl": pnl, "pnl_pct": pnl_pct}

    # ---------------------------------------------------------
    # TELEGRAM
    # ---------------------------------------------------------
    async def notify_telegram(self, message: str):
        await self.tg.send(message)

    async def notify_telegram_with_buttons(self, dec: dict):
        milestone = dec.get("milestone", 0)
        next_m = dec.get("next_milestone", milestone + self.state.settings["profit_target_pct"])
        msg = (
            f"❓ *{dec['symbol']}* đạt +{dec['pnl_pct']:.1f}% "
            f"(mốc +{milestone:.0f}%)\n"
            f"Entry: ${dec['entry_price']:.6f} → Now: ${dec['current_price']:.6f}\n"
            f"Tiềm năng: *{dec['potential']}*\n"
            f"Shill: {dec.get('shill_score', 0)}\n"
            f"_{dec.get('reasoning', '')[:120]}_\n\n"
            f"Giữ tiếp (alert lại ở +{next_m:.0f}%) hay chốt lời?"
        )
        keyboard = [[
            {"text": "💎 GIỮ TIẾP", "callback_data": f"decide:{dec['id']}:hold"},
            {"text": "💰 CHỐT LỜI", "callback_data": f"decide:{dec['id']}:sell"},
        ]]
        await self.tg.send(msg, keyboard=keyboard)

    async def handle_telegram_callback(self, dec_id: str, action: str):
        self.state.log("TG", f"📲 Telegram callback: {dec_id} → {action}")
        dec = next((d for d in self.state.pending_decisions if d["id"] == dec_id), None)
        if not dec:
            self.state.log("TG", f"⚠️ Không tìm thấy decision {dec_id}")
            return
        addr = dec["token_address"]
        if action == "hold":
            if addr in self.state.positions:
                self.state.positions[addr]["awaiting_user"] = False
                # KHÔNG reset last_alert_milestone → mốc tiếp theo vẫn hoạt động
                next_m = dec.get("next_milestone", 50)
                self.state.log("HOLD", f"💎 Giữ {dec['symbol']} — alert lại ở +{next_m:.0f}%")
                await self.tg.send(
                    f"💎 Đã giữ *{dec['symbol']}*\n"
                    f"_Sẽ alert lại khi đạt +{next_m:.0f}%_"
                )
        elif action == "sell":
            await self.execute_sell(addr, reason="User chốt lời (Telegram)")
            await self.tg.send(f"💰 Đã bán *{dec['symbol']}* theo yêu cầu Telegram")
        self.state.pending_decisions = [
            d for d in self.state.pending_decisions if d["id"] != dec_id
        ]

    async def handle_telegram_command(self, text: str, chat_id: str):
        cmd = text.split()[0].lower()
        if cmd == "/status":
            msg = (
                f"📊 *Bot Status*\n"
                f"Ví paper: ${self.state.paper_usdc:.2f}\n"
                f"Vị thế: {len(self.state.positions)}/{self.state.settings['max_positions']}\n"
                f"Trades: {self.state.stats.get('trades_executed', 0)}"
            )
            await self.tg.send(msg)
        elif cmd == "/positions":
            if not self.state.positions:
                await self.tg.send("📭 Không có vị thế nào")
                return
            lines = ["💼 *Vị thế đang mở*"]
            for p in self.state.positions.values():
                pnl = (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100
                emoji = "🟢" if pnl >= 0 else "🔴"
                milestone = p.get("last_alert_milestone", 0)
                lines.append(
                    f"{emoji} *{p['symbol']}* {pnl:+.1f}% (mốc +{milestone:.0f}%)"
                )
            await self.tg.send("\n".join(lines))
        elif cmd == "/pending":
            if not self.state.pending_decisions:
                await self.tg.send("📭 Không có quyết định nào đang chờ")
                return
            for dec in self.state.pending_decisions:
                await self.notify_telegram_with_buttons(dec)
        else:
            await self.tg.send("🤖 *Lệnh:* /status /positions /pending")

    # ---------------------------------------------------------
    # LOOPS
    # ---------------------------------------------------------
    async def run(self):
        self.shill.start_worker()
        await asyncio.gather(
            self.leak.run(),
            self.price_watcher(),
            self.news_loop(),
            self.cache_cleanup(),
        )

    async def price_watcher(self):
        """
        Cập nhật giá + alert tại NHIỀU mốc: 50/100/150/200...
        Sau khi user bấm 'Giữ', bot vẫn tiếp tục alert ở mốc tiếp theo.
        """
        while True:
            if not self.state.positions:
                await asyncio.sleep(ACTIVE_PROFILE["price_watcher_idle"])
                continue

            tp = self.state.settings["profit_target_pct"]
            has_urgent = any(
                abs(((p["current_price"] - p["entry_price"]) / p["entry_price"] * 100) - tp) < 10
                for p in self.state.positions.values()
            )
            interval = 3 if has_urgent else ACTIVE_PROFILE["price_watcher_active"]

            for addr, pos in list(self.state.positions.items()):
                bias = {"x1.5": 1.2, "x2": 1.5, "x3": 2.0}.get(pos["potential"], 1.0)
                drift = random.uniform(-0.10, 0.11) * bias
                pos["current_price"] = max(pos["current_price"] * (1 + drift), 1e-9)
                pos["highest_price"] = max(pos["highest_price"], pos["current_price"])

                pnl_pct = (pos["current_price"] - pos["entry_price"]) / pos["entry_price"] * 100

                # Đảm bảo field tồn tại
                if "last_alert_milestone" not in pos:
                    pos["last_alert_milestone"] = 0.0

                # === LOGIC ALERT NHIỀU MỐC ===
                step = self.state.settings["profit_target_pct"]  # 50 → mốc 50/100/150...
                if pnl_pct >= step:
                    current_milestone = (int(pnl_pct // step)) * step
                else:
                    current_milestone = 0

                if current_milestone > pos["last_alert_milestone"]:
                    pos["last_alert_milestone"] = current_milestone
                    pos["awaiting_user"] = True

                    if pos["potential"] in ("x2", "x3"):
                        dec = {
                            "id": f"{addr[:8]}-{int(datetime.now().timestamp())}",
                            "token_address": addr,
                            "symbol": pos["symbol"],
                            "pnl_pct": pnl_pct,
                            "milestone": current_milestone,
                            "next_milestone": current_milestone + step,
                            "current_price": pos["current_price"],
                            "entry_price": pos["entry_price"],
                            "potential": pos["potential"],
                            "reasoning": pos["analysis"]["reasoning"],
                            "shill_score": pos.get("shill_score", 0),
                            "time": datetime.now().strftime("%H:%M:%S"),
                        }
                        self.state.pending_decisions.append(dec)
                        self.state.log("ASK",
                            f"❓ {pos['symbol']} +{pnl_pct:.1f}% "
                            f"(mốc +{current_milestone:.0f}%) — hỏi user")
                        await self.notify_telegram_with_buttons(dec)
                    else:
                        # x1.5 → bán tự động ở mốc đầu tiên
                        if current_milestone == step:
                            await self.execute_sell(
                                addr,
                                reason=f"TP +{pnl_pct:.1f}% (mốc {current_milestone:.0f}%)",
                            )
                            continue

                # Stop loss
                if pnl_pct <= self.state.settings["stop_loss_pct"]:
                    await self.execute_sell(addr, reason=f"SL {pnl_pct:.1f}%")

            await asyncio.sleep(interval)

    async def news_loop(self):
        await asyncio.sleep(10)
        while True:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get("https://cryptocurrency.cv/api/breaking")
                    if r.status_code == 200:
                        data = r.json()
                        items = data if isinstance(data, list) else []
                        self.state.log("NEWS", f"📰 Nhận {len(items)} tin")
                        for item in items[:3]:
                            title = item.get("title", "")[:100]
                            self.state.news_feed.insert(0, {
                                "id": str(item.get("id", ""))[:10],
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "source": "cryptocurrency.cv",
                                "text": title,
                                "token_symbol": "",
                                "analysis": None,
                            })
                        self.state.news_feed = self.state.news_feed[:50]
            except Exception as e:
                self.state.log("ERROR", f"News loop: {str(e)[:120]}")
            await asyncio.sleep(600)

    async def cache_cleanup(self):
        while True:
            await asyncio.sleep(1800)
            removed = self.state.gemini_cache.cleanup()
            if removed:
                self.state.log("INFO", f"🧹 Dọn {removed} cache entries")


pipeline = TokenPipeline(state, wallet)


# ============================================================
# FASTAPI
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    state.log("INIT",
        f"🚀 Bot khởi động | profile={ACTIVE_PROFILE_NAME} | "
        f"max_pos={state.settings['max_positions']}")

    if state.settings.get("gmgn_api_key"):
        ok = await pipeline.trader.check_config()
        state.log("INIT", f"GMGN: {'✅ OK' if ok else '⚠️ chưa config'}")
    else:
        state.log("WARN", "Chưa có GMGN_API_KEY → paper trading")

    if not state.settings.get("gemini_api_key"):
        state.log("WARN", "Chưa có GEMINI_API_KEY → fallback heuristic")
    if not state.settings.get("helius_api_key"):
        state.log("INFO", "Không có HELIUS_API_KEY → dùng DexScreener/Gecko")

    if pipeline.tg.enabled:
        pipeline.tg.start_polling()
        state.log("INIT", "📱 Telegram polling đã bật")
    else:
        state.log("WARN", "⚠️ Telegram chưa cấu hình — không nhận nút bấm")

    t = asyncio.create_task(pipeline.run())
    yield
    t.cancel()
    pipeline.leak.stop()
    pipeline.tg.stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/state")
async def get_state():
    positions = []
    for addr, p in state.positions.items():
        pnl_pct = (p["current_price"] - p["entry_price"]) / p["entry_price"] * 100
        positions.append({
            **p,
            "current_value": p["tokens_held"] * p["current_price"],
            "pnl_usd": p["tokens_held"] * p["current_price"] - p["amount_usd"],
            "pnl_pct": pnl_pct,
        })
    total_in_positions = sum(p["current_value"] for p in positions)
    return {
        "wallet_usdc": state.paper_usdc,
        "initial_usdc": state.initial_usdc,
        "total_value": state.paper_usdc + total_in_positions,
        "total_pnl": state.paper_usdc + total_in_positions - state.initial_usdc,
        "positions": sorted(positions, key=lambda x: -x["pnl_pct"]),
        "trades": state.trades[:30],
        "news_feed": state.news_feed[:20],
        "candidate_tokens": state.candidate_tokens[:15],
        "logs": state.logs[:60],
        "pending_decisions": state.pending_decisions,
        "settings": state.settings,
        "stats": state.stats,
        "profile": ACTIVE_PROFILE_NAME,
        "wallet_connected": wallet.connected,
        "wallet_address": wallet.public_key,
    }


@app.post("/api/settings")
async def update_settings(payload: dict):
    for k, v in payload.items():
        if k in state.settings:
            state.settings[k] = v
    pipeline.filter.settings = state.settings
    state.log("CFG", "⚙️ Cập nhật cài đặt")
    return {"ok": True}


@app.post("/api/decision/{dec_id}/{action}")
async def decide(dec_id: str, action: str):
    dec = next((d for d in state.pending_decisions if d["id"] == dec_id), None)
    if not dec:
        return {"ok": False}
    addr = dec["token_address"]
    if action == "hold":
        if addr in state.positions:
            state.positions[addr]["awaiting_user"] = False
            # KHÔNG reset last_alert_milestone → mốc tiếp theo vẫn hoạt động
            next_m = dec.get("next_milestone", 50)
            state.log("HOLD", f"💎 Giữ {dec['symbol']} — alert lại ở +{next_m:.0f}%")
    elif action == "sell":
        await pipeline.execute_sell(addr, reason="User chốt lời")
    state.pending_decisions = [d for d in state.pending_decisions if d["id"] != dec_id]
    return {"ok": True}


@app.post("/api/reset")
async def reset():
    state.paper_usdc = state.initial_usdc
    state.positions.clear()
    state.trades.clear()
    state.news_feed.clear()
    state.pending_decisions.clear()
    state.candidate_tokens.clear()
    state.log("INIT", "♻️ Reset")
    return {"ok": True}


@app.get("/api/wallet")
async def wallet_info():
    sol = await wallet.get_sol_balance()
    usdc = await wallet.get_usdc_balance()
    return {
        "connected": wallet.connected,
        "public_key": wallet.public_key,
        "sol_balance": sol,
        "usdc_balance": usdc,
    }


@app.post("/api/test/telegram")
async def test_telegram():
    tok = state.settings.get("telegram_bot_token", "").strip()
    chat = state.settings.get("telegram_chat_id", "").strip()
    if not tok or not chat:
        return {"ok": False, "error": "Chưa cấu hình token/chat_id"}
    try:
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, json={
                "chat_id": chat,
                "text": "🧪 *Test từ Meme Bot*\nNếu bạn thấy tin này → Telegram OK!",
                "parse_mode": "Markdown",
            })
            return {"ok": r.status_code == 200, "status": r.status_code, "body": r.text[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/test/force-buy")
async def test_force_buy():
    fake_candidate = {
        "mint": "TEST" + "1" * 40,
        "symbol": "TESTCOIN",
        "name": "Test Coin",
        "source": "manual_test",
        "filter": {
            "score": 10,
            "metrics": {
                "liquidity": 50000, "volume_24h": 100000, "price": 0.001,
                "lp_locked_pct": 95, "top_holder_pct": 10,
                "mint_authority": None, "freeze_authority": None,
            },
        },
        "shill": {"score": 60, "unique_kols": 3, "count": 5, "kols": ["test1", "test2"]},
        "pre_score": 85,
        "detected_at": datetime.now().strftime("%H:%M:%S"),
    }
    fake_analysis = {
        "score": 85, "decision": "BUY", "potential": "x2",
        "reasoning": "[TEST] Lệnh test", "confidence": 85,
        "engine": "test", "cached": False,
    }
    checks = {
        "auto_trade": state.settings.get("auto_trade"),
        "current_positions": len(state.positions),
        "max_positions": state.settings.get("max_positions"),
        "paper_usdc": state.paper_usdc,
        "trade_amount_usd": state.settings.get("trade_amount_usd"),
        "mint_already_in_positions": fake_candidate["mint"] in state.positions,
    }
    try:
        pos = await pipeline.execute_buy(fake_candidate, fake_analysis)
    except Exception as e:
        return {"ok": False, "reason": "exception", "error": str(e)[:300], "checks": checks}

    if pos:
        return {"ok": True, "message": f"Đã tạo vị thế {pos['symbol']}", "position": pos}

    reasons = []
    if checks["current_positions"] >= checks["max_positions"]:
        reasons.append(f"Đã đủ vị thế ({checks['current_positions']}/{checks['max_positions']})")
    if checks["mint_already_in_positions"]:
        reasons.append("Mint đã có trong positions")
    if checks["paper_usdc"] < checks["trade_amount_usd"]:
        reasons.append(f"Paper USDC ({checks['paper_usdc']}) < amount ({checks['trade_amount_usd']})")
    return {"ok": False, "reason": reasons or ["Không rõ"], "checks": checks}


@app.post("/api/test/decision")
async def test_decision():
    """Tạo decision giả để test nút Telegram."""
    if not state.positions:
        return {"ok": False, "msg": "Chưa có vị thế nào — chạy force-buy trước"}
    addr, pos = next(iter(state.positions.items()))
    step = state.settings["profit_target_pct"]
    dec = {
        "id": f"test-{int(datetime.now().timestamp())}",
        "token_address": addr,
        "symbol": pos["symbol"],
        "pnl_pct": 55.0,
        "milestone": step,
        "next_milestone": step * 2,
        "current_price": pos["current_price"],
        "entry_price": pos["entry_price"],
        "potential": pos.get("potential", "x2"),
        "reasoning": "[TEST] Đây là decision test",
        "shill_score": pos.get("shill_score", 0),
        "time": datetime.now().strftime("%H:%M:%S"),
    }
    state.pending_decisions.append(dec)
    await pipeline.notify_telegram_with_buttons(dec)
    return {"ok": True, "decision": dec}


@app.post("/api/position/{token_address}/close")
async def close_position(token_address: str, percentage: float = 100.0):
    """Đóng vị thế theo % (mặc định 100%)."""
    pos = state.positions.get(token_address)
    if not pos:
        return {"ok": False, "error": "Không tìm thấy vị thế"}

    if percentage >= 100:
        result = await pipeline.execute_sell(
            token_address, reason="User đóng thủ công (dashboard)")
        if result:
            return {"ok": True, "message": f"Đã đóng toàn bộ {pos['symbol']}",
                    "pnl": result.get("pnl"), "pnl_pct": result.get("pnl_pct")}
        return {"ok": False, "error": "execute_sell trả về None"}

    percentage = max(1, min(99, percentage))
    close_ratio = percentage / 100.0
    partial_amount = pos["amount_usd"] * close_ratio
    pos["amount_usd"] -= partial_amount
    pos["tokens_held"] *= (1 - close_ratio)

    sell_price = pos["current_price"]
    pnl = partial_amount * ((sell_price - pos["entry_price"]) / pos["entry_price"])
    pnl_pct = (sell_price - pos["entry_price"]) / pos["entry_price"] * 100

    if pos.get("mode") != "GMGN":
        state.paper_usdc += partial_amount + pnl

    state.trades.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": "SELL", "symbol": pos["symbol"],
        "price": sell_price, "amount_usd": partial_amount + pnl,
        "pnl": pnl, "pnl_pct": pnl_pct,
        "reason": f"Đóng {percentage:.0f}% thủ công",
        "status": "FILLED", "mode": pos.get("mode", "PAPER"),
    })

    state.log("SELL",
        f"🟡 Đóng {percentage:.0f}% {pos['symbol']} @ ${sell_price:.6f} "
        f"| PnL ${pnl:+.2f} ({pnl_pct:+.1f}%)")

    return {"ok": True, "message": f"Đã đóng {percentage:.0f}% {pos['symbol']}",
            "remaining_usd": pos["amount_usd"], "pnl": pnl, "pnl_pct": pnl_pct}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
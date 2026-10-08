"""
Telegram bot tương tác: gửi tin có nút bấm + nhận callback Hold/Sell.
Dùng polling getUpdates — không cần webhook, chạy được trên localhost.
"""
import asyncio
import httpx
from typing import Callable, Optional


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip()
        self.base = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.offset = 0
        self.running = False
        self.on_callback: Optional[Callable] = None  # callback(dec_id, action)
        self.on_command: Optional[Callable] = None   # callback(command, args)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    # =========================================================
    # SEND
    # =========================================================
    async def send(self, text: str, keyboard: list = None) -> bool:
        """Gửi tin nhắn. keyboard = [[{text, callback_data}, ...], ...]"""
        if not self.enabled:
            return False
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(f"{self.base}/sendMessage", json=payload)
                return r.status_code == 200
        except Exception as e:
            print(f"[TG] send error: {str(e)[:100]}", flush=True)
            return False

    async def answer_callback(self, callback_id: str, text: str = ""):
        """Trả lời callback để bỏ loading trên nút."""
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{self.base}/answerCallbackQuery", json={
                    "callback_query_id": callback_id,
                    "text": text[:200] if text else "",
                })
        except Exception:
            pass

    async def edit_message(self, chat_id: str, message_id: int, text: str):
        """Sửa nội dung tin đã gửi (để thông báo user đã quyết định)."""
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(f"{self.base}/editMessageText", json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
        except Exception:
            pass

    # =========================================================
    # POLL getUpdates
    # =========================================================
    async def _poll(self):
        """Poll getUpdates mỗi 2s, xử lý callback + command."""
        if not self.enabled:
            return
        print("[TG] Polling bắt đầu", flush=True)

        while self.running:
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    r = await c.get(f"{self.base}/getUpdates", params={
                        "offset": self.offset,
                        "timeout": 20,
                        "allowed_updates": ["callback_query", "message"],
                    })
                    if r.status_code != 200:
                        await asyncio.sleep(5)
                        continue

                    data = r.json()
                    for upd in data.get("result", []):
                        self.offset = upd["update_id"] + 1
                        await self._handle_update(upd)
            except httpx.ReadTimeout:
                # Long-poll timeout bình thường
                continue
            except Exception as e:
                print(f"[TG] poll error: {str(e)[:120]}", flush=True)
                await asyncio.sleep(5)

    async def _handle_update(self, upd: dict):
        # Callback từ nút bấm
        cb = upd.get("callback_query")
        if cb:
            data = cb.get("data", "")
            cb_id = cb.get("id")
            msg = cb.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            message_id = msg.get("message_id")

            # Format data: "decide:<dec_id>:<action>"
            parts = data.split(":")
            if len(parts) == 3 and parts[0] == "decide":
                dec_id, action = parts[1], parts[2]
                await self.answer_callback(cb_id, f"Đã chọn: {action.upper()}")
                if self.on_callback:
                    try:
                        await self.on_callback(dec_id, action)
                    except Exception as e:
                        print(f"[TG] on_callback error: {e}", flush=True)
                # Sửa tin gốc để báo đã quyết định
                label = "💎 GIỮ TIẾP" if action == "hold" else "💰 ĐÃ CHỐT LỜI"
                if chat_id and message_id:
                    await self.edit_message(
                        chat_id, message_id,
                        f"✅ Quyết định của bạn: *{label}*\n_Vị thế đã được xử lý._"
                    )
            return

        # Text command (tùy chọn)
        msg = upd.get("message")
        if msg and msg.get("text"):
            text = msg["text"].strip()
            if text.startswith("/"):
                if self.on_command:
                    try:
                        await self.on_command(text, str(msg.get("chat", {}).get("id")))
                    except Exception:
                        pass

    def start_polling(self):
        self.running = True
        asyncio.create_task(self._poll())

    def stop(self):
        self.running = False
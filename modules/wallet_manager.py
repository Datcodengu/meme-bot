import os
import json
import base58
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey

from config import USDC_MINT


class WalletManager:
    def __init__(self):
        self.keypair = None
        self.client = None
        self.public_key = None
        self._load()

    def _load(self):
        raw = os.getenv("WALLET_PRIVATE_KEY", "").strip()
        if not raw:
            print("[Wallet] Paper mode (không có WALLET_PRIVATE_KEY)")
            return
        try:
            if raw.startswith("["):
                secret = bytes(json.loads(raw))
            else:
                secret = base58.b58decode(raw)
            self.keypair = Keypair.from_bytes(secret)
            self.public_key = str(self.keypair.pubkey())
            rpc = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            self.client = AsyncClient(rpc, commitment=Confirmed)
            print(f"[Wallet] Đã kết nối: {self.public_key}")
        except Exception as e:
            print(f"[Wallet] Lỗi: {e}")

    @property
    def connected(self) -> bool:
        return self.keypair is not None

    async def get_sol_balance(self) -> float:
        if not self.client:
            return 0.0
        try:
            resp = await self.client.get_balance(self.public_key)
            return resp.value / 1e9
        except Exception:
            return 0.0

    async def get_usdc_balance(self) -> float:
        if not self.client:
            return 0.0
        try:
            resp = await self.client.get_token_accounts_by_owner(
                self.public_key, mint=Pubkey.from_string(USDC_MINT)
            )
            for acc in resp.value:
                info = await self.client.get_token_account_balance(acc.pubkey)
                return info.value.ui_amount or 0.0
        except Exception:
            return 0.0
        return 0.0
import asyncio
import json
from typing import List

from config import SOL_MINT, LAMPORTS_PER_SOL


class GMGNTrader:
    """Wrapper gmgn-cli. Yêu cầu: npm install -g gmgn-cli && gmgn-cli config --apply <KEY>"""

    def __init__(self, api_key: str = "", chain: str = "sol"):
        self.api_key = api_key
        self.chain = chain

    async def _run_cli(self, args: List[str], timeout: int = 45) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gmgn-cli", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "ok": proc.returncode == 0,
                "stdout": out.decode(errors="ignore").strip(),
                "stderr": err.decode(errors="ignore").strip(),
            }
        except asyncio.TimeoutError:
            return {"ok": False, "stderr": f"Timeout {timeout}s", "stdout": ""}
        except FileNotFoundError:
            return {"ok": False, "stderr": "gmgn-cli chưa cài", "stdout": ""}
        except Exception as e:
            return {"ok": False, "stderr": str(e)[:200], "stdout": ""}

    async def check_config(self) -> bool:
        r = await self._run_cli(["config", "--check"], timeout=15)
        return r["ok"]

    async def buy(self, token_address: str, amount_sol: float, slippage_pct: float = 30.0) -> dict:
        lamports = int(amount_sol * LAMPORTS_PER_SOL)
        r = await self._run_cli([
            "swap", "--chain", self.chain,
            "--input-token", SOL_MINT,
            "--output-token", token_address,
            "--amount", str(lamports),
            "--slippage", str(int(slippage_pct)),
        ], timeout=60)
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"] or r["stdout"]}
        try:
            return {"ok": True, "data": json.loads(r["stdout"])}
        except json.JSONDecodeError:
            return {"ok": True, "data": {"raw": r["stdout"]}}

    async def sell(self, token_address: str, percentage: float = 100.0, slippage_pct: float = 30.0) -> dict:
        r = await self._run_cli([
            "swap", "--chain", self.chain,
            "--input-token", token_address,
            "--output-token", SOL_MINT,
            "--percent", str(int(percentage)),
            "--slippage", str(int(slippage_pct)),
        ], timeout=60)
        if not r["ok"]:
            return {"ok": False, "error": r["stderr"] or r["stdout"]}
        try:
            return {"ok": True, "data": json.loads(r["stdout"])}
        except json.JSONDecodeError:
            return {"ok": True, "data": {"raw": r["stdout"]}}
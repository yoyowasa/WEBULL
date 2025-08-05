"""Step 12 : Health Monitor & Fail-over

- 30 s ごとに Webull REST / WS / システム資源をチェック
- 異常なら bot プロセスを kill → restart_cmd 実行 or backup_host へ ssh fail-over
- Discord Webhook に結果を通知
"""

import asyncio
import os
import signal
import subprocess
import time
from datetime import datetime, timezone

import aiohttp
import psutil
from discord_webhook import DiscordWebhook

# ── 設定 ─────────────────────────────
WEBULL_REST = "https://quoteapi.webullbroker.com/api/information/public/quote/tickerRealTime?tickerId=913256135"
WEBSOCKET_PING = "wss://quotes-gw.webullfintech.com/api/quote/tickRealtime"
CPU_LIMIT = 90        # %
MEM_LIMIT = 90        # %
DISK_LIMIT = 90       # %
CHECK_INTERVAL = 30   # sec
RESTART_CMD = ["systemctl", "restart", "webull-bot.service"]
BACKUP_HOST = "user@backup-vps"
DISCORD_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── 通知ヘルパ ───────────────────────
def notify(msg: str) -> None:
    if DISCORD_URL:
        DiscordWebhook(url=DISCORD_URL, content=msg).execute()
    print(msg)

# ── 各種チェック関数 ──────────────────
async def check_rest() -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as sess:
            async with sess.get(WEBULL_REST) as r:
                return r.status == 200
    except Exception:
        return False

async def check_ws() -> bool:
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(WEBSOCKET_PING, timeout=5) as ws:
                await ws.send_json({"ping": int(time.time())})
                await ws.receive(timeout=5)
                return True
    except Exception:
        return False

def check_system() -> bool:
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    return cpu < CPU_LIMIT and mem < MEM_LIMIT and disk < DISK_LIMIT

# ── メインループ ──────────────────────
async def monitor() -> None:
    while True:
        rest_ok, ws_ok = await asyncio.gather(check_rest(), check_ws())
        sys_ok = check_system()

        if rest_ok and ws_ok and sys_ok:
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        ts = datetime.now(timezone.utc).isoformat()
        notify(f":rotating_light: Bot Health NG at {ts}\nREST={rest_ok} WS={ws_ok} SYS={sys_ok}")

        # ── フェイルオーバ vs 再起動 ──
        if rest_ok or os.getenv("PRIMARY") == "False":        # 回線落ち・VPS故障など
            subprocess.run(RESTART_CMD)
            notify(":wrench: bot service restarted")
        else:
            subprocess.run(["ssh", BACKUP_HOST, "systemctl", "start", "webull-bot.service"])
            notify(f":truck: fail-over triggered → {BACKUP_HOST}")
            # ここで自身は停止し、バックアップ側に任せる
            os.kill(os.getpid(), signal.SIGTERM)

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        pass

"""
scripts.run_live
----------------
寄付き後モニタリング:
1) 10:00 ET で未約定指値をキャンセル
2) TP/2 到達で SL→建値（BE スライド）

--provider=webull | alpaca で
・TP 判定に使う Bid/Ask ソースを切替える
"""

# ── import（冒頭で統一）────────────────────────
import argparse
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict

from sdk.webull_sdk_wrapper import WebullClient          # 取引 & 口座
from gap_bot.filters import StockData                    # 型だけ再利用

# Alpaca REST Quote（provider=alpaca 用）
from sdk.quotes_alpaca import get_quote as alpaca_quote  # type: ignore

ET = timezone(timedelta(hours=-5))  # 夏時間は SDK 側に任せる


# ── Quote 抽象化 ──────────────────────────────
def make_quote_func(provider: str) -> Callable[[str], Dict]:
    """何をする関数? → symbol→dict を返す get_quote 関数を provider 別に返す"""
    if provider == "alpaca":
        return lambda sym: alpaca_quote(sym)             # Alpaca REST
    return lambda sym: webull_client.get_quote(sym)      # Webull SDK


# ── CLI ──────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="live monitor & BE slide")
    p.add_argument("--provider", choices=["webull", "alpaca"], default="webull")
    p.add_argument("--tp", type=float, default=0.07, help="TP 幅(例 0.07=+7%)")
    p.add_argument("--loop", type=float, default=30.0, help="監視間隔 sec")
    return p.parse_args()


# ── メイン ────────────────────────────────────
def main() -> None:
    args = parse_args()
    global webull_client
    webull_client = WebullClient.from_env()

    quote_func = make_quote_func(args.provider)

    cancel_time = datetime.combine(
        datetime.now(tz=ET).date(),
        datetime.strptime("10:00", "%H:%M").time(),
        tzinfo=ET,
    )
    end_time = cancel_time + timedelta(hours=1)

    print(f"[{datetime.utcnow():%H:%M:%S}] live monitor start ({args.provider})")

    while datetime.now(tz=ET) < end_time:
        # 1) 未約定指値キャンセル
        if datetime.now(tz=ET) >= cancel_time:
            for o in webull_client.get_active_orders():
                if o["status"] != "Filled":
                    webull_client.cancel_order(o["orderId"])
                    print(f"CANCEL {o['symbol']} #{o['orderId']}")

            cancel_time = end_time  # 二度実行しないよう更新

        # 2) BE スライド
        for pos in webull_client.get_positions():
            sym = pos["symbol"]
            entry = pos["avgPrice"]
            q = quote_func(sym)
            cur = q["bidPrice"] or q["askPrice"]
            if cur and cur >= entry * (1 + args.tp * 0.5):
                webull_client.modify_bracket(
                    order_id=pos["orderId"],
                    stop_loss=round(entry, 2),
                )
                print(f"BE-MOVE {sym} → SL {entry:.2f}")

        time.sleep(args.loop)

    print("live monitor finished")


# ── entrypoint ───────────────────────────────
if __name__ == "__main__":
    main()

"""
scripts.run_entry
-----------------
Step 2-3 : 指値エントリー & ブラケット注文

* --provider webull | alpaca
    指値価格計算に使う Bid/Ask を Webull SDK または Alpaca REST へ切替
* --screened screened_YYYYMMDD.json
    run_screen.py の結果ファイルを入力
"""

# ── import ────────────────────────────────────────────
import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List

from gap_bot.filters import StockData
from sdk.webull_sdk_wrapper import WebullClient          # 発注は必ず Webull
from datetime import datetime
from gap_bot.utils.logger import append_csv

# Alpaca REST Quote
from sdk.quotes_alpaca import get_quote as alpaca_quote  # type: ignore

# ── 共通ヘルパ ───────────────────────────────────────
def make_quote_func(provider: str) -> Callable[[str], Dict]:
    """provider に合わせて symbol→Bid/Ask dict を返す関数を生成"""
    if provider == "alpaca":
        return lambda s: alpaca_quote(s)
    # default webull
    return lambda s: webull_client.get_quote(s, extended=True)


def load_screened(path: Path) -> List[StockData]:
    with path.open() as f:
        return [StockData(**d) for d in json.load(f)]


def calc_shares(equity: float, price: float, kelly: float, max_loss_pct: float) -> int:
    risk_cap = equity * max_loss_pct * kelly
    size_risk = risk_cap / price
    size_cap  = (equity * 0.05) / price
    return int(math.floor(min(size_risk, size_cap)))


# ── CLI ───────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="limit entry + bracket order")
    p.add_argument("--provider", choices=["webull", "alpaca"], default="webull")
    p.add_argument("--screened", type=Path, required=True, help="screened_*.json")
    p.add_argument("--equity", type=float, required=True, help="口座資金 USD")
    p.add_argument("--kelly", type=float, default=0.2)
    p.add_argument("--max-loss-pct", type=float, default=0.02)
    p.add_argument("--tp", type=float, default=0.07)
    p.add_argument("--sl", type=float, default=0.025)
    return p.parse_args()


# ── main ─────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    global webull_client
    webull_client = WebullClient.from_env()
    quote_func = make_quote_func(args.provider)

    stocks = load_screened(args.screened)
    print(f"[{datetime.utcnow():%H:%M:%S}] processing {len(stocks)} tickers…")

    for stk in stocks:
        q = quote_func(stk.symbol)
        bid, ask = q["bidPrice"], q["askPrice"]
        if not bid or not ask:
            print(f"  {stk.symbol}: Bid/Ask 不正でスキップ")
            continue

        limit_px = (bid + ask) / 2 * 1.002
        shares   = calc_shares(args.equity, limit_px, args.kelly, args.max_loss_pct)
        if shares == 0:
            print(f"  {stk.symbol}: 株数 0 → スキップ")
            continue

        # --- 指値エントリー ---
        pid = webull_client.place_limit_order(
            symbol=stk.symbol,
            qty=shares,
            price=round(limit_px, 2),
            extended_hours=True,
        )["orderId"]
        print(f"  {stk.symbol}: limit {limit_px:.2f} ×{shares} → {pid}")

        # --- ブラケット ---
        webull_client.attach_bracket(
            parent_order_id=pid,
            take_profit=round(limit_px * (1 + args.tp), 2),
            stop_loss=round(limit_px * (1 - args.sl), 2),
            break_even_distance=args.tp / 2,
        )

        time.sleep(0.25)   # レート制限対策


if __name__ == "__main__":
    main()


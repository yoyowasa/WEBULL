
"""
Step2–3 : 指値エントリー & TP/SL ブラケット発注バッチ
実行例:
    poetry run python scripts/run_entry.py \
        --screened screened_20250728.json --equity 100000
"""

# ===== インポート =====
import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

from sdk.webull_sdk_wrapper import WebullClient            # 公式 SDK ラッパー
from gap_bot.filters import StockData                       # データ構造再利用

# ===== ユーティリティ =====
def calc_shares(
    equity: float,
    price: float,
    kelly: float,
    max_loss_pct: float,
) -> int:
    """
    ポジション株数を計算する関数
    - equity * 5%  との比較で小さいほうを採用
    - kelly × max_loss_pct で上限リスクを設定
    """
    risk_capital = equity * max_loss_pct * kelly
    size_by_risk = risk_capital / price
    size_by_cap = (equity * 0.05) / price
    return int(math.floor(min(size_by_risk, size_by_cap)))

def load_screened(path: Path) -> list[StockData]:
    """Step1 で保存した JSON を読み込み StockData リストに変換"""
    data = json.loads(path.read_text())
    return [StockData(**d) for d in data]

def parse_args() -> argparse.Namespace:
    """CLI 引数を処理"""
    p = argparse.ArgumentParser(description="Limit entry + bracket order batch")
    p.add_argument("--screened", type=Path, required=True, help="screened_YYYYMMDD.json")
    p.add_argument("--equity", type=float, required=True, help="口座資金 (USD)")
    p.add_argument("--kelly", type=float, default=0.2, help="Kelly 係数 (0–1)")
    p.add_argument("--max-loss-pct", type=float, default=0.02, help="1銘柄あたり許容損失 (%)")
    p.add_argument("--tp", type=float, default=0.07, help="TP 幅 (例 0.07=+7%)")
    p.add_argument("--sl", type=float, default=0.025, help="SL 幅 (例 0.025=–2.5%)")
    return p.parse_args()

# ===== メイン =====
def main() -> None:
    args = parse_args()
    client = WebullClient.from_env()  # .env に API キー等を保存
    stocks = load_screened(args.screened)

    print(f"[{datetime.utcnow():%H:%M:%S}] processing {len(stocks)} tickers…")

    for stk in stocks:
        # 1) 現在の Bid / Ask（Extended Hours）を取得
        q = client.get_quote(stk.symbol, extended=True)
        bid, ask = q["bidPrice"], q["askPrice"]
        if bid == 0 or ask == 0:
            print(f"  {stk.symbol}:   Bid/Ask 不正のためスキップ")
            continue

        limit_price = (bid + ask) / 2 * 1.002  # +0.2%
        shares = calc_shares(
            equity=args.equity,
            price=limit_price,
            kelly=args.kelly,
            max_loss_pct=args.max_loss_pct,
        )
        if shares == 0:
            print(f"  {stk.symbol}:   株数 0 → スキップ")
            continue

        # 2) 指値エントリー
        entry_resp = client.place_limit_order(
            symbol=stk.symbol,
            qty=shares,
            price=round(limit_price, 2),
            extended_hours=True,
        )
        order_id = entry_resp["orderId"]
        print(f"  {stk.symbol}:   limit {limit_price:.2f} ×{shares}  → order {order_id}")

        # 3) TP/SL ブラケットを添付
        tp_price = round(limit_price * (1 + args.tp), 2)
        sl_price = round(limit_price * (1 - args.sl), 2)
        client.attach_bracket(
            parent_order_id=order_id,
            take_profit=tp_price,
            stop_loss=sl_price,
            trail_to_break_even=args.tp / 2,
        )

        # API レート制限対策
        time.sleep(0.25)

if __name__ == "__main__":
    main()

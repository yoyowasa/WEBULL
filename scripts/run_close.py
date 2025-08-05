
"""Step 6 強制クローズ

15:45-16:00 ET の終盤に実行:
1. 口座の全オープンポジションを取得
2. 各ポジションを成行決済
3. 未約定注文を全てキャンセル
4. 当日の取引履歴を CSV 追記 (logs/close_log_YYYYMMDD.csv)
"""

# ── import: ファイル冒頭に統一 ──────────────────────────
import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import List
from gap_bot.utils.logger import append_csv

from sdk.webull_sdk_wrapper import WebullClient  # 独自ラッパ

# ── 関数群 ────────────────────────────────────────────
def load_client() -> WebullClient:
    """環境変数から認証を読み込み、WebullClient を返す関数"""
    return WebullClient.from_env()

def list_open_positions(client: WebullClient) -> List[dict]:
    """現在のオープンポジション ({symbol, qty}) を返す関数"""
    return client.get_positions()  # 各要素: {"symbol": "AAPL", "qty": 100}

def market_close_position(client: WebullClient, symbol: str, qty: int) -> str:
    """成行でポジションを決済し、注文 ID を返す関数"""
    return client.place_market_order(symbol=symbol, qty=qty, side="sell")

def cancel_open_orders(client: WebullClient) -> None:
    """未約定注文を一括取消する関数"""
    for order in client.list_open_orders():
        client.cancel_order(order_id=order["id"])

def append_csv(order_ids: List[str]) -> None:
    """当日ログ CSV に注文 ID とタイムスタンプを追記する関数"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    fname = log_dir / f"close_log_{dt.date.today():%Y%m%d}.csv"
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with fname.open("a", newline="") as f:
        writer = csv.writer(f)
        for oid in order_ids:
            writer.writerow([now, oid])

def main() -> None:
    """CLI エントリポイント"""
    parser = argparse.ArgumentParser(description="Step 6 強制クローズ")
    parser.add_argument("--dry-run", action="store_true", help="発注せずログだけ")
    args = parser.parse_args()

    client = load_client()
    positions = list_open_positions(client)
    order_ids: List[str] = []

    for pos in positions:
        if not args.dry_run:
            oid = market_close_position(client, pos["symbol"], pos["qty"])
            append_csv(f"close_log_{dt.date.today():%Y%m%d}.csv", [dt.datetime.utcnow().isoformat(), pos["symbol"], pos["qty"], oid])

            order_ids.append(oid)

    if not args.dry_run:
        cancel_open_orders(client)
        append_csv(order_ids)

    print(f"Closed {len(order_ids)} positions; open orders cancelled.")

if __name__ == "__main__":
    main()

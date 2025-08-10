
"""Step 6 強制クローズ

15:45-16:00 ET の終盤に実行:
1. 口座の全オープンポジションを取得
2. 各ポジションを成行決済
3. 未約定注文を全てキャンセル
4. 当日の取引履歴を CSV 追記 (logs/close_log_YYYYMMDD.csv)
"""

# ── import: ファイル冒頭に統一 ──────────────────────────
import argparse
from pathlib import Path  # ログ保存先ディレクトリを扱うために使用
import csv                # CSV へログを書き込むために使用
import datetime as dt

from typing import List
from gap_bot.utils.notify import send_discord_message  # 決済イベントを Discord に送信


from sdk.webull_sdk_wrapper import WebullClient  # 独自ラッパ

# ── 関数群 ────────────────────────────────────────────
def load_client() -> WebullClient:
    """環境変数から認証を読み込み、WebullClient を返す関数"""
    return WebullClient.from_env()

def list_open_positions(client: WebullClient) -> List[dict]:
    """現在のオープンポジション ({symbol, qty}) を返す関数"""
    return client.get_positions()  # 各要素: {"symbol": "AAPL", "qty": 100}

def market_close_position(client: WebullClient, symbol: str, qty: int) -> str:
    """
    役割: 成行でポジションを決済し、返ってきた応答から注文IDを安全に取り出して返す。
         同時に Discord へ「どの銘柄を何株クローズしたか」を通知する。
    """
    resp = client.place_market_order(symbol=symbol, qty=qty, side="sell")  # 成行クローズ実行
    # 何をするコードか: 応答が dict/オブジェクト/文字列のいずれでも注文IDを取り出す
    oid = resp.get("orderId") if isinstance(resp, dict) else getattr(resp, "orderId", resp)  # 何をする行か: place_market_order の応答(resp)から注文IDを取り出して oid に入れる

    send_discord_message(f"引け前クローズ発注: {symbol} {qty}株 注文ID={oid}")  # Discord通知
    return str(oid)  # 呼び出し元へ注文IDを返す

def close_all_positions(client: WebullClient) -> list[str]:
    """
    役割: 全ポジションを market_close_position() で成行クローズし、
          取得した注文IDのリストを返す。
    """
    order_ids: list[str] = []
    for p in client.get_positions():  # ← ラッパの関数名が違う場合はここを合わせる（例: list_positions）
        if p.get("qty", 0) > 0:
            oid = market_close_position(client, p["symbol"], p["qty"])  # 中でDiscord通知も実施
            order_ids.append(oid)
    return order_ids



def cancel_open_orders(client: WebullClient) -> None:
    """未約定注文を一括取消する関数"""
    for order in client.list_open_orders():
        client.cancel_order(order_id=order["id"])

def write_close_log(order_ids: List[str]) -> None:  # 決済注文 ID をまとめて CSV 保存する関数

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
    client = WebullClient()  # 何をする行か: 発注に使う Webull クライアントを main() のスコープで生成する
    order_ids = close_all_positions(client)  # 何をする行か: 全ポジションを成行クローズして注文IDのリストを受け取る
    write_close_log(order_ids)               # 何をする行か: 取得した注文IDをCSVに保存する

    parser = argparse.ArgumentParser(description="Step 6 強制クローズ")
    parser.add_argument("--dry-run", action="store_true", help="発注せずログだけ")
    args = parser.parse_args()

    client = load_client()
    positions = list_open_positions(client)
    order_ids: List[str] = []

    for pos in positions:
        if not args.dry_run:
            oid = market_close_position(client, pos["symbol"], pos["qty"])
            log_append_csv(f"close_log_{dt.date.today():%Y%m%d}.csv", [dt.datetime.utcnow().isoformat(), pos["symbol"], pos["qty"], oid])  # クローズ注文を 1 行ずつ追記


            order_ids.append(oid)

    if not args.dry_run:
        cancel_open_orders(client)
        write_close_log(order_ids)  # 決済後に注文 ID 一覧を CSV へ保存


    print(f"Closed {len(order_ids)} positions; open orders cancelled.")

if __name__ == "__main__":
    main()

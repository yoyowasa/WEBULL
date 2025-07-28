
"""
寄付き後にポジション／注文をモニタリングして
・10:00 ET で未約定指値をキャンセル
・利確目標(×tp)の半分に到達したら SL をブレイクイーブンへ変更
"""

# ===== インポート（ファイル冒頭に統一） =====
import time
from datetime import datetime, timedelta, timezone

from sdk.webull_sdk_wrapper import WebullClient  # 公式 SDK ラッパー

# 米東部時間を表す tzinfo
ET = timezone(timedelta(hours=-5))  # 夏時間は SDK 内部で調整すると仮定


# ---------- 補助関数 ----------
def et_now() -> datetime:
    """現在時刻を ET（米東部時間）で返す関数"""
    return datetime.now(tz=ET)


# ---------- キャンセル関数 ----------
def cancel_stale_limit_orders(client: WebullClient, cancel_time_et: datetime) -> None:
    """
    何をする関数？ → 指定時刻(cancel_time_et)を過ぎた未約定指値注文をすべてキャンセルする
    """
    if et_now() < cancel_time_et:
        return  # まだ指定時刻前なら何もしない

    active_orders = client.get_active_orders()
    for order in active_orders:
        if order["status"] == "Filled":
            continue  # すでに約定したものは対象外
        client.cancel_order(order_id=order["orderId"])
        print(f"[{et_now():%H:%M:%S ET}] CANCEL  {order['symbol']}  #{order['orderId']}")


# ---------- BE スライド関数 ----------
def slide_sl_to_break_even(
    client: WebullClient,
    tp_ratio: float = 0.07,
) -> None:
    """
    何をする関数？ → 各ポジションの現在価格が
    「エントリー価格 + TP*0.5」以上になったら、
    そのポジションに紐づく SL をエントリー価格へ変更する
    """
    positions = client.get_positions()
    for pos in positions:
        sym = pos["symbol"]
        entry = pos["avgPrice"]
        current = pos["lastPrice"]
        if current >= entry * (1 + tp_ratio * 0.5):
            # 既に建値以上にスライド済みかを確認
            bracket = client.get_bracket(sym)
            if bracket and bracket["stopLossPrice"] <= entry:
                continue  # もう建値付近にあるならスキップ

            # SL を建値へ変更
            client.modify_bracket(
                symbol=sym,
                stop_loss=round(entry, 2),
            )
            print(f"[{et_now():%H:%M:%S ET}] BE-MOVE {sym} → SL {entry:.2f}")


# ---------- メインループ ----------
def main() -> None:
    """
    何をする関数？ → Market Open 後にループを回して
    1) キャンセル時刻になったら未約定注文を取り消す
    2) 利確 TP/2 到達で SL を建値へ移動
    3) ループは 11:00 ET に自動終了
    """
    client = WebullClient.from_env()
    cancel_time = datetime.combine(et_now().date(), datetime.strptime("10:00", "%H:%M").time(), tzinfo=ET)
    end_time = datetime.combine(et_now().date(), datetime.strptime("11:00", "%H:%M").time(), tzinfo=ET)

    print(f"--- live monitor started ({et_now():%H:%M ET}) ---")
    print("  • 10:00 ET で未約定指値をキャンセル")
    print("  • 利確目標の ½ 到達で SL→建値")

    while et_now() < end_time:
        cancel_stale_limit_orders(client, cancel_time_et=cancel_time)
        slide_sl_to_break_even(client, tp_ratio=0.07)
        time.sleep(30)  # 30 秒間隔でチェック

    print(f"--- live monitor finished ({et_now():%H:%M ET}) ---")


# ---------- エントリーポイント ----------
if __name__ == "__main__":
    main()

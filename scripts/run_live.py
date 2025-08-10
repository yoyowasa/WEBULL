"""
scripts.run_live
----------------
寄付き後モニタリング (Step4-5) :

1) 10:00 ET で未約定指値をキャンセル
2) TP/2 到達で SL→建値 (BE スライド)
3) TP 到達で SL→TP/2 利確幅へ
4) REST で Halt 検知 → Unhalt 5 分以内に逆指値(+1 %) を 1 回だけ発注

--provider=webull | alpaca で
Bid/Ask ソースを切替
"""

# ── import（冒頭で統一）────────────────────────
import argparse
import time
import requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List
from decimal import Decimal
from gap_bot.filters import StockData                    # 型利用のみ
from sdk.webull_sdk_wrapper import WebullClient          # Webull API
from sdk.quotes_alpaca import get_quote as alpaca_quote  # Alpaca REST
from gap_bot.utils.notify import send_discord_message  # 取引イベントを Discord へ通知

# ── グローバル ────────────────────────────────
webull_client: WebullClient | None = None
ET = timezone(timedelta(hours=-5))  # 夏時間は SDK 側に任せる

# ── WebullClient 生成ヘルパ ───────────────────
def get_client() -> WebullClient:
    """環境変数から初期化して使い回す WebullClient"""
    global webull_client
    if webull_client is None:
        webull_client = WebullClient.from_env()
    return webull_client

# ── Trailing Stop-Loss ヘルパ ──────────────────
def update_trailing_sl(pos: dict, price: float, tp_pct: float) -> None:
    """TP/2→SL=建値、TP→SL=TP/2 へ引き上げ（long/short 両対応）"""
    entry, side, sl = pos["entry"], pos["side"], pos["sl"]
    half = tp_pct / 2
    if side == "long":
        if price >= entry * (1 + tp_pct) and sl < entry * (1 + half):
            pos["sl"] = round(entry * (1 + half), 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
        elif price >= entry * (1 + half) and sl < entry:
            pos["sl"] = round(entry, 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
    else:  # short
        if price <= entry * (1 - tp_pct) and sl > entry * (1 - half):
            pos["sl"] = round(entry * (1 - half), 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
        elif price <= entry * (1 - half) and sl > entry:
            pos["sl"] = round(entry, 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])

# ── REST Halt ポーリング ──────────────────────
halt_state: dict[str, bool] = {}                 # symbol → True (=halt中)
halt_ts:    dict[str, datetime | None] = {}      # symbol → unhalt時刻
next_poll = datetime.utcnow()                    # 次回ポーリング時刻

HALF_TP_DONE: set[str] = set()  # 何をするコードか: 銘柄ごとの「半分利確済み」を覚えて二重発注を防ぐモジュール共通の状態
LAST_ET_DATE = None  # 何をする変数か: 前回処理時の ET 日付を記録しておく（切替検知用）

def reset_half_tp_if_new_day():
    """
    役割: 米国東部時間で日付が変わったら HALF_TP_DONE を空にして、翌日に二重発注を起こさないようにする
    """
    # この関数でしか使わないため関数内 import（DST を正しく処理するため zoneinfo を使用）
    from datetime import datetime
    from zoneinfo import ZoneInfo
    global LAST_ET_DATE, HALF_TP_DONE

    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    if LAST_ET_DATE != today_et:
        HALF_TP_DONE.clear()      # 新しい営業日に入ったので「半分利確済み」記録をリセット
        LAST_ET_DATE = today_et   # 何をする行か: リセット後の基準日を更新

# ── 取引実行ヘルパ ────────────────────────────
def execute_half_tp(position, current_price, client):
    """
    役割: TP の 1/2 (+3 % など) に到達した瞬間、
          建玉の半分を成行で利確する。
    """
    avg = Decimal(str(position["average_price"]))  # 取得単価
    gain_pct = (Decimal(str(current_price)) - avg) / avg * Decimal("100")
    half_tp = Decimal(str(position["tp_pct"])) / Decimal("2")

    # +TP/2 に達し、まだ半分利確していないときだけ実行
    if (
        gain_pct >= half_tp
        and position["qty"] > 1
        and not position.get("half_tp_done")
    ):
        qty = position["qty"] // 2
        client.place_market_order(
            symbol=position["symbol"],
            qty=qty,
            side="sell",
            market=True
        )
        send_discord_message(f"半分利確完了 : {position['symbol']} {qty}株 @ {current_price}")  # 取引イベントを Discord に通知する行

        position["half_tp_done"] = True  # もう一度売らないようフラグ保存

def fetch_halt_status() -> set[str]:
    """現在 Halt 中のシンボル集合を返す"""
    url = "https://quoteapi.webullbroker.com/api/information/market/halts?region=US"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return {d["symbol"] for d in r.json() if d["haltFlag"] == "H"}
    except Exception:
        return set()

# ── Quote 抽象化 ──────────────────────────────
def make_quote_func(provider: str) -> Callable[[str], Dict]:
    if provider == "alpaca":
        return lambda sym: alpaca_quote(sym)     # Alpaca REST
    return lambda sym: webull_client.get_quote(sym)  # Webull SDK

# ── CLI ──────────────────────────────────────
def parse_args() -> argparse.Namespace:
    
    p = argparse.ArgumentParser(description="live monitor & BE slide")
    p.add_argument("--provider", choices=["webull", "alpaca"], default="webull")
    p.add_argument("--tp", type=float, default=0.07, help="TP 幅(例 0.07=+7%)")
    p.add_argument("--loop", type=float, default=30.0, help="監視間隔 sec")
    p.add_argument("--paper", action="store_true", help="run in paper-trading mode")  # ペーパートレード切り替え

    return p.parse_args()


# ── メイン ────────────────────────────────────
def main() -> None:
    args = parse_args()
    global webull_client
    webull_client = get_client()
    quote_func = make_quote_func(args.provider)
    client = WebullClient()  # ← 利確で発注するための Webull 通信用クライアント

    cancel_time = datetime.combine(
        datetime.now(tz=ET).date(),
        datetime.strptime("10:00", "%H:%M").time(),
        tzinfo=ET,
    )
    end_time = datetime.combine(
        datetime.now(tz=ET).date(),
        datetime.strptime("15:45", "%H:%M").time(),
        tzinfo=ET,
    )

    # ポジション初期化
    positions: List[dict] = []
    for p in webull_client.get_positions():
        entry = p["avgPrice"]
        qty   = float(p.get("position", p.get("quantity", 0)))
        side  = "short" if qty < 0 else "long"
        init_sl = round(entry * (1 - 0.025), 2) if side == "long" else round(entry * (1 + 0.025), 2)
        positions.append({
            "symbol": p["symbol"],
            "entry": entry,
            "side": side,
            "sl": init_sl,
            "order_id": p["orderId"],
            "tp_pct": args.tp,
            "qty": abs(qty),  
        })

    print(f"[{datetime.utcnow():%H:%M:%S}] live monitor start ({args.provider})")
    while datetime.now(tz=ET) < end_time:
        # ① 10:00 ET 未約定指値キャンセル
        if datetime.now(tz=ET) >= cancel_time:
            for o in webull_client.get_active_orders():
                if o["status"] != "Filled":
                    webull_client.cancel_order(o["orderId"])
                    print(f"CANCEL {o['symbol']} #{o['orderId']}")
            cancel_time = end_time  # 一度だけ

        # ② Halt 状態 REST ポーリング（30 s）
        now = datetime.utcnow()
        if now >= next_poll:
            current = fetch_halt_status()
            next_poll = now + timedelta(seconds=30)

            for sym in current - {s for s, v in halt_state.items() if v}:
                halt_state[sym] = True
                webull_client.cancel_open_orders(symbol=sym)
                print(f"HALT REST → cancel {sym} orders")

            for sym, active in list(halt_state.items()):
                if active and sym not in current:
                    halt_state[sym] = False
                    halt_ts[sym] = now
                    print(f"UNHALT {sym} REST → will set stop")

        reset_half_tp_if_new_day()  # 何をする行か: 米国ETで日付が変わっていたら半分利確フラグ(HALF_TP_DONE)をリセットする

        # ③ 価格更新ループ
        for pos in positions:
            q = quote_func(pos["symbol"])
            cur = q["bidPrice"] or q["askPrice"]
            if not cur:
                continue
            execute_half_tp(pos, cur, client)  # TP/2 到達なら半分利確

            update_trailing_sl(pos, cur, pos["tp_pct"])

            # Unhalt 復帰 5 分以内に逆指値(+1 %) 発注
            t0 = halt_ts.get(pos["symbol"])
            if t0 and 0 <= (datetime.utcnow() - t0).total_seconds() <= 300:
                stop_px = cur * (1.01 if pos["side"] == "long" else 0.99)
                webull_client.place_stop_order(
                    symbol=pos["symbol"],
                    qty=pos["qty"],  
                    stop_price=round(stop_px, 2),
                    side="sell" if pos["side"] == "long" else "buy",
                )
                halt_ts[pos["symbol"]] = None
                print(f"UNHALT {pos['symbol']} → stop @ {stop_px:.2f}")

        time.sleep(args.loop)

    print("live monitor finished")

# ── entrypoint ───────────────────────────────
if __name__ == "__main__":
    main()

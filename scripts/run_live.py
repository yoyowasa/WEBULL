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
from datetime import datetime, timedelta
from typing import Callable, Dict, List
from decimal import Decimal
from gap_bot.filters import StockData                    # 型利用のみ
from sdk.webull_sdk_wrapper import WebullClient          # Webull API
from sdk.quotes_alpaca import get_quote as alpaca_quote  # Alpaca REST
from gap_bot.utils.notify import send_discord_message  # 取引イベントを Discord へ通知
from zoneinfo import ZoneInfo  # DST対応の米国東部時間を扱うために使用（importは冒頭に追加）


# ── グローバル ────────────────────────────────
webull_client: WebullClient | None = None
ET = ZoneInfo("America/New_York")  # 何をする行か: DST対応のETに切替（夏時間/冬時間を自動反映）


# ── WebullClient 生成ヘルパ ───────────────────
def get_client() -> WebullClient:
    """環境変数から初期化して使い回す WebullClient"""
    global webull_client, next_poll  # 何をする行か: main内で next_poll を更新できるようにグローバル参照にする

    if webull_client is None:
        try:
            webull_client = WebullClient.from_env()  # 何をする行か: 環境変数から認証つきクライアントを生成（対応していれば）
        except AttributeError:
            webull_client = WebullClient()           # 何をする行か: from_env が無い実装向けのフォールバック

    return webull_client

# ── Trailing Stop-Loss ヘルパ ──────────────────
def update_trailing_sl(pos: dict, price: float, tp_pct: float) -> None:
    if webull_client is None:  # 何をする行か: クライアント未初期化時の AttributeError を防ぎ、安全にスキップする
        return
    
    """TP/2→SL=建値、TP→SL=TP/2 へ引き上げ（long/short 両対応）"""
    entry, side, sl = pos["entry"], pos["side"], pos["sl"]
    half = tp_pct / 2
    if side == "long":
        if price >= entry * (1 + tp_pct) and sl < entry * (1 + half):
            pos["sl"] = round(entry * (1 + half), 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
            send_discord_message(f"SL繰上げ: {pos['symbol']} → {pos['sl']} (TP到達, long)")  # 何をする行か: BE→TP/2 への逆指値繰上げをDiscordへ通知

        elif price >= entry * (1 + half) and sl < entry:
            pos["sl"] = round(entry, 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
            send_discord_message(f"SL→BE: {pos['symbol']} → {pos['sl']} (TP/2到達, long)")  # 何をする行か: 長ポジの逆指値を建値へ繰り上げたことをDiscordへ通知

    else:  # short
        if price <= entry * (1 - tp_pct) and sl > entry * (1 - half):
            pos["sl"] = round(entry * (1 - half), 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
            send_discord_message(f"SL繰上げ: {pos['symbol']} → {pos['sl']} (TP到達, short)")  # 何をする行か: 短ポジのTP到達で逆指値をTP/2へ繰上げたことをDiscordへ通知

        elif price <= entry * (1 - half) and sl > entry:
            pos["sl"] = round(entry, 2)
            webull_client.modify_bracket(order_id=pos.get("order_id", pos.get("oid")), stop_loss=pos["sl"])
            send_discord_message(f"SL→BE: {pos['symbol']} → {pos['sl']} (TP/2到達, short)")  # 何をする行か: 短ポジの逆指値を建値へ繰り上げたことをDiscordへ通知


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
    global LAST_ET_DATE, HALF_TP_DONE

    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    if LAST_ET_DATE != today_et:
        HALF_TP_DONE.clear()      # 新しい営業日に入ったので「半分利確済み」記録をリセット
        LAST_ET_DATE = today_et   # 何をする行か: リセット後の基準日を更新

# ── 取引実行ヘルパ ────────────────────────────
def execute_half_tp(position, current_price, client, paper: bool = False):
    """役割: TP/2 到達で建玉の半分を利確する（paper=True のときは約定せず通知だけ）"""

    """
    役割: TP の 1/2 (+3 % など) に到達した瞬間、
          建玉の半分を成行で利確する。
    """
    avg = Decimal(str(position["entry"]))  # 何をする行か: ポジション初期化で入れた取得単価 'entry' を使う（KeyError防止）  
    gain_pct = (Decimal(str(current_price)) - avg) / avg * Decimal("100")
    profit_pct = gain_pct if position.get("side", "long") == "long" else -gain_pct  # 何をする行か: ショートは利益を正にするため符号を反転し、利益率(%)をlong/short共通指標にする

    half_tp = (Decimal(str(position["tp_pct"])) * Decimal("100")) / Decimal("2")  # 何をする行か: tp_pct(0.07=7%)を「百分率」に直してから半分にする→3.5に揃え、gain_pct(%)との単位不一致を解消


    # +TP/2 に達し、まだ半分利確していないときだけ実行
    if (
        profit_pct >= half_tp  # 何をする行か: long/short共通の利益率(%) profit_pct を使って TP/2 到達を判定する
        and position["qty"] > 1
        and position["symbol"] not in HALF_TP_DONE  # 何をする行か: 銘柄ごとの“半分利確済み”集合で未処理かを確認する
    ):
        qty = int(position["qty"] // 2)  # 何をする行か: SDKが整数株数を要求するため、半分の数量を明示的にintへキャストする
    if not paper:  # 何をする行か: ペーパーモードのときは実発注せず通知だけにする
        order_side = "sell" if position.get("side", "long") == "long" else "buy"  # 何をする行か: ロングは売り、ショートは買い戻しに切替える
        client.place_market_order(symbol=position["symbol"], qty=qty, side=order_side)  # 何をする行か: 半分利確の実発注（paper=Falseのときのみ）



        send_discord_message(f"半分利確完了 : {position['symbol']} {qty}株 @ {current_price}")  # 取引イベントを Discord に通知する行
        position["qty"] = max(0, int(position["qty"]) - qty)  # 何をする行か: 半分利確で売った分だけ保有数量を減らし、後続の逆指値やUNHALT発注の数量を正しく保つ

        HALF_TP_DONE.add(position["symbol"])  # 何をする行か: この銘柄は本日すでに半分利確を済ませたと記録して二重発注を防ぐ


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
    client = get_client()  # 何をする行か: 発注も見積もりも同じ認証セッション(WebullClient)を共有して再認証や不整合を防ぐ


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
        entry = float(p["avgPrice"])  # 何をする行か: 取得単価を数値化して後続の計算(round/×÷)で型エラーを防ぐ

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
    send_discord_message(f"live開始: provider={args.provider}")  # 何をする行か: 監視開始をDiscordへ通知して運用ログを残す

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
                for o in webull_client.get_active_orders():  # 何をする行か: 新規HALTのこの銘柄に紐づく未約定だけ走査（← 'for sym in ...' の中に入れる）
                    if o.get("symbol") == sym and o.get("status") != "Filled":
                        try:
                            webull_client.cancel_order(o["orderId"])  # 何をする行か: 当該銘柄の未約定をキャンセルする
                            send_discord_message(f"HALT検知→注文取消: {sym} #{o['orderId']}")  # 何をする行か: 成功をDiscordへ通知
                        except Exception as e:
                            send_discord_message(f"HALT取消失敗: {sym} #{o.get('orderId')} {e}")  # 何をする行か: 失敗も通知して原因をログ化

                print(f"HALT REST → cancel {sym} orders")  # 何をする行か: この銘柄の取消処理が完了したログ


            for sym, active in list(halt_state.items()):
                if active and sym not in current:
                    halt_state[sym] = False
                    halt_ts[sym] = now
                    print(f"UNHALT {sym} REST → will set stop")

        reset_half_tp_if_new_day()  # 何をする行か: 米国ETで日付が変わっていたら半分利確フラグ(HALF_TP_DONE)をリセットする

        # ③ 価格更新ループ
        for pos in positions:
            q = quote_func(pos["symbol"])
            cur = q.get("bidPrice") or q.get("askPrice") or q.get("bid_price") or q.get("ask_price") or q.get("p") or q.get("lastPrice")  # 何をする行か: プロバイダ差のキーに対応して現在値を安全取得

            if not cur:
                continue
            execute_half_tp(pos, cur, client, paper=args.paper)  # 何をする行か: CLI引数のpaperフラグを渡し、ペーパーモード時は実発注せず通知だけにする


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
                send_discord_message(f"UNHALT逆指値: {pos['symbol']} stop @ {round(stop_px, 2)}")  # 何をする行か: Unhalt直後の逆指値発注をDiscordへ通知
                halt_ts[pos["symbol"]] = None
                print(f"UNHALT {pos['symbol']} → stop @ {stop_px:.2f}")

        time.sleep(args.loop)

    print("live monitor finished")

# ── entrypoint ───────────────────────────────
if __name__ == "__main__":
    main()

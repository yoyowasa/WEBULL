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
def update_trailing_sl(pos: dict, price: float, tp_pct: float) -> float:
    """何をする関数なのか: 価格が利確目標(TP%)の半分に到達したら、ストップ(sl)を建値(entry)へ繰り上げ/繰り下げする。更新後のslを返す"""
    # 何をする行か: 入力(辞書)から必要な値を安全に取り出して型をそろえる
    entry = float(pos.get("entry"))
    sl = float(pos.get("sl", entry))
    side = str(pos.get("side", "long")).lower()
    half = 0.5 * float(tp_pct or 0.0)  # 何をする行か: TP%の半分(例: 0.03 → 0.015)を計算

    if side in {"long", "buy"}:
        trigger = entry * (1.0 + half)  # 何をする行か: ロングの半分TP到達価格
        if price >= trigger:
            new_sl = max(sl, entry)  # 何をする行か: 既存slより低くならないように建値へ繰り上げ
            pos["sl"] = new_sl
            return new_sl
        pos["sl"] = sl  # 何をする行か: 未到達なら変更なし
        return sl

    if side in {"short", "sell"}:
        trigger = entry * (1.0 - half)  # 何をする行か: ショートの半分TP到達価格
        if price <= trigger:
            new_sl = min(sl, entry)  # 何をする行か: 既存slより高くならないように建値へ繰り下げ
            pos["sl"] = new_sl
            return new_sl
        pos["sl"] = sl  # 何をする行か: 未到達なら変更なし
        return sl

    # 何をする行か: 想定外のside入力時は変更せず現状維持
    pos["sl"] = sl
    return sl

# ── 逆指値発注ヘルパ ──────────────────────────
def ensure_stop_at_sl(pos: dict, client, paper: bool = False) -> bool:
    """何をする関数なのか: 現在の pos['sl']（建値など）と同じ価格の逆指値STOPをアクティブに保つ。修正APIが無いSDKもあるため、既存STOPがあればキャンセル→指定価格で再作成する"""
    # 何をする行か: ペーパーモードでは実発注せず成功扱いにする（実運用時のみ発注）
    if paper:
        return True

    # 何をする行か: 銘柄・サイド・数量・新しいSTOP価格を安全に取り出し/正規化
    symbol = str(pos.get("symbol", "")).upper()
    side = "sell" if str(pos.get("side", "long")).lower() in {"long", "buy"} else "buy"
    qty = int(abs(float(pos.get("qty", 0)) or 0))
    if not symbol or qty <= 0:
        return False
    new_stop = round(float(pos.get("sl")), 2)

    # 何をする行か: アクティブ注文から、この銘柄のSTOP注文（対側）を1件探す
    try:
        orders = client.get_active_orders() or []
    except Exception:
        orders = []
    def _get(d, *keys):
        for k in keys:
            if isinstance(d, dict) and k in d:
                return d[k]
        return None

    target_oid = None
    target_stop = None
    for o in orders:
        if str(_get(o, "symbol", "ticker", "sym") or "").upper() != symbol:
            continue
        o_side = str(_get(o, "side", "action", "orderSide") or "").lower()
        if o_side not in {"buy", "sell"} or o_side != side:
            continue
        otype = str(_get(o, "orderType", "type", "order_type") or "").lower()
        if "stop" not in otype and not any(k in o and str(o[k]).lower().startswith("stop") for k in ("flag", "category")):
            continue
        target_oid = str(_get(o, "orderId", "id", "oid", "clientOrderId", "cloid") or "")
        s_px = _get(o, "stopPrice", "stop_price", "triggerPrice", "auxPrice", "stop", "stop_px")
        try:
            target_stop = float(s_px) if s_px is not None else None
        except Exception:
            target_stop = None
        break

    # 何をする行か: 既存STOPの価格が同じなら何もしない
    if target_oid and target_stop is not None and abs(target_stop - new_stop) < 0.005:
        return True

    # 何をする行か: 既存STOPがあればキャンセル（失敗しても続行）
    if target_oid:
        try:
            client.cancel_order(target_oid)
        except Exception:
            pass

    # 何をする行か: 建値SLの価格でSTOPを新規作成
    try:
        res = client.place_stop_order(symbol=symbol, qty=qty, stop_price=new_stop, side=side)
        return bool(isinstance(res, dict) and (res.get("success") is True or res.get("orderId")))
    except Exception:
        return False



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
# ── 発注ヘルパ ──────────────────────────────

def place_entry(webull_client, symbol: str, side: str, qty: int, limit: float, tif: str = "DAY", extended: bool = False, tp_pct: float = None, sl_pct: float = None) -> dict:
    """何をする関数なのか: 指値エントリーを一括実行する。TP/SLが割合(例:0.07)で渡されたら価格へ変換し、SDK差異を吸収するWebullラッパで発注し、結果をDiscordへ通知する"""
    s = str(side).strip().lower()  # 何をする行か: サイド表記を正規化（buy/long/SELLなどの揺れを吸収）
    is_long = s in {"buy", "long"}  # 何をする行か: ロング判定
    is_short = s in {"sell", "short"}  # 何をする行か: ショート判定
    if not (is_long or is_short):  # 何をする行か: 想定外入力はbuy扱いでフォールバック
        is_long = True
        s = "buy"

    # 何をする行か: TP/SLを割合→価格に換算（エクイティ想定。ロングは+でTP/-でSL、ショートは逆）
    tp = None
    sl = None
    if isinstance(tp_pct, (int, float)) and tp_pct is not None:
        tp = limit * (1 + tp_pct) if is_long else limit * (1 - tp_pct)
    if isinstance(sl_pct, (int, float)) and sl_pct is not None:
        sl = limit * (1 - sl_pct) if is_long else limit * (1 + sl_pct)

    # 何をする行か: 発注処理をラッパーで統一し、TP/SL(%)→価格換算も自動化してDiscord通知まで行う
    res = place_entry(webull_client, symbol=symbol, side=side, qty=qty, limit=limit, tif=tif, extended=extended, tp_pct=tp_pct, sl_pct=sl_pct)  
    oid = res.get("orderId")

    # 何をする行か: 結果を人間が読みやすい形でDiscord通知
    tp_str = f"{tp:.2f}" if tp is not None else "-"
    sl_str = f"{sl:.2f}" if sl is not None else "-"
    msg = f"ENTRY {symbol} {('LONG' if is_long else 'SHORT')} x{qty} @ {limit:.2f} {tif}{' EXT' if extended else ''} TP={tp_str} SL={sl_str} OID={oid or 'N/A'}"
    send_discord_message(msg)

    return res  # 何をする行か: 上位で orderId や success を確認できるようそのまま返す

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


            tp_ratio = pos.get("tp_pct", getattr(args, "tp", None))  # 何をする行か: ポジション固有TP%が無ければCLI引数--tpを使う
            prev_sl = pos.get("sl")  # 何をする行か: SL更新前の値を保持して比較に使う
            new_sl = update_trailing_sl(pos, price=cur, tp_pct=tp_ratio)  # 何をする行か: 半分TP到達ならSLを建値(entry)へ自動移動
            if new_sl != prev_sl:  # 何をする行か: いまSLが更新されたかどうかを判定
                synced = ensure_stop_at_sl(pos, client=webull_client, paper=args.paper)  # 何をする行か: 実際のSTOP注文を建値に同期（paper時は発注せずTrue）
                send_discord_message(f"TSL→建値移動: {pos.get('symbol','?')} SL={new_sl:.2f} (entry={float(pos.get('entry',0)):.2f}) {'[STOP更新OK]' if synced else '[STOP更新失敗]'}")  # 何をする行か: 同期結果をDiscordへ通知
                ensure_stop_at_sl(pos, client=webull_client, paper=args.paper)  # 何をする行か: 実際のSTOP注文をpos["sl"](建値)へ同期する。paper=Trueなら発注せずスキップ



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

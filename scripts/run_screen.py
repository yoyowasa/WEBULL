"""
scripts.run_screen
------------------
Step 1  : プレマーケット銘柄スクリーナー

* provider = webull | alpaca を選択
* 出力 : 条件を満たした銘柄を JSON 保存 & 標準出力に一覧表示
"""

# ── インポート（冒頭で統一） ───────────────────────────
import argparse
import os
import json
import pandas as pd

from datetime import datetime, timedelta, timezone
import yaml
from pathlib import Path
from typing import List
import time 
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)


required_keys = ["POLYGON_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
missing = [k for k in required_keys if not os.getenv(k)]
if missing:
    raise RuntimeError(f"未設定の環境変数: {', '.join(missing)}")

from gap_bot.filters import StockData, screen_stocks
from sdk.quotes_polygon import get_prev_close, get_snapshot
from sdk.quotes_alpaca import get_quote as alpaca_quote
import requests
from sdk.quotes_polygon import _get 
from sdk.webull_sdk_wrapper import WebullClient  # type: ignore
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from gap_bot.utils.logger import logger
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from gap_bot.utils.logger import append_csv
# 追加: import 行
from gap_bot.filters import StockData, screen_stocks, build_filters  # データ型・総合フィルタ・ビルダー
filters = {}

# Alpaca Market-Data クライアント（IEX 無料フィード）
client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY")
)
# Alpaca ラッパー（provider=alpaca の時だけ使う）
try:
    from sdk.quotes_alpaca import list_premarket_gappers  # type: ignore
except ImportError:
    list_premarket_gappers = None  # Alpaca 利用しない場合ここは None

def get_float_shares(symbol: str) -> int:
    """
    流通株数 (Float) を取得する関数
    - メモリキャッシュで同一銘柄の重複アクセスを回避
    - 未取得なら yfinance で取得し、成功したらキャッシュに入れる
    - 取得できなければ 0 を返して後段フィルタで弾く
    """
    # ── メモリキャッシュ ─────────────────────
    if not hasattr(get_float_shares, "_cache"):
        get_float_shares._cache = {}              # type: ignore[attr-defined]
    cache: dict[str, int] = get_float_shares._cache  # type: ignore[attr-defined]

    if symbol in cache:                           # キャッシュ HIT
        return cache[symbol]

    # ── API 呼び出し (yfinance) ──────────────
    try:
        import yfinance as yf                     # 関数内 import
    except ImportError:
        logger.debug("yfinance 未インストール→ float_shares を 0 扱い")
        cache[symbol] = 0
        return 0

    try:
        info = yf.Ticker(symbol).fast_info
        shares_float = int(info.get("shares_float", 0))
        cache[symbol] = shares_float              # キャッシュ保存
        return shares_float
    except Exception as e:
        logger.debug("%s float_shares error: %s", symbol, e)
        cache[symbol] = 0
        return 0



def get_sentiment_score(symbol: str) -> float:
    """
    SNS／ニュースのポジティブ度合いを数値で返す関数
    - Finnhub の News-Sentiment API を利用 (要 FINNHUB_API_KEY)
    - スコアは -1.0〜+1.0 程度で返る想定。取得できなければ 0.0
    """
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        logger.debug("FINNHUB_API_KEY 未設定→ sentiment_score を 0 扱い")
        return 0.0

    url = "https://finnhub.io/api/v1/news-sentiment"
    try:
        r = requests.get(url, params={"symbol": symbol, "token": token}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            # Finnhub のレスポンス例では `companyNewsScore` が中心値
            return float(data.get("companyNewsScore", 0.0))
        logger.debug("%s sentiment HTTP %s", symbol, r.status_code)
    except Exception as e:
        logger.debug("%s sentiment error: %s", symbol, e)

    return 0.0

# ── Webull 用データ取得 ──────────────────────────────
def fetch_premarket_webull(client: WebullClient) -> List[StockData]:
    """Webull 版のデータ取得は未実装なので、空リストを返して呼び出しエラーを防ぐ"""
    return []

def get_last_min_bar(symbol: str) -> dict:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    path = f"/v2/aggs/ticker/{symbol}/range/1/minute/{today}/{today}"
    bars = _get(path)["results"]
    return bars[-1] if bars else {}


def alpaca_premarket(sym: str) -> tuple[float, int]:
    """IEX 最新 Quote と 04:00～今 の出来高合計を返す"""
    q = alpaca_quote(sym)
    pre_price = q.get("ap") or q.get("askPrice") or q.get("bp") or q.get("bidPrice") or q.get("p")

    if pre_price is None:
        return None, 0

    # 04:00 ET から現在までの 1 分足 volume 合計
    et_now = datetime.now(tz=timezone.utc) - timedelta(hours=4)
    start  = et_now.replace(hour=4, minute=0, second=0, microsecond=0)
    bars = client.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=sym,
        timeframe=TimeFrame.Minute,
        start=start,
        feed="iex",
    )).df
    vol = int(bars["V"].sum()) if not bars.empty else 0
    return pre_price, vol

def _get_close_price(df):
    for key in ("c", "close", "Close"):
        if key in df.columns:
            closes = df[key].replace(0, pd.NA).dropna()
            if not closes.empty:
                return float(closes.iloc[0])        # ← 最初の非ゼロ Close
    return 0.0




# ── Alpaca + Polygon Free 併用データ取得 ──────────────────────
def fetch_premarket_alpaca(symbols: List[str], args) -> List[StockData]:
    """
    Polygon Free で前日終値だけ取得し、
    Alpaca IEX でプレマーケット価格（最新 Quote）と
    04:00 ET 以降の出来高を取得して統合する。

    フィルタ条件
        ・ギャップ率 ±3 % 以上
        ・プレマーケット出来高 50 k 株 以上
    """
    out: List[StockData] = []

    for sym in symbols:
        # --- 前日終値を Polygon Free から取得 (200 OK) ---
        try:
            prev_close = get_prev_close(sym)
            if prev_close == 0:
                bars = client.get_stock_bars(
                    StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, limit=5, feed="iex")
                ).df
                if not bars.empty:
                    logger.debug("%s bars columns %s", sym, list(bars.columns))


                    prev_close = _get_close_price(bars)



            if prev_close == 0:
                latest = client.get_stock_latest_bar(
                    StockLatestBarRequest(symbol_or_symbols=sym, feed="iex")
                )
                if latest and sym in latest:
                    prev_close = latest[sym].close



            if prev_close == 0:
                logger.debug("%s skip: prev_close still zero", sym)
                continue




        except requests.HTTPError as e:
            print(f"[ERR ] {sym} Polygon prev_close {e.response.status_code}")
            logger.debug("%s skip: prev_close error %s", sym, e)

            continue

        # --- Alpaca IEX で最新 Quote と出来高を取得 ---
        q = alpaca_quote(sym)
        logger.debug("%s raw quote %s", sym, q)
# ask-price / bid-price / last
        pre_price = q.get("ap") or q.get("askPrice") or q.get("bp") or q.get("bidPrice") or q.get("p")

        if pre_price is None:

            logger.debug("%s skip: pre_price None", sym)

            continue                                    # 価格が取れない銘柄は除外

        # 04:00 ET から現在までの 1 分足 volume を合算
        et_now  = datetime.now(tz=timezone.utc) - timedelta(hours=4)
        start   = et_now.replace(hour=4, minute=0, second=0, microsecond=0)
        bars_df = client.get_stock_bars(
            StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Minute, start=start, feed="iex")
        ).df
        if bars_df.empty:
            logger.debug("%s skip: pre_volume zero (bars empty)", sym)
            continue


        vol_col = next((c for c in ("V", "v", "volume", "Volume") if c in bars_df.columns), None)
        pre_vol = int(bars_df[vol_col].sum()) if vol_col else 0
        float_shares = get_float_shares(sym)
        float_rot = pre_vol / float_shares * 100 if float_shares else 0
        sent_score = get_sentiment_score(sym)


        # --- ギャップ率計算 & デバッグ表示 ---
        if prev_close == 0:
            logger.debug("%s skip: prev_close zero", sym)
            continue

        gap_pct = (pre_price - prev_close) / prev_close

        logger.debug("%s prev=%.2f pre=%.2f gap=%+.2f%% vol=%d",
                     sym, prev_close, pre_price, gap_pct * 100, pre_vol)
        Path("logs").mkdir(exist_ok=True)  # ログ用ディレクトリが無ければ作成
        append_csv("logs/raw_premarket.csv", [sym, prev_close, pre_price, pre_vol])



        # --- フィルタ ---
        if not (
            filters["gap_ok"](gap_pct)
            and filters["vol_ok"](pre_vol)
            and filters["rot_ok"](float_rot) # ← float_rot 値をここで渡す
            and filters["sent_ok"](sent_score)                     # ← sent_score 値をここで渡す
        ):
            logger.debug("%s skip: filtered-out", sym)
            continue



        # --- 合格銘柄をリストに追加 ---
        out.append(
            StockData(
                symbol=sym,
                previous_close=prev_close,
                premarket_price=pre_price,
                premarket_volume=pre_vol,
                float_shares=float_shares,            # 取得済みの Float を格納
                sentiment_score=sent_score,           # SNS／News スコアを格納

            )
        )

        time.sleep(0.25)   # Alpaca 無料枠 5 req/sec を守る

    return out



# ── CLI 引数 ───────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    cfg_path = Path(__file__).parent.parent / "screen_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}

    p = argparse.ArgumentParser(description="Pre-market gap screener")
    p.add_argument("--provider", choices=["webull", "alpaca"], default=cfg.get("provider", "webull"))
    p.add_argument("--symbols", type=Path, default=Path(cfg.get("symbols", "")) if cfg.get("symbols") else None, help="監視ティッカーリスト (alpaca 専用)")
    p.add_argument("--gap", type=float, default=cfg.get("gap", 3.0), help="Gap%% threshold")
    p.add_argument("--vol", type=int, default=cfg.get("vol", 100_000), help="Premarket volume threshold")
    p.add_argument("--rot", type=float, default=cfg.get("rot", 50.0), help="Float rotation threshold")
    p.add_argument("--sent", type=float, default=cfg.get("sent", 3.0), help="Sentiment score threshold")
    p.add_argument(
        "--out",
        type=Path,
        default=Path(cfg.get("out", f"screened_{datetime.utcnow():%Y%m%d}.json")),
        help="Output JSON file",
    )

    return p.parse_args()


# ── メイン ────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    global filters
    filters = build_filters(Path(__file__).parent.parent / "screen_config.yaml")
    logger.debug("active thresholds → gap=%s%% vol=%s rot=%s%% sent=%s",
             args.gap, args.vol, args.rot, args.sent)

    # 1) データ取得
    if args.provider == "webull":
        client = WebullClient.from_env()
        raw_stocks = fetch_premarket_webull(client)
    else:  # alpaca
        if args.symbols is None or not args.symbols.exists():
            raise SystemExit("alpaca 利用時は --symbols <file> が必須です")
        symbols = [s.strip() for s in args.symbols.read_text().splitlines() if s.strip()]
        raw_stocks = fetch_premarket_alpaca(symbols, args)

    # ▼ ここから追加 ─ プレマーケットの生データを CSV に追記保存する
    raw_df = pd.DataFrame([s.__dict__ for s in raw_stocks])      # list → DataFrame
    csv_path = Path("logs/raw_premarket.csv")                    # 保存パス
    csv_path.parent.mkdir(exist_ok=True)                         # logs/ ディレクトリ確保
    file_exists = csv_path.exists()                              # ヘッダー出力要否
    raw_df.to_csv(csv_path, mode="a", header=not file_exists, index=False)  # 追記保存
    # ▲ 追加はここまで ────────────────

    # 2) フィルタリング


    # 2) フィルタリング
    screened = screen_stocks(
        raw_stocks,
        gap_threshold=args.gap,
        min_volume=args.vol,
        min_rotation=args.rot,
        min_sentiment=args.sent,
    )

    # 3) 出力
    for s in screened:
        gap_pct = (s.premarket_price - s.previous_close) / s.previous_close * 100
        print(f"{s.symbol:<6}  Gap {gap_pct:>5.2f}%  Vol {s.premarket_volume:,}")

    args.out.write_text(json.dumps([s.__dict__ for s in screened], indent=2))
    print(f"\n{len(screened)} tickers saved → {args.out.resolve()}")


if __name__ == "__main__":
    main()

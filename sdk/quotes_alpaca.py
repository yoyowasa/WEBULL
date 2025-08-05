"""
sdk.quotes_alpaca
-----------------
Alpaca Data v2 を使った無料リアルタイム気配ラッパー。

必要な環境変数 (.env):
ALPACA_API_KEY
ALPACA_SECRET_KEY
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

# ────────────────────────────────────────────────────
# 共通 UTC / ET ヘルパ
ET = timezone(timedelta(hours=-5))


def _et_today_0400() -> datetime:
    """何をする関数? → 今日 04:00 ET を返す（プレマーケット開始）"""
    now_et = datetime.now(tz=ET)
    return now_et.replace(hour=4, minute=0, second=0, microsecond=0)


# ────────────────────────────────────────────────────
# Alpaca クライアント生成
def _get_historical_client() -> StockHistoricalDataClient:
    """何をする関数? → REST 用クライアントを返す"""
    load_dotenv()
    return StockHistoricalDataClient(
        api_key=os.environ["APCA_API_KEY_ID"],
        secret_key=os.environ["APCA_API_SECRET_KEY"],
    )



def _get_stream_client() -> StockDataStream:
    """何をする関数? → WebSocket 用クライアントを返す"""
    load_dotenv()
    return StockDataStream(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
    )


# ────────────────────────────────────────────────────
# プレマーケットギャッパー抽出
def list_premarket_gappers(
    *,
    symbols: List[str],
    gap_threshold: float = 3.0,
    min_volume: int = 100_000,
) -> List[Dict[str, Any]]:
    """
    何をする関数? → 指定シンボル群からプレマーケットギャップ銘柄を抽出して返す
    REST 1分足を 04:00 ET～ 現在まで取得し、前日終値 vs 最新値で Gap% を計算
    """
    client = _get_historical_client()
    start = _et_today_0400()
    end = datetime.now(tz=ET)

    req = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex", 
        limit=1,  # 最新1本
        adjustment=None,
    )
    bars = client.get_stock_bars(req).df  # pandas.DataFrame

    out: List[Dict[str, Any]] = []
    for sym in symbols:
        if "symbol" not in bars.columns or sym not in bars["symbol"].values:
            continue

        row = bars.xs(sym, level="symbol").iloc[-1]
        pre_price = row["close"]
        pre_vol = int(row["volume"])
        # 前日終値は /v2/stocks/{sym}/bars?timeframe=1Day&limit=2 から前日を引く
        prev_req = StockBarsRequest(
            symbol_or_symbols=sym, timeframe=TimeFrame.Day, limit=2, adjustment=None
        )
        prev_day = client.get_stock_bars(prev_req).df.xs(sym, level="symbol").iloc[-2][
            "close"
        ]
        gap_pct = (pre_price - prev_day) / prev_day * 100

        if gap_pct >= gap_threshold and pre_vol >= min_volume:
            out.append(
                {
                    "symbol": sym,
                    "prevClose": prev_day,
                    "preMarketPrice": pre_price,
                    "preMarketVolume": pre_vol,
                    "floatShares": 0,  # Alpaca では取得不可
                    "sentimentScore": 0.0,  # 別ソースで補完
                }
            )
    return out


# ────────────────────────────────────────────────────
# L1 Bid/Ask 取得
def get_quote(symbol: str) -> Dict[str, Any]:
    """何をする関数? → 指定銘柄の最新 Bid / Ask を返す (IEX Top)"""
    client = _get_historical_client()
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    q = client.get_stock_latest_quote(req)

    quote = q[symbol]

    return {
        "bidPrice": quote.bid_price,
        "askPrice": quote.ask_price,
        "bidSize": quote.bid_size,
        "askSize": quote.ask_size,
        "timestamp": quote.timestamp,
    }

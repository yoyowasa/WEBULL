"""sdk.quotes_polygon
----------------------------------
Polygon.io Free エンドポイント用の簡易ラッパ

Functions
---------
get_prev_close(symbol) : 前日終値 (float)
get_snapshot(symbol)   : {'bid': float, 'ask': float, 'volume': int}
"""

# ── import（冒頭で統一）────────────────────────
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict
from functools import lru_cache
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
_BASE = "https://api.polygon.io"

_alp = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

# ── API 呼び出し関数群 ─────────────────────────
def _get(path: str, params: Dict = None) -> Dict:
    """内部用：GET リクエストを叩いて JSON を返す関数"""
    params = params or {}
    api_key = os.getenv("POLYGON_API_KEY")  # 毎回読み込み
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is not set")
    params["apiKey"] = api_key

    r = requests.get(f"{_BASE}{path}", params=params, timeout=5)
    r.raise_for_status()
    return r.json()


@lru_cache(maxsize=1)
def _prev_close_map() -> dict[str, float]:
    """前日終値をまとめて取得して dict で返す（Free でも 1 リクエスト）"""
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    data = _get(f"/v2/aggs/grouped/locale/us/market/stocks/{yesterday}")
    return {str(r["T"]): float(r["c"]) for r in data.get("results", [])}

@lru_cache(maxsize=2048)
def get_prev_close(symbol: str) -> float:
    """
    【前日終値を Alpaca 日足で取得】
    Polygon Free の 403 / 429 を完全回避するため、
    symbol ごとに 1Day bar を 1 本だけ取り、その close を返す。
    """
    bars = _alp.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        limit=2,               # 昨日と今日
        feed="iex",
    )).df
    if bars.empty or len(bars) < 2:
        return 0.0
    return float(bars.iloc[-2]["c"])       # 昨日の close



def get_snapshot(symbol: str) -> Dict:
    """Bid/Ask と当日出来高を返す関数"""
    data = _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
    tkr = data["ticker"]
    return {
        "bid": float(tkr["lastQuote"]["p"]),
        "ask": float(tkr["lastQuote"]["p2"]),
        "volume": int(tkr["day"]["v"]),
        "ts": datetime.fromtimestamp(tkr["updated"]/1000, tz=timezone.utc),
    }

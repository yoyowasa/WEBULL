"""
sdk.alpaca_ws  ― Alpaca Data v2 IEX フィード (WebSocket)

使い方 (ブロッキング):
    from sdk.alpaca_ws import stream_quotes

    def printer(q):
        print(q)

    stream_quotes(["AAPL", "TSLA"], printer)   # Ctrl-C で終了
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List

from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream
from alpaca.data.models import Quote
from dotenv import load_dotenv

QuoteHandler = Callable[[Dict], None]


def _build_client() -> StockDataStream:
    """IEX 無料フィード用クライアントを初期化して返す"""
    load_dotenv()
    key = os.environ["ALPACA_API_KEY"]
    sec = os.environ["ALPACA_SECRET_KEY"]
    return StockDataStream(key, sec, feed=DataFeed.IEX)


def stream_quotes(symbols: List[str], handler: QuoteHandler) -> None:
    """
    symbols の最新 L1 Quote を購読し、受信するたびに handler(dict) を呼び出す。
    * ブロッキング実行 (内部で asyncio.run を使う)
    """
    client = _build_client()

    async def _on_quote(q: Quote) -> None:
        handler(
            {
                "symbol": q.symbol,
                "bidPrice": q.bid_price,
                "askPrice": q.ask_price,
                "bidSize": q.bid_size,
                "askSize": q.ask_size,
                "timestamp": q.timestamp,
            }
        )

    for sym in symbols:
        client.subscribe_quotes(_on_quote, sym)

    # ← 内部で asyncio.run() を呼び出す blocking メソッド
    client.run()

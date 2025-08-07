"""
tests/test_filters.py
------------------------------------------------
filters.py 内の StockData & screen_stocks の最小テスト
"""

import pytest
from gap_bot.filters import StockData, screen_stocks

# ── テスト用のダミー銘柄データを作成 ───────────────
GOOD = StockData(
    symbol="GOOD",
    previous_close=100.0,
    premarket_price=103.5,   # +3.5 %
    premarket_volume=150_000,
    float_shares=1_000_000,
    sentiment_score=3.5,
)

BAD_GAP = StockData(
    symbol="BADG",
    previous_close=100.0,
    premarket_price=100.5,   # +0.5 %
    premarket_volume=150_000,
    float_shares=1_000_000,
    sentiment_score=3.5,
)

BAD_VOL = StockData(
    symbol="BADV",
    previous_close=100.0,
    premarket_price=103.5,
    premarket_volume=10_000,  # 出来高不足
    float_shares=1_000_000,
    sentiment_score=3.5,
)

BAD_ROT = StockData(
    symbol="BADR",
    previous_close=100.0,
    premarket_price=103.5,
    premarket_volume=150_000,
    float_shares=10_000_000,  # Float が大きく Rotation 低い
    sentiment_score=3.5,
)

BAD_SENT = StockData(
    symbol="BADS",
    previous_close=100.0,
    premarket_price=103.5,
    premarket_volume=150_000,
    float_shares=1_000_000,
    sentiment_score=0.5,      # SNS スコア不足
)

# ── テスト本体 ────────────────────────────────
def test_screen_stocks_filters_correctly():
    stocks = [GOOD, BAD_GAP, BAD_VOL, BAD_ROT, BAD_SENT]
    screened = screen_stocks(stocks)
    # 合格は GOOD だけのはず
    assert [s.symbol for s in screened] == ["GOOD"]

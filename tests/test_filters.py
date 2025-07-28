# tests/test_filters.py
from gap_bot.filters import StockData, screen_stocks

def test_screen_stocks_basic():
    """gap=5%, volume=200k, rotation=60%, sentiment=4 → 条件を通過するか？"""
    sample = [
        StockData(
            symbol="TEST",
            previous_close=100,
            premarket_price=105,
            premarket_volume=200_000,
            float_shares=300_000,
            sentiment_score=4,
        )
    ]
    screened = screen_stocks(sample)
    assert len(screened) == 1
    assert screened[0].symbol == "TEST"

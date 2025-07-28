
from dataclasses import dataclass
from typing import List

# ---------- データ保持用 ----------
@dataclass
class StockData:
    """1銘柄ぶんのプレマーケットデータを保持するクラス"""
    symbol: str
    previous_close: float          # 前日終値
    premarket_price: float         # プレマーケット価格
    premarket_volume: int          # プレマーケット出来高
    float_shares: int              # 流通株数（Float）
    sentiment_score: float         # SNS／News スコア

# ---------- 個別判定ロジック ----------
def calculate_gap_percent(stock: StockData) -> float:
    """ギャップ率(%)を計算する関数"""
    return (stock.premarket_price - stock.previous_close) / stock.previous_close * 100

def passes_gap(stock: StockData, threshold: float) -> bool:
    """ギャップ率が閾値を超えているか判定する関数"""
    return calculate_gap_percent(stock) >= threshold

def calculate_float_rotation(stock: StockData) -> float:
    """Float Rotation(%) = 出来高 ÷ Float × 100"""
    if stock.float_shares == 0:
        return 0.0
    return stock.premarket_volume / stock.float_shares * 100

def passes_float_rotation(stock: StockData, min_rotation: float) -> bool:
    """Float Rotation が閾値を超えているか判定する関数"""
    return calculate_float_rotation(stock) >= min_rotation

def passes_volume(stock: StockData, min_volume: int) -> bool:
    """プレマーケット出来高が閾値を超えているか判定する関数"""
    return stock.premarket_volume >= min_volume

def passes_sentiment(stock: StockData, min_score: float) -> bool:
    """SNS／News スコアが閾値を超えているか判定する関数"""
    return stock.sentiment_score >= min_score

# ---------- 総合スクリーニング ----------
def screen_stocks(
    stocks: List[StockData],
    gap_threshold: float = 3.0,
    min_volume: int = 100_000,
    min_rotation: float = 50.0,
    min_sentiment: float = 3.0,
) -> List[StockData]:
    """
    条件をすべて満たす銘柄だけを返す総合フィルター関数
    - gap_threshold:   ギャップ率(%)
    - min_volume:      プレマーケット出来高
    - min_rotation:    Float Rotation(%)
    - min_sentiment:   SNS／News スコア
    """
    screened: List[StockData] = []
    for stk in stocks:
        if (
            passes_gap(stk, gap_threshold)
            and passes_volume(stk, min_volume)
            and passes_float_rotation(stk, min_rotation)
            and passes_sentiment(stk, min_sentiment)
        ):
            screened.append(stk)
    return screened

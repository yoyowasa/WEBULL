from pathlib import Path
import yaml
import logging
from dataclasses import dataclass            # ── データ保持用クラスに必要
from typing import List                      # ── リスト型ヒントで使用
# 共通ロガー
logger = logging.getLogger("gap_bot.filters")

def _load_cfg(cfg_path: str | Path) -> dict:
    """YAML 設定を読み込み dict で返す"""
    cfg_file = Path(cfg_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"config not found: {cfg_file}")
    with cfg_file.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
from dataclasses import dataclass            # ── データ保持用クラスに必要
from typing import List                      # ── リスト型ヒントで使用

@dataclass
class StockData:
    """1 銘柄のプレマーケット情報を保持する箱"""
    symbol: str
    previous_close: float                    # 前日終値
    premarket_price: float                   # プレマーケット価格
    premarket_volume: int                    # プレマーケット出来高
    float_shares: int                        # 流通株数 (Float)
    sentiment_score: float                   # SNS／News スコア

# ────────── 個別判定ロジック ──────────
def calculate_gap_percent(stock: StockData) -> float:
    """ギャップ率(%)を計算: (pre − prev) ÷ prev ×100"""
    return (stock.premarket_price - stock.previous_close) / stock.previous_close * 100

def passes_gap(stock: StockData, threshold: float) -> bool:
    """ギャップ率が threshold 以上なら True"""
    return calculate_gap_percent(stock) >= threshold

def calculate_float_rotation(stock: StockData) -> float:
    """Float Rotation(%) = volume ÷ float ×100（float=0 なら 0）"""
    return stock.premarket_volume / stock.float_shares * 100 if stock.float_shares else 0.0

def passes_float_rotation(stock: StockData, min_rotation: float) -> bool:
    """Float Rotation が min_rotation 以上か判定"""
    return calculate_float_rotation(stock) >= min_rotation

def passes_volume(stock: StockData, min_volume: int) -> bool:
    """出来高が min_volume 以上か判定"""
    return stock.premarket_volume >= min_volume

def passes_sentiment(stock: StockData, min_score: float) -> bool:
    """SNS／News スコアが min_score 以上か判定"""
    return stock.sentiment_score >= min_score

# ────────── 総合スクリーニング ──────────
def screen_stocks(
    stocks: List[StockData],
    gap_threshold: float = 3.0,
    min_volume: int = 100_000,
    min_rotation: float = 50.0,
    min_sentiment: float = 3.0,
) -> List[StockData]:
    """4 条件すべて通過した銘柄だけを返す"""
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


def build_filters(cfg_path: str | Path):
    """
    screen_config.yaml を読み込み、4 種のフィルタ関数を生成して dict で返す
      ├ gap_ok    : ギャップ率フィルタ
      ├ vol_ok    : 出来高フィルタ
      ├ rot_ok    : Float Rotation フィルタ
      └ sent_ok   : SNS／News スコアフィルタ
    """
    cfg = _load_cfg(cfg_path)

    gap_th = cfg["gap"] / 100           # % を小数に変換
    vol_th = cfg["vol"]
    rot_th = cfg["rot"] / 100
    sent_th = cfg["sent"]

    def gap_ok(gap_pct: float) -> bool:
        """ギャップ率が許容範囲内か判定"""
        return abs(gap_pct) < gap_th

    def vol_ok(volume: int) -> bool:
        """出来高が閾値以上か判定"""
        return volume >= vol_th

    def rot_ok(float_rot: float) -> bool:
        """Float Rotation が閾値以上か判定"""
        return float_rot >= rot_th

    def sent_ok(sentiment: float) -> bool:
        """SNS／News スコアが閾値以上か判定"""
        return sentiment >= sent_th

    logger.debug(
        "filters ready (gap=%s vol=%s rot=%s sent=%s)",
        gap_th, vol_th, rot_th, sent_th
    )

    # 呼び出し側で {'gap_ok': func, ...} として受け取る
    return {
        "gap_ok": gap_ok,
        "vol_ok": vol_ok,
        "rot_ok": rot_ok,
        "sent_ok": sent_ok,
    }

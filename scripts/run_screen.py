"""
scripts.run_screen
------------------
Step 1  : プレマーケット銘柄スクリーナー

* provider = webull | alpaca を選択
* 出力 : 条件を満たした銘柄を JSON 保存 & 標準出力に一覧表示
"""

# ── インポート（冒頭で統一） ───────────────────────────
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List

from gap_bot.filters import StockData, screen_stocks

# Webull 公式 SDK ラッパー
from sdk.webull_sdk_wrapper import WebullClient  # type: ignore

# Alpaca ラッパー（provider=alpaca の時だけ使う）
try:
    from sdk.quotes_alpaca import list_premarket_gappers  # type: ignore
except ImportError:
    list_premarket_gappers = None  # Alpaca 利用しない場合ここは None

# ── Webull 用データ取得 ──────────────────────────────
def fetch_premarket_webull(client: WebullClient) -> List[StockData]:
    """何をする関数? → Webull から Top Gainer を取り込み StockData に正規化"""
    raw_list = client.get_premarket_gainers()
    out: List[StockData] = []
    for item in raw_list:
        out.append(
            StockData(
                symbol=item["symbol"],
                previous_close=item["prevClose"],
                premarket_price=item["preMarketPrice"],
                premarket_volume=item["preMarketVolume"],
                float_shares=item.get("floatShares", 0),
                sentiment_score=item.get("sentimentScore", 0.0),
            )
        )
    return out


# ── Alpaca 用データ取得 ────────────────────────────────
def fetch_premarket_alpaca(symbols: List[str]) -> List[StockData]:
    """何をする関数? → Alpaca REST から Gap% 条件を満たす銘柄を正規化"""
    if list_premarket_gappers is None:
        raise RuntimeError("sdk.quotes_alpaca がインポートできません")

    raw_list = list_premarket_gappers(symbols=symbols)
    out: List[StockData] = []
    for item in raw_list:
        out.append(
            StockData(
                symbol=item["symbol"],
                previous_close=item["prevClose"],
                premarket_price=item["preMarketPrice"],
                premarket_volume=item["preMarketVolume"],
                float_shares=item.get("floatShares", 0),
                sentiment_score=item.get("sentimentScore", 0.0),
            )
        )
    return out


# ── CLI 引数 ───────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pre-market gap screener")
    p.add_argument("--provider", choices=["webull", "alpaca"], default="webull")
    p.add_argument("--symbols", type=Path, help="監視ティッカーリスト (alpaca 専用)")
    p.add_argument("--gap", type=float, default=3.0, help="Gap%% threshold")
    p.add_argument("--vol", type=int, default=100_000, help="Premarket volume threshold")
    p.add_argument("--rot", type=float, default=50.0, help="Float rotation threshold")
    p.add_argument("--sent", type=float, default=3.0, help="Sentiment score threshold")
    p.add_argument(
        "--out",
        type=Path,
        default=Path(f"screened_{datetime.utcnow():%Y%m%d}.json"),
        help="Output JSON file",
    )
    return p.parse_args()


# ── メイン ────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    # 1) データ取得
    if args.provider == "webull":
        client = WebullClient.from_env()
        raw_stocks = fetch_premarket_webull(client)
    else:  # alpaca
        if args.symbols is None or not args.symbols.exists():
            raise SystemExit("alpaca 利用時は --symbols <file> が必須です")
        symbols = [s.strip() for s in args.symbols.read_text().splitlines() if s.strip()]
        raw_stocks = fetch_premarket_alpaca(symbols)

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

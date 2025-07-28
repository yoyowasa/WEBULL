
"""
プレマーケットのギャップアップ銘柄を抽出するバッチスクリプト
Step1：銘柄スクリーンニング
"""

# ===== インポート（ファイル冒頭に統一） =====
import argparse
import json
from datetime import datetime
from pathlib import Path

from sdk.webull_sdk_wrapper import WebullClient  # 公式 SDK ラッパー
from gap_bot.filters import StockData, screen_stocks

# ===== 関数群 =====
def fetch_premarket_data(client: WebullClient) -> list[StockData]:
    """Webull からプレマーケットデータを取得し StockData リストに変換する関数"""
    raw_list = client.get_premarket_gainers()  # ラッパーのメソッド名は実装に合わせて調整
    stocks: list[StockData] = []
    for item in raw_list:
        stocks.append(
            StockData(
                symbol=item["symbol"],
                previous_close=item["prevClose"],
                premarket_price=item["preMarketPrice"],
                premarket_volume=item["preMarketVolume"],
                float_shares=item["floatShares"],
                sentiment_score=item["sentimentScore"],
            )
        )
    return stocks


def parse_args() -> argparse.Namespace:
    """CLI からフィルター閾値と出力ファイル名を受け取る関数"""
    parser = argparse.ArgumentParser(description="Premarket gap screener")
    parser.add_argument("--gap", type=float, default=3.0, help="Gap percent threshold")
    parser.add_argument("--vol", type=int, default=100_000, help="Minimum premarket volume")
    parser.add_argument("--rot", type=float, default=50.0, help="Minimum float‑rotation percent")
    parser.add_argument("--sent", type=float, default=3.0, help="Minimum sentiment score")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(f"screened_{datetime.utcnow():%Y%m%d}.json"),
        help="Output JSON file",
    )
    return parser.parse_args()


def main() -> None:
    """スクリプト全体をまとめるメイン関数"""
    args = parse_args()

    # 1) データ取得
    client = WebullClient.from_env()  # .env で認証情報を管理
    raw_stocks = fetch_premarket_data(client)

    # 2) スクリーニング
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
        print(f"{s.symbol:<6}  Gap {gap_pct:5.2f}%  Vol {s.premarket_volume:,}")

    args.out.write_text(json.dumps([s.__dict__ for s in screened], indent=2))
    print(f"\n{len(screened)} tickers saved → {args.out.resolve()}")


# ===== エントリーポイント =====
if __name__ == "__main__":
    main()

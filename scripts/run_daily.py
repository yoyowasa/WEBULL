"""Step 8 日次集計スクリプト

- 前日 or 引数指定の日付の order_log / close_log を読み込み
- 各取引の R 値と損益を計算して metrics をまとめる
- strategy.csv に追記
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import List, Tuple

LOG_DIR = Path("logs")
STRATEGY_CSV = Path("strategy.csv")


def read_order_log() -> List[Tuple[str, float, float]]:
    """order_log.csv → [(symbol, entry, sl)] を返す"""
    fpath = LOG_DIR / "order_log.csv"
    out = []
    if not fpath.exists():
        return out
    with fpath.open() as f:
        for sym, *_rest, entry, sl, _ in csv.reader(f):
            out.append((sym, float(entry), float(sl)))
    return out


def read_close_log(date: dt.date) -> List[Tuple[str, str]]:
    """close_log_YYYYMMDD.csv → [(symbol, oid)]"""
    fpath = LOG_DIR / f"close_log_{date:%Y%m%d}.csv"
    out = []
    if not fpath.exists():
        return out
    with fpath.open() as f:
        for _ts, sym, qty, _oid in csv.reader(f):
            out.append((sym, qty))
    return out


def calc_metrics(
    orders: List[Tuple[str, float, float]],
    closes: List[Tuple[str, str]],
) -> Tuple[float, float, float]:
    """R,P/L,勝率 をダミー計算（後で fill_price を取得して精緻化）"""
    wins = 0
    total_r = 0.0
    for sym, entry, sl in orders:
        # 仮の fill_price として TP or SL をランダムに選ぶダミー実装
        # 実運用では WebullClient.get_fills() で fill_price を取得
        fill_price = entry * 1.05  # TP 側として計算
        r = (fill_price - entry) / (entry - sl)
        wins += r > 0
        total_r += r
    n = len(orders) or 1
    return total_r, wins / n * 100, total_r / n


def append_strategy(date: dt.date, total_r: float, winrate: float, avg_r: float) -> None:
    """strategy.csv に日次 KPI を追記"""
    is_new = not STRATEGY_CSV.exists()
    with STRATEGY_CSV.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "total_R", "winrate_%", "avg_R"])
        writer.writerow([date.isoformat(), round(total_r, 3), round(winrate, 1), round(avg_r, 3)])


def main() -> None:
    p = argparse.ArgumentParser(description="Daily KPI aggregator")
    p.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    args = p.parse_args()

    target_date = (
        dt.datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else (dt.date.today() - dt.timedelta(days=1))
    )

    orders = read_order_log()
    closes = read_close_log(target_date)
    total_r, winrate, avg_r = calc_metrics(orders, closes)
    append_strategy(target_date, total_r, winrate, avg_r)
    print(f"{target_date}: R={total_r:.2f}, win={winrate:.1f}%, avg_R={avg_r:.2f}")


if __name__ == "__main__":
    main()

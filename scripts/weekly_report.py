
"""Step 10 : Weekly KPI Report

直近 7 days の strategy.csv → KPI 集計 → console & CSV
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_CSV = Path("strategy.csv")
LOG_DIR = Path("logs")


def load_last_n_days(n: int = 7) -> pd.DataFrame:
    df = pd.read_csv(STRATEGY_CSV, parse_dates=["date"])
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=n)
    return df[df["date"] >= cutoff]


def calc_week_metrics(df: pd.DataFrame) -> dict[str, float]:
    total_r = df["total_R"].sum()
    avg_r = df["avg_R"].mean() if not df.empty else 0.0
    winrate = df["winrate_%"].mean() if not df.empty else 0.0
    returns = df["total_R"].to_numpy()
    sharpe = (returns.mean() / returns.std()) * np.sqrt(len(returns)) if returns.size > 1 and returns.std() else 0.0
    return {"total_R": total_r, "avg_R": avg_r, "winrate_%": winrate, "Sharpe": sharpe}


def save_weekly_report(metrics: dict[str, float]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fname = LOG_DIR / f"weekly_report_{dt.date.today():%Y%m%d}.csv"
    is_new = not fname.exists()
    with fname.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", *metrics.keys()])
        writer.writerow([dt.date.today().isoformat(), *[round(v, 3) for v in metrics.values()]])


def main() -> None:
    p = argparse.ArgumentParser(description="Weekly KPI report")
    p.add_argument("--days", type=int, default=7, help="対象日数 (default: 7)")
    args = p.parse_args()

    df = load_last_n_days(args.days)
    if df.empty:
        print("No data for weekly report.")
        return

    metrics = calc_week_metrics(df)
    save_weekly_report(metrics)

    print("---- Weekly KPI ----")
    for k, v in metrics.items():
        print(f"{k:12}: {v:.3f}")


if __name__ == "__main__":
    main()

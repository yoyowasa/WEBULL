"""Step 11 : Monthly parameter re-optimisation

strategy.csv の 90 day KPI を基に Kelly, Gap%, TP, SL を再計算し
configs/config.yaml を上書きする
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
from pathlib import Path
import yaml
import pandas as pd

STRATEGY_CSV = Path("strategy.csv")
CONFIG_YAML = Path("configs/config.yaml")


def load_kpi(days: int = 90) -> pd.DataFrame:
    """直近 days 日ぶんの KPI（total_R）を返す関数"""
    df = pd.read_csv(STRATEGY_CSV, parse_dates=["date"])
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    return df[df["date"] >= cutoff]


def grid_search(df: pd.DataFrame) -> dict[str, float]:
    """粗いグリッド探索で Kelly, Gap, TP, SL を決める関数"""
    best = {"score": -1e9}
    for kelly in (0.2, 0.3, 0.4, 0.5):
        for gap in (0.03, 0.04, 0.05):
            for tp in (0.05, 0.07, 0.10):
                for sl in (0.02, 0.025, 0.03):
                    pl = (df["total_R"] * kelly * (tp / sl)).sum()
                    if pl > best["score"]:
                        best.update({"kelly": kelly, "gap": gap, "tp": tp, "sl": sl, "score": pl})
    return best


def update_yaml(params: dict[str, float]) -> None:
    """config.yaml の該当パラメータを書き換える関数"""
    CONFIG_YAML.parent.mkdir(exist_ok=True)
    if CONFIG_YAML.exists():
        with CONFIG_YAML.open() as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}
    cfg.update({
        "kelly": params["kelly"],
        "gap_threshold": params["gap"],
        "tp_pct": params["tp"],
        "sl_pct": params["sl"],
        "updated_at": dt.datetime.utcnow().isoformat(),
    })
    with CONFIG_YAML.open("w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def main() -> None:
    p = argparse.ArgumentParser(description="Monthly parameter optimiser")
    p.add_argument("--days", type=int, default=90, help="学習対象日数 (default: 90)")
    args = p.parse_args()

    df = load_kpi(args.days)
    if df.empty:
        print("データが不足しています。")
        return

    best = grid_search(df)
    update_yaml(best)
    print("---- New Params ----")
    for k in ("kelly", "gap", "tp", "sl"):
        print(f"{k:12}: {best[k]:.3f}")
    print(f"score: {best['score']:.2f}")


if __name__ == "__main__":
    main()

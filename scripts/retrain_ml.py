
"""Step 9  : ML フィードバック β版
strategy.csv → 特徴量 → LightGBM でオンライン学習し、model.pkl を更新する
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

STRATEGY_CSV = Path("strategy.csv")
MODEL_PATH = Path("gap_bot/ml/model.pkl")


def load_dataset(days: int | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """strategy.csv から直近 days 日 (None: 全期間) を読み出して X, y を返す"""
    df = pd.read_csv(STRATEGY_CSV, parse_dates=["date"])
    if days:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df["date"] >= cutoff]
    X = df[["total_R", "winrate_%", "avg_R"]]
    y = (df["total_R"] > 0).astype(int)  # 黒字 = 1, 赤字 = 0
    return X, y


def incremental_train(model: lgb.LGBMClassifier | None, X: pd.DataFrame, y: pd.Series) -> lgb.LGBMClassifier:
    """既存モデルがあれば partial_fit、無ければ新規学習"""
    if model is None:
        model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, objective="binary")
        model.fit(X, y)
    else:
        model.fit(X, y, init_model=model.booster_)
    return model


def save_model(model: lgb.LGBMClassifier) -> None:
    """モデルを pkl で保存"""
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as f:
        pickle.dump(model, f)


def main() -> None:
    p = argparse.ArgumentParser(description="Online ML retrain")
    p.add_argument("--days", type=int, default=30, help="直近 N 日のみで再学習 (default: 30)")
    args = p.parse_args()

    X, y = load_dataset(days=args.days)
    if X.empty:
        print("No data to train.")
        return

    model = None
    if MODEL_PATH.exists():
        with MODEL_PATH.open("rb") as f:
            model = pickle.load(f)

    model = incremental_train(model, X, y)
    save_model(model)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    auc = roc_auc_score(y_te, model.predict_proba(X_te)[:, 1])
    print(f"Model updated. AUC={auc:.3f}")


if __name__ == "__main__":
    main()

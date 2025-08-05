"""logger.append_csv の基本動作テスト

- logs/ ディレクトリが無い場合でも自動生成されるか
- 1 行追記でファイルサイズ（行数）が +1 になるか
"""

import os
import csv
import shutil
from pathlib import Path

from gap_bot.utils.logger import append_csv, LOG_DIR


def setup_function():
    """テスト前処理： logs/ を真っさらにする"""
    if LOG_DIR.exists():
        shutil.rmtree(LOG_DIR)  # 完全削除（空ディレクトリから検証）


def test_append_creates_dir_and_file():
    # まだ logs/ もファイルも無い状態
    target = "unit_test.csv"
    assert not LOG_DIR.exists()

    # 1 行追記
    append_csv(target, ["foo", "bar", 123])

    # ── 検証 ──────────────────────────────
    # ① logs/ ディレクトリが生成された
    assert LOG_DIR.exists() and LOG_DIR.is_dir()

    # ② ファイルが生成された
    fpath = LOG_DIR / target
    assert fpath.exists()

    # ③ 行数が 1 行
    with fpath.open() as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert len(rows) == 1 and rows[0] == ["foo", "bar", "123"]  # csv は str 型

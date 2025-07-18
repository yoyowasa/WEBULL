"""config.py  
YAML 形式の設定ファイル (`configs/config.yaml`) を読み込むユーティリティ。

今は最小実装として、辞書を返すだけに留めています。
後でバリデーションやデフォルト値の注入を追加していきます。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# プロジェクトのルートを基準に `configs/config.yaml` を探す
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "config.yaml"


def load_config(path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    """
    YAML を読み込み Python dict で返す。

    Parameters
    ----------
    path : str | Path | None, optional
        読み込むファイルパス。指定がなければ
        1. 環境変数 ``GAP_BOT_CONFIG``、
        2. `configs/config.yaml` （リポジトリ既定）
        の順に探索する。

    Returns
    -------
    dict
        設定内容
    """
    file_path = (
        Path(path)
        if path is not None
        else Path(os.getenv("GAP_BOT_CONFIG", DEFAULT_CONFIG_PATH))
    )

    if not file_path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

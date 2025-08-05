"""共通 CSV ロガー

append_csv(path, row) を呼ぶだけで logs/ 以下に追記できる。
"""

import csv
from pathlib import Path
import logging

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,                             # ここでログレベルなどをまとめて設定
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("gap_bot")    
logger.setLevel(logging.DEBUG)

def append_csv(path: str, row: list[str]) -> None:
    """CSV ファイルに行追記（ヘッダ無し・改行コード自動）"""
    file_path = LOG_DIR / path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("a", newline="") as f:
        csv.writer(f).writerow(row)

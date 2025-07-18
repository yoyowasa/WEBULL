"""run_screen.py  
Step 1 : プレマーケット銘柄スクリーニングを実行するエントリポイント
"""
from gap_bot.filters import screen_gappers
from gap_bot.utils.config import load_config


def main() -> None:
    """config.yaml を読み込み、スクリーナーを実行して結果を出力するだけ。"""
    config = load_config()
    results = screen_gappers(config)
    for symbol in results:
        print(symbol)


if __name__ == "__main__":
    main()

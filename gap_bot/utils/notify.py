# -*- coding: utf-8 -*-
"""
役割: Discord Webhook へメッセージを送信するユーティリティ関数を提供する
"""

# ---- import（ファイル冒頭で統一）----
import os          # 環境変数から Webhook URL を読み取る
import json        # Discord へ送るペイロードを構築
import requests    # HTTP POST を実行
try:
    from dotenv import load_dotenv  # .env から環境変数を読み込むためのライブラリ
    load_dotenv()  # 何をする行か：モジュール読み込み時に一度だけ .env を取り込んで DISCORD_WEBHOOK_URL を使えるようにする
except Exception:
    pass  # ライブラリ未導入でも通知機能自体は動かすために握りつぶす

# ---- 関数定義 ----
def send_discord_message(content: str) -> None:
    """
    役割: 引数で受け取った文字列を Discord Webhook へ送信する

    Parameters
    ----------
    content : str
        投稿したいメッセージ本文 (2000 文字以内推奨)
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return  # URL 未設定なら何もしない

    payload = {
        "content": content
    }

    # 何をするコードか: Discord に JSON ペイロードを POST する
    try:
        requests.post(webhook_url, data=json.dumps(payload), timeout=5)
    except requests.RequestException:
        # 通知失敗で取引を止めないよう、例外は握りつぶす
        pass

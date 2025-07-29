
# Webull Gap-Bot

## 📜 What is this?
プレマーケットで **ギャップアップ** した銘柄をスクリーニングし、  
条件を満たすものだけに **指値エントリー＋TP/SL ブラケット** を自動発注するボット。  
日中は **10:00 ET キャンセル** & **BE スライド** を自律実行します。

---

## 🚀 Quick Start

```bash
# 1. clone
git clone <your-repo-url> && cd webull_bot

# 2. create env (Poetry uses Python 3.11)
poetry install --no-root

# 3. set Webull creds in .env
cp .env.example .env
#   → WEBULL_APP_ID, APP_SECRET, ACCESS_TOKEN, ACCOUNT_ID を入力

# 4. run screener (Step 2)
poetry run python scripts/run_screen.py

# 5. place entries (Step 3)
poetry run python scripts/run_entry.py --screened screened_YYYYMMDD.json --equity 100000

# 6. live monitor (Step 4)
poetry run python scripts/run_live.py


cd E:\webull_bot
poetry shell
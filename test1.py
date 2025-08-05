import pandas as pd
import yfinance as yf
import time

# ティッカーリストをロード
df = pd.read_csv("us_equities.csv")
tickers = df["Unnamed: 0"].dropna().unique().tolist()

small_caps = []
for i, ticker in enumerate(tickers):
    try:
        info = yf.Ticker(ticker).info
        market_cap = info.get("marketCap")
        if market_cap is not None and market_cap < 2_000_000_000:  # 20億ドル未満＝Small Cap
            small_caps.append(ticker)
            print(f"{ticker}: {market_cap}")
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
    # 取得制限対策でスリープ（Yahoo制限回避。速すぎるとBAN）
    time.sleep(1)

# 抽出結果を書き出し
with open("symbols_nyse_small.txt", "w") as f:
    for t in small_caps:
        f.write(f"{t}\n")

print(f"抽出された小型株の数: {len(small_caps)}")

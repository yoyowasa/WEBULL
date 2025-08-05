import requests
import pandas as pd

url = "https://api.iextrading.com/1.0/ref-data/symbols"
r = requests.get(url)
print("レスポンスの中身（先頭500文字）:", r.text[:500])
print("ステータスコード:", r.status_code)
try:
    data = r.json()
except Exception:
    print("JSONじゃないデータが返ってきました！")
    print(r.text)
    exit(1)

df = pd.DataFrame(data)
# "isEnabled"がTrueかつ"exchange"=="IEXG"ならIEX上場
df_iex = df[(df["isEnabled"]) & (df["exchange"] == "IEXG")]
df_iex["symbol"].to_csv("iex_symbols.txt", index=False, header=False)

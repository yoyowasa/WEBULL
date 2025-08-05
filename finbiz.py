import requests
from bs4 import BeautifulSoup
import time

all_caps = ['cap_micr', 'cap_small', 'cap_mid']
tickers = set()

for cap in all_caps:
    for page in range(1, 101):
        url = f"https://finviz.com/screener.ashx?v=111&f={cap},geo_usa&r={(page-1)*20+1}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        print(r.text[:1000])  # ←ここで出力！
        soup = BeautifulSoup(r.text, "html.parser")
        ticker_links = soup.find_all("a", class_="screener-link-primary")
        if not ticker_links:
            break
        for link in ticker_links:
            ticker = link.text.strip()
            tickers.add(ticker)
        time.sleep(0.1)
    print(f"{cap} done. 現在までのユニーク銘柄数: {len(tickers)}")

with open("symbols_usa_large.txt", "w") as f:
    for t in sorted(tickers):
        f.write(f"{t}\n")
print(f"抽出ティッカー総数: {len(tickers)}")

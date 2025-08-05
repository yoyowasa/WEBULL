from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import os, pprint
from dotenv import load_dotenv
load_dotenv()

client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
load_dotenv()

sym = "PLTR"

# Quote (最新)
from sdk.quotes_alpaca import get_quote
print("Quote:")
pprint.pp(get_quote(sym))

# 昨日の日足 (IEX)
bars = client.get_stock_bars(
    StockBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, limit=3, feed="iex")
).df

if bars.empty:
    print("Bars EMPTY — IEX 無料フィードは終値なし")
else:
    print(bars[["t", "o", "h", "l", "c"]])


from dotenv import load_dotenv
import os
from webullsdkcore.common.region import Region
from webullsdkquotescore.grpc.grpc_client import GrpcApiClient
from webullsdktrade.grpc_api import API as GrpcTradeApi

load_dotenv()                               # .env を読む
app_key    = os.getenv("WEBULL_APP_KEY")
app_secret = os.getenv("WEBULL_SECRET")
region     = Region.JP.value                # ← 口座リージョン

# ★ 2025-07 時点で JP quotes ホストが DNS 未登録のため、US ホストを暫定利用
grpc_host  = "quoteapi.webull.com"

grpc_cli = GrpcApiClient(app_key, app_secret, region, host=grpc_host)
grpc_api = GrpcTradeApi(grpc_cli)

resp = grpc_api.market_data.get_token()     # ← 公式フロー
if resp.status_code == 200:
    token = resp.json()                     # これが access_token
    print("token =", token)
else:
    print(resp.status_code, resp.text)      # 403 → 権限不足 / 503 → サーバ停止


from webullsdkcore.client import ApiClient
from webullsdktrade.api import API
api_client = ApiClient(
    app_key='11e47bd33f09aaadf4751889a22cd1f',
    app_secret='14d429cda218870b37b254944e385a38',
    # そのほか必要なパラメータ
)

try:
    api_client.fetch_access_token()
    print("access_token:", api_client.access_token)
except Exception as e:
    print("token取得失敗:", e)
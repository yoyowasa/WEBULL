from webullsdkcore.client import ApiClient
from dotenv import load_dotenv
import os

load_dotenv()  # .envから環境変数を読み込む

client = ApiClient(
    app_key=os.environ["WEBULL_APP_KEY"],
    app_secret=os.environ["WEBULL_SECRET"],
    # region_idやaccount_idも必要なら追加
)

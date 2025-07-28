
"""
sdk.webull_sdk_wrapper
----------------------
公式 Webull Python SDK を薄くラップする最小クライアント。
関数ごとに「何をする関数なのか」を異形で明記する。
"""

# すべての import はファイル冒頭に統一
import os
from typing import Any

# sdk/webull_sdk_wrapper.py の冒頭に、必ずこの３行だけを残す
from webullsdkcore.client               import ApiClient
from webullsdktrade.api                 import API        as TradeApi
from webullsdkquotescore.quotes_client import QuotesClient as QuotesApi




class WebullClient:
    """Webull 公式 SDK を操作する便利クラス。"""

    def __init__(self) -> None:
        # 何をする？ → 環境変数から認証情報を取得
        app_id: str | None = os.getenv("WEBULL_APP_ID")
        app_secret: str | None = os.getenv("WEBULL_APP_SECRET")
        if not app_id or not app_secret:
            raise RuntimeError(
                "環境変数 WEBULL_APP_ID / WEBULL_APP_SECRET を設定してください"
            )

        # 何をする？ → SDK の共通 ApiClient を初期化
        self._client = ApiClient(
            app_id=app_id,
            app_secret=app_secret,
            region="US",      # 必要なら可変にしても良い
            is_sandbox=True,  # 本番は False
        )

        # 何をする？ → API モジュールをプロパティに保持
        self.trade_api = TradeApi(self._client)
        self.quotes_api = QuotesApi(self._client)

    # -------------------------------------------------
    # 公開メソッド
    # -------------------------------------------------

    def get_quote(self, symbol: str) -> dict[str, Any]:
        """指定シンボルの最新株価スナップショットを取得する。"""
        return self.quotes_api.get_snapshot(
            category="US_STOCK",
            symbols=symbol,
        )

    def place_market_order(
        self,
        ticker: str,
        quantity: int,
        side: str = "BUY",
        time_in_force: str = "DAY",
    ) -> dict[str, Any]:
        """成行で株式注文を発注する。"""
        return self.trade_api.place_order(
            category="US_STOCK",
            ticker=ticker,
            price_type="MARKET",
            order_type=side,   # BUY / SELL
            qty=quantity,
            time_in_force=time_in_force,
        )

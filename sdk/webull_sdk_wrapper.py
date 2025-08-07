"""
sdk.webull_sdk_wrapper
----------------------
公式 Webull SDK を “使いやすい 1 クラス” にまとめた薄ラッパー。
スクリプト側は WebullClient だけ import すれば OK。

■ 依存ライブラリ
- webull-python-sdk-core        (共通基盤クライアント)
- webull-python-sdk-quotes      (気配 & 市況データ)
- webull-python-sdk-trade       (発注まわり)
- python-dotenv                 (.env 読み込み用)

■ 必要な環境変数 (.env)
WEBULL_APP_KEY, WEBULL_SECRET, ACCOUNT_ID
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from webullsdkcore.client import ApiClient                # 共通 HTTP 基盤
from webullsdkquotescore.quotes_client import QuotesClient        # 気配
from webullsdktrade.api import API as TradeApi            # 発注

__all__ = ["WebullClient"]


class WebullClient:
    """QuotesClient と TradeClient をまとめた便利クラス"""

    # ---------- 初期化 ----------
    def __init__(
        self,
        app_key: str,
        secret: str,
        account_id: str,
        region: str = "US",
    ) -> None:
        self._api = ApiClient(app_key=app_key, app_secret=secret)
        self.quotes = QuotesClient(app_key=app_key, app_secret=secret)
        self.trade = TradeApi(self._api,)
        self.account_id = account_id

    # ---------- ファクトリ ----------
    @classmethod
    def from_env(cls) -> "WebullClient":
        """
        .env または環境変数から認証情報を読んで初期化
        必須キー: WEBULL_APP_KEY / WEBULL_SECRET / ACCOUNT_ID
        """
        load_dotenv()  # .env が無ければ空読みされるだけ

        keys = ("WEBULL_APP_KEY", "WEBULL_SECRET", "ACCOUNT_ID")
        missing = [k for k in keys if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"環境変数が足りません: {', '.join(missing)}")

        return cls(
            app_key=os.environ["WEBULL_APP_KEY"],
            secret=os.environ["WEBULL_SECRET"],
            account_id=os.environ["ACCOUNT_ID"],
        )

    # ======================================================================
    #  -----------  Market-Data ラッパー  ----------------------------------
    # ======================================================================
    def get_premarket_gainers(self) -> List[Dict[str, Any]]:
        """
        プレマーケットの Top Gainers を取得して
        Step 2 で期待するキー構造に整形して返す
        """
        raw = self.quotes.get_top_list(list_type="gainers", sub_type="preMarket")

        out: List[Dict[str, Any]] = []
        for item in raw.get("data", []):
            out.append(
                {
                    "symbol": item["tickerId"],
                    "prevClose": item["preClose"],
                    "preMarketPrice": item["last"],
                    "preMarketVolume": item["volume"],
                    "floatShares": item.get("floatShares", 0),
                    "sentimentScore": item.get("sentimentScore", 0.0),
                }
            )
        return out

    def get_quote(self, symbol: str, *, extended: bool = True) -> Dict[str, Any]:
        """Bid / Ask を含む最新気配を取得"""
        return self.quotes.get_quote(symbol=symbol, include_pre=extended)

    # ======================================================================
    #  -----------  Trading ラッパー  --------------------------------------
    # ======================================================================
    # 指値発注 --------------------------------------------------------------
    def place_limit_order(
        self,
        *,
        symbol: str,
        qty: int,
        price: float,
        extended_hours: bool = True,
        tif: str = "GTC",
    ) -> Dict[str, Any]:
        return self.trade.place_order(
            symbol=symbol,
            order_type="LMT",
            side="BUY",
            quantity=qty,
            price=price,
            time_in_force=tif,
            extended_hours=extended_hours,
        )

    # ブラケット添付 --------------------------------------------------------
    def attach_bracket(
        self,
        *,
        parent_order_id: str,
        take_profit: float,
        stop_loss: float,
        break_even_distance: float,
    ) -> Dict[str, Any]:
        return self.trade.attach_bracket_order(
            parent_order_id=parent_order_id,
            take_profit=take_profit,
            stop_loss=stop_loss,
            break_even_distance=break_even_distance,
        )

    # 注文取得・キャンセル --------------------------------------------------
    def get_active_orders(self) -> List[Dict[str, Any]]:
        return self.trade.get_active_orders().get("data", [])

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self.trade.cancel_order(order_id=order_id)

    # ポジション & ブラケット ----------------------------------------------
    def get_positions(self) -> List[Dict[str, Any]]:
        return self.trade.get_positions().get("data", [])

    def get_bracket(self, symbol: str) -> Optional[Dict[str, Any]]:
        for order in self.get_active_orders():
            if order["symbol"] == symbol and order.get("orderType") in ("TP", "SL"):
                return order
        return None

    def modify_bracket(self, *, order_id: str, stop_loss: float) -> Dict[str, Any]:
        return self.trade.modify_order(order_id=order_id, stop_loss=stop_loss)

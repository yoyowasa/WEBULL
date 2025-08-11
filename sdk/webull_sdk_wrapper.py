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
from decimal import Decimal, ROUND_HALF_UP  # 何をする行か: 価格をティックサイズ(例:$0.01)へ安全に丸めるために使う

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
    def place_limit_order(self, symbol: str, side: str, qty: float, price: float, time_in_force: str = "DAY", extended: bool = False, take_profit: float | None = None, stop_loss: float | None = None) -> dict:
        """何をする関数なのか: 指値の新規注文(必要に応じてTP/SL同梱)を、SDK差異を吸収しながら発注し、orderId等を標準化して返す"""
        # 何をする行か: 入力を正規化（記号・大文字小文字・数量/価格の体裁）
        sym = str(symbol).strip()
        act = str(side).strip().upper()
        action = "BUY" if act in {"BUY", "LONG"} else "SELL"
        qty_int = max(1, int(qty))  # 何をする行か: 株数は整数に丸め、最低1株を保証
        px = float(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))  # 何をする行か: 価格を$0.01刻みに丸める

        def _extract_oid(r: object) -> str | None:
            """何をする関数なのか: SDKごとに異なるレスポンスから注文ID相当を見つける"""
            if isinstance(r, dict):
                for k in ("orderId", "id", "oid", "clientOrderId", "cloid"):
                    if k in r and r[k]:
                        return str(r[k])
                d = r.get("data") if "data" in r else None
                if isinstance(d, dict):
                    for k in ("orderId", "id", "oid", "clientOrderId", "cloid"):
                        if k in d and d[k]:
                            return str(d[k])
                    sts = d.get("statuses")
                    if isinstance(sts, list) and sts:
                        for item in sts:
                            for k in ("oid", "orderId", "id", "clientOrderId", "cloid"):
                                if isinstance(item, dict) and item.get(k):
                                    return str(item[k])
            return None

        def _try_call(method_name: str):
            """何をする関数なのか: 指定メソッド名で複数の引数バリエーションを順に試す"""
            if not hasattr(self.trade, method_name):
                return None
            m = getattr(self.trade, method_name)
            # 何をする行か: よくあるキーワード引数パターン(A)
            try:
                return m(
                    symbol=sym, action=action, order_type="limit",
                    limit_price=px, qty=qty_int, time_in_force=time_in_force,
                    extended_hours=extended, take_profit=take_profit, stop_loss=stop_loss
                )
            except TypeError:
                pass
            # 何をする行か: キーワード名が異なるパターン(B)
            try:
                return m(
                    symbol=sym, side=action, type="limit",
                    price=px, quantity=qty_int, tif=time_in_force,
                    ext=extended, tp=take_profit, sl=stop_loss
                )
            except TypeError:
                pass
            # 何をする行か: 位置引数中心のパターン(C)
            try:
                return m(sym, action, qty_int, px, "limit", time_in_force, extended)
            except TypeError:
                pass
            return None

        try:
            resp = None  # 何をする行か: 発注レスポンスの初期化

            # 何をする行か: 代表的なメソッド名から順に試す
            for name in ("place_order", "submit_order", "placeOrder", "order_limit", "order", "create_order"):
                resp = _try_call(name)
                if resp is not None:
                    break

            # 何をする行か: サブクライアント(account)配下の実装へのフォールバック
            if resp is None and hasattr(self.trade, "account"):
                for name in ("place_order", "submit_order", "placeOrder", "order_limit", "order", "create_order"):
                    try:
                        acc = self.trade.account
                        if hasattr(acc, name):
                            m = getattr(acc, name)
                            try:
                                resp = m(
                                    symbol=sym, action=action, order_type="limit",
                                    limit_price=px, qty=qty_int, time_in_force=time_in_force,
                                    extended_hours=extended, take_profit=take_profit, stop_loss=stop_loss
                                )
                            except TypeError:
                                try:
                                    resp = m(
                                        symbol=sym, side=action, type="limit",
                                        price=px, quantity=qty_int, tif=time_in_force,
                                        ext=extended, tp=take_profit, sl=stop_loss
                                    )
                                except TypeError:
                                    try:
                                        resp = m(sym, action, qty_int, px, "limit", time_in_force, extended)
                                    except TypeError:
                                        resp = None
                    except Exception:
                        resp = None
                    if resp is not None:
                        break

            # 何をする行か: どのルートでも発注できなければ失敗を返す
            if resp is None:
                return {"orderId": None, "response": None, "success": False}

            # 何をする行か: レスポンスから注文IDを抽出し、標準化して返す
            oid = _extract_oid(resp)
            return {"orderId": oid, "response": resp, "success": True if oid else False}

        except Exception as e:
            msg = str(e)
            # 何をする行か: 認証切れを検知したら1回だけ再ログイン→再試行
            if "UNAUTHORIZED" in msg or "grpc_status:16" in msg or "UNAUTHENTICATED" in msg:
                if self._relogin():
                    try:
                        return self.place_limit_order(symbol, side, qty, price, time_in_force, extended, take_profit, stop_loss)
                    except Exception:
                        return {"orderId": None, "response": None, "success": False}
                return {"orderId": None, "response": None, "success": False}
            # 何をする行か: その他の例外は失敗として標準形で返す
            return {"orderId": None, "response": None, "success": False}


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
    def get_active_orders(self) -> list:
        """何をする関数なのか: SDKバージョン差（メソッド名・返却形式）を吸収し、現在アクティブな注文一覧をlistで安全に返す"""
        try:
            # 何をする行か: 新系SDKの一般的な名称をまず試す
            if hasattr(self.trade, "get_active_orders"):
                resp = self.trade.get_active_orders()  # 何をする行か: 新系メソッドの呼び出し

            # 何をする行か: 旧系/別実装で使われる名称にフォールバック
            elif hasattr(self.trade, "get_open_orders"):
                resp = self.trade.get_open_orders()  # 何をする行か: 旧系メソッドの呼び出し
            elif hasattr(self.trade, "orders"):
                resp = self.trade.orders()  # 何をする行か: 汎用orders取得の呼び出し
            elif hasattr(self.trade, "get_orders"):
                resp = self.trade.get_orders()  # 何をする行か: 別名の呼び出し

            # 何をする行か: サブクライアント(account)経由の最終フォールバック
            elif hasattr(self.trade, "account") and hasattr(self.trade.account, "get_active_orders"):
                resp = self.trade.account.get_active_orders()  # 何をする行か: account配下の呼び出し
            else:
                return []  # 何をする行か: 取得手段が無ければ空で返す

            # 何をする行か: {"data":[...]} と [...] の両形式に対応
            data = (resp or {}).get("data", resp)
            if not isinstance(data, list):
                return []
            # 何をする行か: Filled/Canceled等を除外できるなら除外（キーが無い実装もあるため安全に）
            return [o for o in data if str(o.get("status", "")).lower() not in {"filled", "canceled", "cancelled"}]
        except Exception as e:
            msg = str(e)
            # 何をする行か: 認証切れの典型ワードなら再ログイン→1回だけリトライ
            if "UNAUTHORIZED" in msg or "grpc_status:16" in msg or "UNAUTHENTICATED" in msg:
                if self._relogin():
                    try:
                        if hasattr(self.trade, "get_active_orders"):
                            resp = self.trade.get_active_orders()
                        elif hasattr(self.trade, "get_open_orders"):
                            resp = self.trade.get_open_orders()
                        elif hasattr(self.trade, "orders"):
                            resp = self.trade.orders()
                        elif hasattr(self.trade, "get_orders"):
                            resp = self.trade.get_orders()
                        elif hasattr(self.trade, "account") and hasattr(self.trade.account, "get_active_orders"):
                            resp = self.trade.account.get_active_orders()
                        else:
                            return []
                        data = (resp or {}).get("data", resp)
                        if not isinstance(data, list):
                            return []
                        return [o for o in data if str(o.get("status", "")).lower() not in {"filled", "canceled", "cancelled"}]
                    except Exception:
                        return []
                return []
            raise  # 何をする行か: 認証以外の想定外は上位で処理してもらう


    def cancel_order(self, order_id, _retry=False) -> bool:
        """何をする関数なのか: SDKのメソッド名・引数差・返却形式の違いを吸収し、指定注文IDの取消を確実に試みて成功可否をboolで返す"""
        oid = str(order_id)  # 何をする行か: IDを文字列に正規化（SDK実装差の吸収）
        try:
            # 何をする行か: 代表的な名称から順にフォールバックして呼び出す
            if hasattr(self.trade, "cancel_order"):
                res = self.trade.cancel_order(oid)  # 何をする行か: 新系メソッド
            elif hasattr(self.trade, "cancelOrder"):
                res = self.trade.cancelOrder(oid)   # 何をする行か: キャメルケース別名
            elif hasattr(self.trade, "cancel"):
                try:
                    res = self.trade.cancel(oid)    # 何をする行か: 単一引数版
                except TypeError:
                    res = self.trade.cancel(orderId=oid)  # 何をする行か: キーワード引数版
            elif hasattr(self.trade, "cancel_orders"):
                try:
                    res = self.trade.cancel_orders([oid])  # 何をする行か: 複数ID対応APIに単一で渡す
                except TypeError:
                    res = self.trade.cancel_orders(order_ids=[oid])  # 何をする行か: 別名キーワードに対応
            elif hasattr(self.trade, "account"):
                acc = self.trade.account  # 何をする行か: サブクライアント経由の最終フォールバック
                if hasattr(acc, "cancel_order"):
                    res = acc.cancel_order(oid)
                elif hasattr(acc, "cancelOrder"):
                    res = acc.cancelOrder(oid)
                else:
                    return False
            else:
                return False

            # 何をする行か: 返却をboolへ正規化（dict/None/リスト等のケースに対応）
            if res is None:
                return True
            if isinstance(res, bool):
                return res
            if isinstance(res, dict):
                status = str(res.get("status", "")).lower()
                if status in {"ok", "success", "canceled", "cancelled"}:
                    return True
                data = res.get("data")
                if isinstance(data, dict):
                    if data.get("success") is True:
                        return True
                    if str(data.get("status", "")).lower() in {"ok", "success", "canceled", "cancelled"}:
                        return True
                    sts = data.get("statuses")
                    if isinstance(sts, list) and sts:
                        item = sts[0]
                        if item.get("error"):
                            return False
                        if item.get("success") is True:
                            return True
                        if str(item.get("status", "")).lower() in {"canceled", "cancelled"}:
                            return True
                if isinstance(data, list):
                    return True  # 何をする行か: 成功リストのみ返る実装を成功とみなす
            return True  # 何をする行か: 未知型は成功扱い（上位で実検証される前提）
        except Exception as e:
            msg = str(e)
            # 何をする行か: 認証切れは再ログイン→同処理を1回だけ再試行
            if ("UNAUTHORIZED" in msg or "grpc_status:16" in msg or "UNAUTHENTICATED" in msg) and not _retry:
                if self._relogin():
                    try:
                        return self.cancel_order(order_id, _retry=True)
                    except Exception:
                        return False
                return False
            return False  # 何をする行か: 認証以外の例外は失敗としてFalse


    def _relogin(self) -> bool:
        """何をする関数なのか: UNAUTHORIZED/UNAUTHENTICATED検知時に、SDKの再認証ルートを試してセッションを復旧する"""
        # 何をする行か: SDKが reauth を提供していればトークンリフレッシュを最優先で試す
        if hasattr(self.trade, "reauth"):
            try:
                self.trade.reauth()
                return True
            except Exception:
                pass

        # 何をする行か: ユーザー名/パスワードを属性または環境変数から取得（どれかが定義されていれば使う）
        user = getattr(self, "username", None) or os.getenv("WEBULL_USERNAME") or os.getenv("WEBULL_EMAIL") or os.getenv("WEBULL_PHONE")
        pwd = getattr(self, "password", None) or os.getenv("WEBULL_PASSWORD")
        mfa = os.getenv("WEBULL_MFA")  # 何をする行か: MFAコードがある場合のために読む（無ければNone）

        # 何をする行か: login を提供する実装ではフルログインを試す（MFA対応版/非対応版の両方に配慮）
        if hasattr(self.trade, "login") and user and pwd:
            try:
                if mfa is not None:
                    self.trade.login(user, pwd, mfa)  # 何をする行か: MFAありログイン（SDK側が対応時）
                else:
                    self.trade.login(user, pwd)       # 何をする行か: 通常ログイン
                return True
            except Exception:
                pass

        # 何をする行か: refresh_token のみ提供される実装へのフォールバック
        if hasattr(self.trade, "refresh_token"):
            try:
                self.trade.refresh_token()
                return True
            except Exception:
                pass

        return False  # 何をする行か: どの再認証ルートも成功しなければFalseを返す

    # ポジション & ブラケット ----------------------------------------------
    def get_positions(self) -> list:
        """何をする関数なのか: SDKのバージョン差(メソッド名や返却形式の違い)を吸収して、現在の保有ポジション一覧を安全に返す"""
        try:
            # 何をする行か: 新しいSDKで一般的なメソッド名をまず試す
            if hasattr(self.trade, "get_positions"):
                resp = self.trade.get_positions()  # 何をする行か: 新系メソッドの呼び出し

            # 何をする行か: 旧SDKで使われることがある別名にフォールバック
            elif hasattr(self.trade, "positions"):
                resp = self.trade.positions()  # 何をする行か: 旧系メソッドの呼び出し

            # 何をする行か: サブクライアント(account)配下にある場合の最終フォールバック
            elif hasattr(self.trade, "account") and hasattr(self.trade.account, "get_positions"):
                resp = self.trade.account.get_positions()  # 何をする行か: サブクライアント経由で取得

            else:
                # 何をする行か: どのAPIも見つからない場合は空配列で返す(上位での再ログインや警告判断に委ねる)
                return []

            # 何をする行か: レスポンスが {"data": [...]} 形式でも [... ] 直でも受け取れるように吸収
            data = (resp or {}).get("data", resp)  # 何をする行か: キーが無ければ素のrespを使う
            return data if isinstance(data, list) else []  # 何をする行か: 最終的にlistだけを返す
        
        except Exception as e:
            msg = str(e)
            # 何をする行か: 認証切れの典型ワードを検知したら再ログイン→同じ取得処理を1回だけリトライ
            if "UNAUTHORIZED" in msg or "grpc_status:16" in msg or "UNAUTHENTICATED" in msg:
                if self._relogin():
                    try:
                        # 何をする行か: 再ログイン後に同じ分岐ロジックで取得をやり直す
                        if hasattr(self.trade, "get_positions"):
                            resp = self.trade.get_positions()
                        elif hasattr(self.trade, "positions"):
                            resp = self.trade.positions()
                        elif hasattr(self.trade, "account") and hasattr(self.trade.account, "get_positions"):
                            resp = self.trade.account.get_positions()
                        else:
                            return []
                        data = (resp or {}).get("data", resp)
                        return data if isinstance(data, list) else []
                    except Exception:
                        return []
                return []
            raise  # 何をする行か: 認証以外の想定外エラーは上位へ送出





    def get_bracket(self, symbol: str) -> Optional[Dict[str, Any]]:
        for order in self.get_active_orders():
            if order["symbol"] == symbol and order.get("orderType") in ("TP", "SL"):
                return order
        return None

    def modify_bracket(self, *, order_id: str, stop_loss: float) -> Dict[str, Any]:
        return self.trade.modify_order(order_id=order_id, stop_loss=stop_loss)

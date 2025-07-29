"""
tests/conftest.py
─────────────────
・外部 SDK をスタブ化（ネットワーク遮断）
・pytest 終了時に “残タスク” を強制キャンセル
・websockets の DeprecationWarning 抑制
"""

import sys, types, warnings, asyncio, contextlib

# ── Warning 抑制 ────────────────────────────────
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module=r"websockets\.legacy",
)

# ── Alpaca REST スタブ ──────────────────────────
stub_alp = types.ModuleType("sdk.quotes_alpaca")
stub_alp.get_quote = lambda sym: {"bidPrice": 123, "askPrice": 124}
sys.modules["sdk.quotes_alpaca"] = stub_alp

# Alpaca WS / live モジュールも空スタブ
sys.modules["sdk.alpaca_ws"] = types.ModuleType("sdk.alpaca_ws")
sys.modules["alpaca.data.live"] = types.ModuleType("alpaca.data.live")

# ── Webull SDK スタブ ──────────────────────────
class DummyWebull:
    def get_quote(self, sym, extended=True):
        return {"bidPrice": 111, "askPrice": 112}
    def place_limit_order(self, **kw):
        return {"orderId": "TEST"}
    def attach_bracket(self, **kw): return {}
    def get_active_orders(self):    return []
    def get_positions(self):        return []
    def cancel_order(self, order_id): pass
    @classmethod
    def from_env(cls): return cls()

stub_wb = types.ModuleType("sdk.webull_sdk_wrapper")
stub_wb.WebullClient = DummyWebull
sys.modules["sdk.webull_sdk_wrapper"] = stub_wb

# ── pytest セッション終了フック ─────────────────
def pytest_sessionfinish(session, exitstatus):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return  # ループが存在しない／すでに閉じている
    # 未完了タスクを全キャンセル
    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(t)
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.close()

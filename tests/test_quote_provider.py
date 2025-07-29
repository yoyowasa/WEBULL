"""
make_quote_func() が provider に応じて
・webull_client.get_quote
・alpaca_quote
を正しく呼び分けるかを確認する。
"""

import importlib
import types

# テスト対象モジュール
re = importlib.import_module("scripts.run_entry")


def test_webull_path(monkeypatch):
    """provider='webull' で webull_client.get_quote が呼ばれるか"""
    class DummyWebull:
        def __init__(self):
            self.called = False
        def get_quote(self, sym, extended=True):
            self.called = True
            return {"bidPrice": 111, "askPrice": 112}

    dummy_client = DummyWebull()
    monkeypatch.setattr(re, "webull_client", dummy_client, raising=False)  # ← ダミーを注入

    qf = re.make_quote_func("webull")
    out = qf("AAPL")
    assert dummy_client.called
    assert out["askPrice"] == 112


def test_alpaca_path(monkeypatch):
    """provider='alpaca' で alpaca_quote が呼ばれるか"""
    called = {"flag": False}

    def fake_alpaca(sym):
        called["flag"] = True
        return {"bidPrice": 123, "askPrice": 124}

    monkeypatch.setattr(re, "alpaca_quote", fake_alpaca, raising=False)  # ← スタブを注入

    qf = re.make_quote_func("alpaca")
    out = qf("AAPL")
    assert called["flag"]
    assert out["bidPrice"] == 123

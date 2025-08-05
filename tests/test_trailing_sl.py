"""update_trailing_sl の動作検証
long / short それぞれで TP/2・TP 到達時に SL が正しく更新されるかを確認する。
"""

import types
import pytest

# --------------------------------------------
# 疑似 WebullClient.modify_bracket をモック
# --------------------------------------------
class DummyClient:
    def __init__(self):
        self.calls = []  # [(order_id, stop_loss)] を記録

    def modify_bracket(self, order_id: str, stop_loss: float):
        self.calls.append((order_id, stop_loss))

# fixtures でグローバル webull_client を差し替え
@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    from scripts import run_live
    dummy = DummyClient()
    monkeypatch.setattr(run_live, "webull_client", dummy)
    yield dummy

# --------------------------------------------
# テストケース
# --------------------------------------------
def _make_pos(side: str, entry: float, tp_pct: float = 0.03):
    return {
        "entry": entry,
        "side": side,
        "sl": entry * (0.975 if side == "long" else 1.025),
        "oid": "ABC123",
        "tp_pct": tp_pct,
    }

def test_long_half_tp_updates_to_entry(_patch_client):
    from scripts.run_live import update_trailing_sl

    pos = _make_pos("long", entry=100.0)
    update_trailing_sl(pos, price=101.5, tp_pct=pos["tp_pct"])  # +1.5%
    assert pytest.approx(pos["sl"], rel=1e-3) == 100.0

def test_long_full_tp_updates_to_half_profit(_patch_client):
    from scripts.run_live import update_trailing_sl

    pos = _make_pos("long", entry=100.0)
    update_trailing_sl(pos, price=103.0, tp_pct=pos["tp_pct"])  # +3%
    assert pytest.approx(pos["sl"], rel=1e-3) == 101.5

def test_short_half_tp_updates_to_entry(_patch_client):
    from scripts.run_live import update_trailing_sl

    pos = _make_pos("short", entry=100.0)
    update_trailing_sl(pos, price=98.5, tp_pct=pos["tp_pct"])   # -1.5%
    assert pytest.approx(pos["sl"], rel=1e-3) == 100.0

def test_short_full_tp_updates_to_half_profit(_patch_client):
    from scripts.run_live import update_trailing_sl

    pos = _make_pos("short", entry=100.0)
    update_trailing_sl(pos, price=97.0, tp_pct=pos["tp_pct"])   # -3%
    assert pytest.approx(pos["sl"], rel=1e-3) == 98.5

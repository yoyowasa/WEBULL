# tests/test_entry_calc.py
from scripts.run_entry import calc_shares

def test_calc_shares_risk_cap():
    """リスク上限を超えない株数になるか確認"""
    shares = calc_shares(equity=20_000, price=100, kelly=0.2, max_loss_pct=0.02)
    # 計算例: equity*0.02*0.2 = 80 USD → 80 / 100 = 0.8 株 → 0 株 (floor)
    assert shares == 0

def test_calc_shares_capital_limit():
    """資金5%上限が正しく適用されるか"""
    shares = calc_shares(equity=10_000, price=10, kelly=1.0, max_loss_pct=0.5)
    # 5%枠: 10_000*0.05 / 10 = 50 株
    assert shares == 50

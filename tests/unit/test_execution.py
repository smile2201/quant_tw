"""
tests/unit/test_execution.py
執行模型單元測試 - 驗收 Playbook v1 用
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backtest.execution import Trade, Mode, execute_trade, calc_slippage


def test_ideal_no_slippage():
    """ideal 模式沒有滑價"""
    price = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"ideal")).exec_price
    assert price == 100.0, f"ideal 應無滑價，got {price}"


def test_realistic_buy_slippage():
    """realistic 買進滑價 0.2%"""
    t = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"realistic"))
    expected = 100.0 * 1.002
    assert abs(t.exec_price - expected) < 0.01, f"got {t.exec_price}"


def test_realistic_sell_slippage():
    """realistic 賣出滑價 0.3%"""
    t = execute_trade(Trade("2330","2024-01-02","sell",1000,100.0,"realistic"))
    expected = 100.0 * 0.997
    assert abs(t.exec_price - expected) < 0.01, f"got {t.exec_price}"


def test_pessimistic_buy_slippage():
    """pessimistic 買進滑價 = 0.2% × 1.5 = 0.3%"""
    t = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"pessimistic"))
    expected = 100.0 * (1 + 0.002 * 1.5)
    assert abs(t.exec_price - expected) < 0.01, f"got {t.exec_price}"


def test_limit_hit_realistic():
    """漲跌停時 realistic 模式無法成交"""
    t = execute_trade(
        Trade("2330","2024-01-02","buy",1000,100.0,"realistic"),
        is_limit_hit=True
    )
    assert t.shares == 0, "漲跌停時 shares 應為 0"
    assert t.net_amount == 0.0


def test_limit_hit_ideal_ok():
    """漲跌停時 ideal 模式照常成交"""
    t = execute_trade(
        Trade("2330","2024-01-02","buy",1000,100.0,"ideal"),
        is_limit_hit=True
    )
    assert t.shares == 1000, "ideal 模式不受漲跌停限制"


def test_position_cap():
    """部位超過成交量 0.5% 時只部分成交"""
    # daily_volume=100000，0.5% = 500股；請求1000股應被截為500
    t = execute_trade(
        Trade("2330","2024-01-02","buy",1000,100.0,"realistic"),
        daily_volume=100_000
    )
    assert t.shares == 500, f"應截為500，got {t.shares}"


def test_tax_only_on_sell():
    """證交稅只在賣出時收"""
    buy  = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"realistic"))
    sell = execute_trade(Trade("2330","2024-01-02","sell",1000,100.0,"realistic"))
    assert buy.tax == 0.0, "買進不應收稅"
    assert sell.tax > 0.0, "賣出應收稅"


def test_three_modes_ordering():
    """三模式報酬：ideal > realistic > pessimistic（買進成本）"""
    buy_ideal  = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"ideal"))
    buy_real   = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"realistic"))
    buy_pess   = execute_trade(Trade("2330","2024-01-02","buy",1000,100.0,"pessimistic"))
    # 買進成本：ideal 最低（無滑價），pessimistic 最高
    assert buy_ideal.exec_price <= buy_real.exec_price <= buy_pess.exec_price


if __name__ == "__main__":
    tests = [
        test_ideal_no_slippage,
        test_realistic_buy_slippage,
        test_realistic_sell_slippage,
        test_pessimistic_buy_slippage,
        test_limit_hit_realistic,
        test_limit_hit_ideal_ok,
        test_position_cap,
        test_tax_only_on_sell,
        test_three_modes_ordering,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")

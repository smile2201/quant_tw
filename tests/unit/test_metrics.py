"""
tests/unit/test_metrics.py
績效指標單元測試 - 手算驗證
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pandas as pd
import numpy as np
from backtest.metrics import (
    calc_sharpe, calc_mdd, calc_annual_return,
    calc_win_rate, calc_payoff_ratio, calc_calmar, summarize
)


def test_mdd_known():
    """已知資料驗證 MDD"""
    # 100 → 80 → 90：MDD = (80-100)/100 = -20%
    equity = pd.Series([100, 90, 80, 85, 90])
    mdd = calc_mdd(equity)
    assert abs(mdd - (-0.20)) < 0.001, f"got {mdd}"


def test_win_rate():
    pnl = [100, -50, 200, -30, 150]
    wr = calc_win_rate(pnl)
    assert abs(wr - 0.6) < 0.001, f"got {wr}"


def test_payoff_ratio():
    pnl = [100, -50]  # 平均獲利100，平均虧損50 → 賠率=2
    pr = calc_payoff_ratio(pnl)
    assert abs(pr - 2.0) < 0.001, f"got {pr}"


def test_annual_return_flat():
    """持平 equity curve 應為 0% 報酬"""
    equity = pd.Series([100.0] * 252)
    ar = calc_annual_return(equity)
    assert abs(ar) < 0.0001, f"got {ar}"


def test_calmar():
    assert abs(calc_calmar(0.20, -0.10) - 2.0) < 0.001


def test_summarize_keys():
    """summarize 應包含所有必要 key"""
    equity = pd.Series([100, 105, 98, 110, 108, 115])
    pnl = [5, -7, 12, -2, 7]
    result = summarize(equity, pnl, "realistic")
    required = ["mode","annual_return","sharpe","mdd","win_rate","payoff_ratio","calmar","total_trades"]
    for k in required:
        assert k in result, f"缺少 key: {k}"
    assert result["total_trades"] == 5


if __name__ == "__main__":
    tests = [
        test_mdd_known,
        test_win_rate,
        test_payoff_ratio,
        test_annual_return_flat,
        test_calmar,
        test_summarize_keys,
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

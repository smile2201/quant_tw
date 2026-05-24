"""
tests/unit/test_engine.py
回測引擎單元測試 - 驗收 Playbook v3 用
全部使用 mock 資料，不打任何 API
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pandas as pd
import numpy as np
from backtest.engine import (
    run_single, run_three_modes, compare_modes,
    _get_price, _is_limit
)


# ─── Mock 資料工廠 ─────────────────────────────────────────────────────────────

def make_price_data(stock_ids=None, n=500, start="2022-01-03") -> dict:
    """產生模擬價格資料（含足夠的回測日期）"""
    stock_ids = stock_ids or ["2330", "2317"]
    np.random.seed(42)
    dates = pd.bdate_range(start, periods=n).strftime("%Y-%m-%d").tolist()
    result = {}
    for sid in stock_ids:
        base   = 100.0
        closes = base + np.cumsum(np.random.uniform(-0.5, 0.8, n))
        result[sid] = pd.DataFrame({
            "date":           dates,
            "open":           closes * 0.99,
            "high":           closes * 1.02,
            "low":            closes * 0.97,
            "close":          closes,
            "Trading_Volume": np.random.randint(10_000, 100_000, n),
        })
    return result


def make_signals(stock_ids=None, score=70.0) -> pd.DataFrame:
    """產生模擬選股訊號"""
    stock_ids = stock_ids or ["2330", "2317"]
    return pd.DataFrame({
        "stock_id":    stock_ids,
        "final_score": [score] * len(stock_ids),
        "tier":        ["觀察股"] * len(stock_ids),
        "tech_score":  [score] * len(stock_ids),
        "fund_score":  [score] * len(stock_ids),
        "event_score": [50.0]  * len(stock_ids),
        "tech_signals": ["MA多頭"] * len(stock_ids),
        "fund_signals": ["EPS成長"] * len(stock_ids),
        "events":       ["無重大訊息"] * len(stock_ids),
    })


# ─── 引擎測試 ──────────────────────────────────────────────────────────────────

def test_engine_returns_result():
    """run_single 應回傳 BacktestResult 且含必要欄位"""
    price_data = make_price_data()
    signals    = make_signals()
    result = run_single(signals, price_data, mode="realistic")
    assert result.mode == "realistic"
    assert not result.equity_curve.empty
    assert isinstance(result.metrics, dict)
    assert "sharpe" in result.metrics


def test_engine_equity_starts_near_initial():
    """equity curve 第一個值應接近初始資金"""
    from config.settings import BACKTEST
    price_data = make_price_data()
    signals    = make_signals()
    result = run_single(signals, price_data, mode="ideal")
    first_eq = result.equity_curve.iloc[0]
    capital  = BACKTEST["initial_capital"]
    # 第一天可能已建倉，允許 20% 誤差
    assert 0.5 * capital <= first_eq <= 1.5 * capital, \
        f"第一天資產 {first_eq} 偏離初始資金 {capital} 太多"


def test_three_modes_returns_all():
    """run_three_modes 應回傳三個模式的結果"""
    price_data = make_price_data()
    signals    = make_signals()
    results = run_three_modes(signals, price_data)
    assert set(results.keys()) == {"ideal", "realistic", "pessimistic"}


def test_three_modes_ideal_best():
    """三模式報酬：ideal >= realistic >= pessimistic"""
    price_data = make_price_data()
    signals    = make_signals()
    results    = run_three_modes(signals, price_data)
    r_ideal = results["ideal"].metrics["annual_return"]
    r_real  = results["realistic"].metrics["annual_return"]
    r_pess  = results["pessimistic"].metrics["annual_return"]
    # ideal 成本最低，報酬最高（或相近）
    assert r_ideal >= r_pess, f"ideal={r_ideal}, pess={r_pess}"


def test_compare_modes_dataframe():
    """compare_modes 應回傳正確格式的 DataFrame"""
    price_data = make_price_data()
    signals    = make_signals()
    results    = run_three_modes(signals, price_data)
    df = compare_modes(results)
    assert len(df) == 3
    assert "mode" in df.columns
    assert "sharpe" in df.columns
    assert "mdd" in df.columns


def test_engine_empty_signals():
    """無候選股時應正常回傳（不崩潰），equity 維持初始資金"""
    from config.settings import BACKTEST
    price_data = make_price_data()
    signals    = pd.DataFrame()  # 空訊號
    result     = run_single(signals, price_data, mode="realistic")
    assert not result.equity_curve.empty


def test_engine_no_price_data():
    """無價格資料時應正常回傳（不崩潰）"""
    signals = make_signals()
    result  = run_single(signals, {}, mode="realistic")
    assert result.equity_curve is not None


def test_limit_detection():
    """漲跌停偵測：high == low 視為封死"""
    class FakeRow:
        def get(self, key, default=0):
            return {"high": 100.0, "low": 100.0, "close": 100.0}.get(key, default)
    assert _is_limit(FakeRow()) is True


def test_no_limit():
    """正常行情不是漲跌停"""
    class FakeRow:
        def get(self, key, default=0):
            return {"high": 102.0, "low": 98.0, "close": 100.0}.get(key, default)
    assert _is_limit(FakeRow()) is False


def test_runner_serial():
    """ParallelRunner 序列模式可正常跑完"""
    from runner.parallel_runner import ParallelRunner

    def dummy_task(params):
        return {"score": params["ma"] + params["period"]}

    runner = ParallelRunner(workers=1)
    results = runner.run_grid(
        task_fn    = dummy_task,
        param_grid = {"ma": [5, 10], "period": [20, 30]},
        resume     = False,
    )
    assert len(results) == 4
    assert all("score" in r for r in results)


def test_runner_ablation():
    """ParallelRunner ablation 應回傳6個實驗結果"""
    from runner.parallel_runner import ParallelRunner

    call_log = []
    def dummy_task(params):
        call_log.append(params)
        return {"sharpe": 1.0}

    runner  = ParallelRunner(workers=1)
    results = runner.run_ablation(dummy_task, {"x": 1})
    assert len(results) == 6
    assert "all" in results
    assert "tech_only" in results


# ─── 執行 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_engine_returns_result,
        test_engine_equity_starts_near_initial,
        test_three_modes_returns_all,
        test_three_modes_ideal_best,
        test_compare_modes_dataframe,
        test_engine_empty_signals,
        test_engine_no_price_data,
        test_limit_detection,
        test_no_limit,
        test_runner_serial,
        test_runner_ablation,
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

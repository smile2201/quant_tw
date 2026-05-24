"""
backtest/metrics.py
績效指標計算：Sharpe、MDD、勝率、賠率、卡爾瑪
"""
import numpy as np
import pandas as pd
from config.settings import BACKTEST


def calc_sharpe(returns: pd.Series, freq: int = 252) -> float:
    """年化 Sharpe Ratio"""
    if returns.std() == 0:
        return 0.0
    excess = returns - BACKTEST["risk_free_rate"] / freq
    return float(excess.mean() / returns.std() * np.sqrt(freq))


def calc_mdd(equity_curve: pd.Series) -> float:
    """最大回撤（%）"""
    roll_max = equity_curve.cummax()
    drawdown = (equity_curve - roll_max) / roll_max
    return float(drawdown.min())


def calc_annual_return(equity_curve: pd.Series, freq: int = 252) -> float:
    """年化報酬率（幾何平均）"""
    n_days = len(equity_curve)
    if n_days < 2:
        return 0.0
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    return float((1 + total_return) ** (freq / n_days) - 1)


def calc_win_rate(pnl_list: list) -> float:
    """勝率"""
    if not pnl_list:
        return 0.0
    wins = sum(1 for p in pnl_list if p > 0)
    return wins / len(pnl_list)


def calc_payoff_ratio(pnl_list: list) -> float:
    """賠率 = 平均獲利 / 平均虧損"""
    wins   = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]
    if not wins or not losses:
        return 0.0
    return float(np.mean(wins) / abs(np.mean(losses)))


def calc_calmar(annual_return: float, mdd: float) -> float:
    """卡爾瑪比率 = 年化報酬 / MDD"""
    if mdd == 0:
        return 0.0
    return float(annual_return / abs(mdd))


def summarize(equity_curve: pd.Series, pnl_list: list, mode: str) -> dict:
    """
    一次計算所有指標

    Returns:
        dict with keys: mode, annual_return, sharpe, mdd, win_rate,
                        payoff_ratio, calmar, total_trades
    """
    returns = equity_curve.pct_change().dropna()
    ann_ret = calc_annual_return(equity_curve)
    mdd     = calc_mdd(equity_curve)

    return {
        "mode":          mode,
        "annual_return": round(ann_ret * 100, 2),   # %
        "sharpe":        round(calc_sharpe(returns), 3),
        "mdd":           round(mdd * 100, 2),        # %
        "win_rate":      round(calc_win_rate(pnl_list) * 100, 2),   # %
        "payoff_ratio":  round(calc_payoff_ratio(pnl_list), 3),
        "calmar":        round(calc_calmar(ann_ret, mdd), 3),
        "total_trades":  len(pnl_list),
    }

"""
backtest/engine.py
回測引擎主體：三模式並行輸出
輸入：策略訊號 + 價格資料
輸出：equity curve + 交易記錄 + 績效指標（三模式）
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from backtest.execution import Trade, Mode, execute_trade
from backtest.metrics import summarize
from config.settings import BACKTEST, EXECUTION, SCREENER


@dataclass
class Position:
    stock_id:   str
    shares:     int
    avg_cost:   float   # 平均成本（含手續費）
    entry_date: str


@dataclass
class BacktestResult:
    mode:         str
    equity_curve: pd.Series
    trades:       list
    pnl_list:     list
    metrics:      dict


def run_single(
    signals:     pd.DataFrame,
    price_data:  dict,
    mode:        str = "realistic",
    initial_capital: Optional[float] = None,
) -> BacktestResult:
    """
    單一模式回測

    Args:
        signals:    hybrid_screener.run() 的輸出，含 stock_id + final_score
        price_data: {stock_id: price_adj_df}，需含 date/close/high/low/Trading_Volume
        mode:       "ideal" | "realistic" | "pessimistic"
        initial_capital: 初始資金（預設從 config 讀）

    Returns:
        BacktestResult
    """
    capital  = initial_capital or BACKTEST["initial_capital"]
    max_pos  = BACKTEST["max_positions"]
    pos_size = BACKTEST["position_size"]

    # 整理所有交易日期
    all_dates = sorted(set(
        date
        for df in price_data.values()
        if not df.empty and "date" in df.columns
        for date in df["date"].tolist()
    ))
    if not all_dates:
        return BacktestResult(mode=mode,
                              equity_curve=pd.Series([capital]),
                              trades=[], pnl_list=[],
                              metrics=summarize(pd.Series([capital]), [], mode))

    # 過濾回測區間
    start = BACKTEST["start_date"]
    end   = BACKTEST["end_date"]
    all_dates = [d for d in all_dates if start <= d <= end]

    # 建立每股票的價格查詢表 {stock_id: {date: row}}
    price_lookup = {}
    for sid, df in price_data.items():
        if df.empty or "date" not in df.columns:
            continue
        df = df.copy().sort_values("date")
        # 相容 FinMind price dataset（max/min）與 price_adj（high/low）
        if "high" not in df.columns and "max" in df.columns:
            df["high"] = df["max"]
        if "low" not in df.columns and "min" in df.columns:
            df["low"] = df["min"]
        price_lookup[sid] = df.set_index("date")

    # 候選股（依評分排序，門檻從 settings 讀取）
    threshold  = SCREENER.get("threshold_watch", 60)
    candidates = (signals[signals["final_score"] >= threshold]
                  .sort_values("final_score", ascending=False)
                  ["stock_id"].tolist()) if not signals.empty else []

    cash       = float(capital)
    positions  = {}     # {stock_id: Position}
    equity_log = []
    all_trades = []
    pnl_list   = []

    for date in all_dates:

        # ── 賣出邏輯：持倉超過 20 個交易日，或評分掉出候選 ───────────────────
        to_sell = []
        for sid, pos in positions.items():
            days_held = _days_between(pos.entry_date, date, all_dates)
            still_candidate = sid in candidates[:max_pos]
            if days_held >= 20 or not still_candidate:
                to_sell.append(sid)

        for sid in to_sell:
            pos   = positions.pop(sid)
            price_row = _get_price(price_lookup, sid, date)
            if price_row is None:
                continue

            close        = float(price_row.get("close", price_row.get("Close", 0)))
            daily_vol    = int(price_row.get("Trading_Volume", 0))
            is_limit_hit = _is_limit(price_row)

            t = Trade(sid, date, "sell", pos.shares, close, mode)
            t = execute_trade(t, daily_volume=daily_vol, is_limit_hit=is_limit_hit)

            if t.shares > 0:
                cash += t.net_amount
                pnl   = t.net_amount - (pos.avg_cost * t.shares)
                pnl_list.append(pnl)
                all_trades.append(t)

        # ── 買進邏輯：補足持倉到 max_pos ─────────────────────────────────────
        slots = max_pos - len(positions)
        for sid in candidates:
            if slots <= 0:
                break
            if sid in positions:
                continue

            price_row = _get_price(price_lookup, sid, date)
            if price_row is None:
                continue

            close        = float(price_row.get("close", price_row.get("Close", 0)))
            daily_vol    = int(price_row.get("Trading_Volume", 0))
            is_limit_hit = _is_limit(price_row)

            target_value = capital * pos_size
            shares       = int(target_value / close / 1000) * 1000  # 整張
            if shares <= 0:
                continue

            t = Trade(sid, date, "buy", shares, close, mode)
            t = execute_trade(t, daily_volume=daily_vol, is_limit_hit=is_limit_hit)

            if t.shares > 0 and cash + t.net_amount >= 0:
                cash += t.net_amount   # net_amount 是負值（買進）
                positions[sid] = Position(
                    stock_id   = sid,
                    shares     = t.shares,
                    avg_cost   = abs(t.net_amount) / t.shares,
                    entry_date = date,
                )
                all_trades.append(t)
                slots -= 1

        # ── 計算當日資產 ──────────────────────────────────────────────────────
        pos_value = 0.0
        for sid, pos in positions.items():
            price_row = _get_price(price_lookup, sid, date)
            if price_row is not None:
                close = float(price_row.get("close", price_row.get("Close", 0)))
                pos_value += close * pos.shares

        equity_log.append({"date": date, "equity": cash + pos_value})

    equity_df    = pd.DataFrame(equity_log).set_index("date")
    equity_curve = equity_df["equity"] if not equity_df.empty else pd.Series([capital])

    return BacktestResult(
        mode         = mode,
        equity_curve = equity_curve,
        trades       = all_trades,
        pnl_list     = pnl_list,
        metrics      = summarize(equity_curve, pnl_list, mode),
    )


def run_three_modes(
    signals:    pd.DataFrame,
    price_data: dict,
    initial_capital: Optional[float] = None,
) -> dict:
    """
    三模式並行回測，回傳 dict {mode: BacktestResult}

    Args:
        signals:    hybrid_screener 輸出
        price_data: 價格資料
    """
    results = {}
    for mode in ["ideal", "realistic", "pessimistic"]:
        print(f"  [backtest] 跑 {mode} 模式...")
        results[mode] = run_single(signals, price_data, mode, initial_capital)
    return results


def compare_modes(results: dict) -> pd.DataFrame:
    """
    三模式指標並排比較

    Returns:
        DataFrame，每行一個模式，每欄一個指標
    """
    rows = [r.metrics for r in results.values()]
    df   = pd.DataFrame(rows)
    col_order = ["mode", "annual_return", "sharpe", "mdd",
                 "win_rate", "payoff_ratio", "calmar", "total_trades"]
    return df[[c for c in col_order if c in df.columns]]


# ─── 內部工具函式 ──────────────────────────────────────────────────────────────

def _get_price(price_lookup: dict, stock_id: str, date: str):
    """取得特定股票特定日期的價格資料，找不到回傳 None"""
    if stock_id not in price_lookup:
        return None
    idx = price_lookup[stock_id]
    if date in idx.index:
        return idx.loc[date]
    return None


def _is_limit(price_row) -> bool:
    """判斷是否漲跌停（high == low 視為封死）"""
    if price_row is None:
        return False
    high  = float(price_row.get("high",  price_row.get("High",  0)))
    low   = float(price_row.get("low",   price_row.get("Low",   0)))
    close = float(price_row.get("close", price_row.get("Close", 0)))
    if close <= 0:
        return False
    # 漲停：high == low（封死）或漲幅接近10%
    return high == low


def _days_between(entry_date: str, current_date: str, all_dates: list) -> int:
    """計算兩個交易日之間的交易日數"""
    try:
        i1 = all_dates.index(entry_date)
        i2 = all_dates.index(current_date)
        return i2 - i1
    except ValueError:
        return 0


# ─── 動態訊號版本 ──────────────────────────────────────────────────────────────

def run_single_dynamic(
    price_data:  dict,
    fund_data:   dict,
    news_df,
    mode:        str = "realistic",
    initial_capital: Optional[float] = None,
    rescore_every:   int = 5,
) -> BacktestResult:
    """
    動態訊號回測：每 rescore_every 個交易日用當天為止的資料重新評分。

    Args:
        price_data:    {stock_id: price_df}
        fund_data:     {stock_id: {"financial":df, "dividend":df, "revenue":df}}
        news_df:       TWSE 重大訊息（事件面在動態模式用中性分，不使用此參數）
        mode:          "ideal" | "realistic" | "pessimistic"
        initial_capital: 初始資金
        rescore_every: 每幾個交易日重新評分（預設 5 = 每週）
    """
    from strategy import hybrid_screener

    capital  = initial_capital or BACKTEST["initial_capital"]
    max_pos  = BACKTEST["max_positions"]
    pos_size = BACKTEST["position_size"]

    # 整理交易日期並過濾回測區間
    all_dates = sorted(set(
        date
        for df in price_data.values()
        if not df.empty and "date" in df.columns
        for date in df["date"].tolist()
    ))
    start = BACKTEST["start_date"]
    end   = BACKTEST["end_date"]
    all_dates = [d for d in all_dates if start <= d <= end]
    if not all_dates:
        return BacktestResult(mode=mode, equity_curve=pd.Series([capital]),
                              trades=[], pnl_list=[],
                              metrics=summarize(pd.Series([capital]), [], mode))

    # 建立價格查詢表
    price_lookup = {}
    for sid, df in price_data.items():
        if df.empty or "date" not in df.columns:
            continue
        df = df.copy().sort_values("date")
        if "high" not in df.columns and "max" in df.columns:
            df["high"] = df["max"]
        if "low" not in df.columns and "min" in df.columns:
            df["low"] = df["min"]
        price_lookup[sid] = df.set_index("date")

    threshold  = SCREENER.get("threshold_watch", 60)
    candidates = []   # 初始空，第一天就會評分

    cash       = float(capital)
    positions  = {}
    equity_log = []
    all_trades = []
    pnl_list   = []

    for i, date in enumerate(all_dates):

        # ── 每 rescore_every 天重新評分 ────────────────────────────────────────
        if i % rescore_every == 0:
            signals    = hybrid_screener.run(price_data, fund_data, news_df,
                                             cutoff_date=date)
            candidates = (signals[signals["final_score"] >= threshold]
                          .sort_values("final_score", ascending=False)
                          ["stock_id"].tolist()) if not signals.empty else []

        # ── 賣出邏輯 ──────────────────────────────────────────────────────────
        to_sell = []
        for sid, pos in positions.items():
            days_held      = _days_between(pos.entry_date, date, all_dates)
            still_candidate = sid in candidates[:max_pos]
            if days_held >= 20 or not still_candidate:
                to_sell.append(sid)

        for sid in to_sell:
            pos       = positions.pop(sid)
            price_row = _get_price(price_lookup, sid, date)
            if price_row is None:
                continue
            close        = float(price_row.get("close", price_row.get("Close", 0)))
            daily_vol    = int(price_row.get("Trading_Volume", 0))
            is_limit_hit = _is_limit(price_row)
            t = Trade(sid, date, "sell", pos.shares, close, mode)
            t = execute_trade(t, daily_volume=daily_vol, is_limit_hit=is_limit_hit)
            if t.shares > 0:
                cash += t.net_amount
                pnl_list.append(t.net_amount - pos.avg_cost * t.shares)
                all_trades.append(t)

        # ── 買進邏輯 ──────────────────────────────────────────────────────────
        slots = max_pos - len(positions)
        for sid in candidates:
            if slots <= 0:
                break
            if sid in positions:
                continue
            price_row = _get_price(price_lookup, sid, date)
            if price_row is None:
                continue
            close        = float(price_row.get("close", price_row.get("Close", 0)))
            daily_vol    = int(price_row.get("Trading_Volume", 0))
            is_limit_hit = _is_limit(price_row)
            shares = int(capital * pos_size / close / 1000) * 1000
            if shares <= 0:
                continue
            t = Trade(sid, date, "buy", shares, close, mode)
            t = execute_trade(t, daily_volume=daily_vol, is_limit_hit=is_limit_hit)
            if t.shares > 0 and cash + t.net_amount >= 0:
                cash += t.net_amount
                positions[sid] = Position(
                    stock_id   = sid,
                    shares     = t.shares,
                    avg_cost   = abs(t.net_amount) / t.shares,
                    entry_date = date,
                )
                all_trades.append(t)
                slots -= 1

        # ── 當日資產 ──────────────────────────────────────────────────────────
        pos_value = sum(
            float(_get_price(price_lookup, sid, date).get("close", 0)) * pos.shares
            for sid, pos in positions.items()
            if _get_price(price_lookup, sid, date) is not None
        )
        equity_log.append({"date": date, "equity": cash + pos_value})

    equity_df    = pd.DataFrame(equity_log).set_index("date")
    equity_curve = equity_df["equity"] if not equity_df.empty else pd.Series([capital])

    return BacktestResult(
        mode         = mode,
        equity_curve = equity_curve,
        trades       = all_trades,
        pnl_list     = pnl_list,
        metrics      = summarize(equity_curve, pnl_list, mode),
    )


def run_three_modes_dynamic(
    price_data:  dict,
    fund_data:   dict,
    news_df,
    initial_capital: Optional[float] = None,
    rescore_every:   int = 5,
) -> dict:
    """動態訊號三模式回測"""
    results = {}
    for mode in ["ideal", "realistic", "pessimistic"]:
        print(f"  [dynamic backtest] 跑 {mode} 模式（每 {rescore_every} 日重新評分）...")
        results[mode] = run_single_dynamic(
            price_data, fund_data, news_df, mode, initial_capital, rescore_every
        )
    return results

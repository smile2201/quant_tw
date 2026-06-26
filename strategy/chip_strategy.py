"""
strategy/chip_strategy.py
籌碼面策略：三大法人（外資、投信、自營商）買賣超分析
輸入：FinMind TaiwanStockInstitutionalInvestorsBuySell DataFrame
輸出：含籌碼評分的 DataFrame（0~100，50 = 中性）

評分邏輯：
  外資（最重要）：5日累計買超 +20，連買3天以上 +10，賣超 -20
  投信（中等）：  5日累計買超 +15，賣超 -10
  自營商（輔助）：3日累計買超  +5，賣超  -5
  起始分 50 → 最高 100，最低 0
"""
from typing import Optional
import pandas as pd
import numpy as np
from config.settings import SCREENER


INVESTOR_NAMES = {
    "外資": ["外資及陸資", "外資", "Foreign_Investor"],
    "投信": ["投信", "Investment_Trust"],
    "自營商": ["自營商", "Dealer"],
}


def _find_investor_name(df: pd.DataFrame, keys: list) -> Optional[str]:
    """找到 df 裡實際用的法人名稱欄位值"""
    if "name" not in df.columns:
        return None
    actual = df["name"].unique().tolist()
    for k in keys:
        if k in actual:
            return k
    return None


def score_institutional(inst_df: pd.DataFrame, stock_id: str,
                        cutoff_date: str = None) -> tuple[float, list]:
    """
    計算單一股票的籌碼評分

    Args:
        inst_df:     TaiwanStockInstitutionalInvestorsBuySell DataFrame
        stock_id:    股票代號（用於 debug）
        cutoff_date: 只用 <= 此日期的資料

    Returns:
        (score 0~100, signals list)
    """
    if inst_df.empty:
        return 50.0, []

    df = inst_df.copy()
    if "date" in df.columns:
        df = df.sort_values("date")
        if cutoff_date:
            df = df[df["date"] <= cutoff_date]

    if df.empty:
        return 50.0, []

    # 計算 diff（買賣超股數）
    if "diff" not in df.columns:
        buy_col  = next((c for c in df.columns if c.lower() in ("buy",  "buy_volume")),  None)
        sell_col = next((c for c in df.columns if c.lower() in ("sell", "sell_volume")), None)
        if buy_col and sell_col:
            df["diff"] = pd.to_numeric(df[buy_col], errors="coerce") - \
                         pd.to_numeric(df[sell_col], errors="coerce")
        else:
            return 50.0, []
    else:
        df["diff"] = pd.to_numeric(df["diff"], errors="coerce")

    score   = 50.0
    signals = []
    n       = SCREENER["chip_lookback_days"]
    streak  = SCREENER["chip_streak_min"]

    def _investor_score(investor_keys: list, w_buy: float, w_buy_streak: float,
                        w_sell: float, label: str):
        nonlocal score
        name = _find_investor_name(df, investor_keys)
        if name is None:
            return

        sub  = df[df["name"] == name].tail(n)
        if sub.empty:
            return

        net_5d    = sub["diff"].sum()
        consec    = _consecutive_days(sub["diff"])

        if net_5d > 0:
            score += w_buy
            if consec >= streak:
                score += w_buy_streak
                signals.append(f"{label}連買{consec}日")
            else:
                signals.append(f"{label}買超")
        elif net_5d < 0:
            score += w_sell   # w_sell 是負值
            signals.append(f"{label}賣超")

    _investor_score(INVESTOR_NAMES["外資"],  w_buy=20, w_buy_streak=10, w_sell=-20, label="外資")
    _investor_score(INVESTOR_NAMES["投信"],  w_buy=15, w_buy_streak=5,  w_sell=-10, label="投信")
    _investor_score(INVESTOR_NAMES["自營商"], w_buy=5,  w_buy_streak=0,  w_sell=-5,  label="自營")

    return float(max(0.0, min(100.0, score))), signals


def _consecutive_days(series: pd.Series) -> int:
    """計算末尾連續正值（連買）天數"""
    vals = series.dropna().tolist()
    count = 0
    for v in reversed(vals):
        if v > 0:
            count += 1
        else:
            break
    return count


def run(inst_data: dict, stock_ids: list, cutoff_date: str = None) -> pd.DataFrame:
    """
    批次計算所有股票的籌碼評分

    Args:
        inst_data:   {stock_id: DataFrame}（TaiwanStockInstitutionalInvestorsBuySell）
        stock_ids:   要評分的股票代號 list
        cutoff_date: 只用 <= 此日期的資料

    Returns:
        DataFrame，columns: [stock_id, chip_score, chip_signals]
    """
    records = []
    for sid in stock_ids:
        df    = inst_data.get(sid, pd.DataFrame())
        score, signals = score_institutional(df, sid, cutoff_date)
        records.append({
            "stock_id":     sid,
            "chip_score":   round(score, 1),
            "chip_signals": " | ".join(signals) if signals else "",
        })

    return pd.DataFrame(records).sort_values("chip_score", ascending=False).reset_index(drop=True)

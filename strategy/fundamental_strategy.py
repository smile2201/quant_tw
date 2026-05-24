"""
strategy/fundamental_strategy.py
基本面策略：EPS成長、股利殖利率、月營收動能、本益比
輸入：FinMind 財務資料 DataFrame
輸出：含基本面評分的 DataFrame（0~100）
"""
import pandas as pd
import numpy as np
from config.settings import SCREENER


def score_eps(financial_df: pd.DataFrame) -> float:
    """
    EPS 成長評分（0~40）
    - 近4季 EPS 年增率 > 15%：+25
    - 連續4季獲利（無虧損）：+15
    """
    if financial_df.empty:
        return 0.0

    df = financial_df.copy()
    eps_col = next((c for c in df.columns if "EPS" in c or "eps" in c.lower()), None)
    if eps_col is None:
        return 0.0

    df = df.sort_values("date") if "date" in df.columns else df
    df[eps_col] = pd.to_numeric(df[eps_col], errors="coerce")

    recent = df[eps_col].dropna().tail(8)
    if len(recent) < 4:
        return 0.0

    score = 0.0
    current_4 = recent.tail(4)
    prior_4   = recent.head(4)

    # 近4季全數獲利（無任何虧損季）
    no_loss = (current_4 > 0).all()
    if no_loss:
        score += 15

    # 年增率（只有無虧損才加分，避免虧轉小虧被誤判為成長）
    if no_loss and len(prior_4) == 4 and prior_4.sum() != 0:
        yoy = (current_4.sum() - prior_4.sum()) / abs(prior_4.sum())
        if yoy >= SCREENER["eps_growth_min"]:
            score += 25
        elif yoy > 0:
            score += 10

    return float(min(40.0, score))


def score_dividend(dividend_df: pd.DataFrame) -> float:
    """
    股利評分（0~30）
    - 近3年持續配息：+15
    - 殖利率 > 4%：+15
    """
    if dividend_df.empty:
        return 0.0

    df = dividend_df.copy()

    # 找現金股利欄位
    cash_col = next((c for c in df.columns
                     if "現金" in c or "cash" in c.lower() or "CashEarningsDistribution" in c), None)
    yield_col = next((c for c in df.columns
                      if "殖利" in c or "yield" in c.lower()), None)

    score = 0.0

    # 持續配息（近3年）
    if cash_col:
        df[cash_col] = pd.to_numeric(df[cash_col], errors="coerce")
        recent = df[cash_col].dropna().tail(3)
        if len(recent) >= 3 and (recent > 0).all():
            score += 15
        elif len(recent) >= 2 and (recent > 0).all():
            score += 8

    # 殖利率
    if yield_col:
        df[yield_col] = pd.to_numeric(df[yield_col], errors="coerce")
        last_yield = df[yield_col].dropna().iloc[-1] if not df[yield_col].dropna().empty else 0
        # FinMind 殖利率可能是百分比或小數，統一處理
        if last_yield > 1:
            last_yield = last_yield / 100
        if last_yield >= SCREENER["dividend_yield_min"]:
            score += 15
        elif last_yield >= 0.02:
            score += 7

    return float(min(30.0, score))


def score_revenue(revenue_df: pd.DataFrame) -> float:
    """
    月營收動能評分（0~30）
    - 連3個月月增率 > 0：+15
    - 年增率 > 10%：+15
    """
    if revenue_df.empty:
        return 0.0

    df = revenue_df.copy()
    rev_col = next((c for c in df.columns
                    if "revenue" in c.lower() or "營收" in c or "Revenue" in c), None)
    if rev_col is None:
        return 0.0

    df = df.sort_values("date") if "date" in df.columns else df
    df[rev_col] = pd.to_numeric(df[rev_col], errors="coerce")
    recent = df[rev_col].dropna().tail(14)

    if len(recent) < 4:
        return 0.0

    score = 0.0
    last3 = recent.tail(3)
    mom   = last3.pct_change().dropna()

    # 連3個月月增率 > 0
    if len(mom) >= 2 and (mom > 0).all():
        score += 15
    elif len(mom) >= 1 and mom.iloc[-1] > 0:
        score += 7

    # 年增率
    if len(recent) >= 13:
        yoy = (recent.iloc[-1] - recent.iloc[-13]) / abs(recent.iloc[-13]) \
              if recent.iloc[-13] != 0 else 0
        if yoy >= SCREENER["revenue_growth_min"]:
            score += 15
        elif yoy > 0:
            score += 7

    return float(min(30.0, score))


def score_stock(financial_df: pd.DataFrame,
                dividend_df: pd.DataFrame,
                revenue_df: pd.DataFrame) -> float:
    """
    計算單一股票的基本面評分（0~100）
    EPS(40) + 股利(30) + 月營收(30)
    """
    return float(min(100.0,
        score_eps(financial_df) +
        score_dividend(dividend_df) +
        score_revenue(revenue_df)
    ))


def run(data: dict, cutoff_date: str = None) -> pd.DataFrame:
    """
    批次計算所有股票的基本面評分

    Args:
        data: {
            stock_id: {
                "financial": DataFrame,
                "dividend":  DataFrame,
                "revenue":   DataFrame,
            }
        }
        cutoff_date: 若指定，只用 <= 此日期的資料（動態回測用）

    Returns:
        DataFrame，columns: [stock_id, fund_score, signals]
    """
    records = []
    for sid, d in data.items():
        def _slice(df):
            if cutoff_date and not df.empty and "date" in df.columns:
                return df[df["date"] <= cutoff_date]
            return df

        fin = _slice(d.get("financial", pd.DataFrame()))
        div = _slice(d.get("dividend",  pd.DataFrame()))
        rev = _slice(d.get("revenue",   pd.DataFrame()))

        eps_s  = score_eps(fin)
        div_s  = score_dividend(div)
        rev_s  = score_revenue(rev)
        total  = min(100.0, eps_s + div_s + rev_s)

        signals = []
        if eps_s >= 25:
            signals.append("EPS成長")
        if div_s >= 15:
            signals.append("持續配息")
        if rev_s >= 15:
            signals.append("營收動能")

        records.append({
            "stock_id":   sid,
            "fund_score": round(total, 1),
            "eps_score":  round(eps_s, 1),
            "div_score":  round(div_s, 1),
            "rev_score":  round(rev_s, 1),
            "signals":    " | ".join(signals),
        })

    return pd.DataFrame(records).sort_values("fund_score", ascending=False).reset_index(drop=True)

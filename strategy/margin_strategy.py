"""
strategy/margin_strategy.py
融資融券（信用交易）策略
資料來源：FinMind TaiwanStockMarginPurchaseShortSale

評分邏輯（0~100，起始 50）：
  券資比 < 0.10  : +15（空頭少，多方未被做空）
  券資比 > 0.25  : -10（空頭壓力大）
  5日融資增幅 5~20% : +10（健康追買）
  5日融資增幅 > 30% : -5（追高過熱，強制斷頭風險）
  5日融資增幅 < -10% : -15（資金撤退）
  融資使用率 < 25%   : +5（籌碼乾淨）
  融資使用率 > 60%   : -10（融資壓力大）
"""
import pandas as pd
from config.settings import SCREENER


def _col(df: pd.DataFrame, candidates: list):
    """不分大小寫找欄位名稱"""
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def score_margin(margin_df: pd.DataFrame, cutoff_date: str = None) -> tuple[float, list]:
    """
    計算單一股票融資融券評分

    Returns:
        (score 0~100, signals list)
    """
    if margin_df.empty:
        return 50.0, []

    df = margin_df.copy()
    date_col = _col(df, ["date"])
    if date_col:
        df = df.sort_values(date_col)
        if cutoff_date:
            df = df[df[date_col] <= cutoff_date]

    if df.empty:
        return 50.0, []

    mp_today_col = _col(df, ["MarginPurchaseToday",  "margin_purchase_today"])
    mp_limit_col = _col(df, ["MarginPurchaseLimit",  "margin_purchase_limit"])
    ss_today_col = _col(df, ["ShortSaleToday",       "short_sale_today"])

    if not mp_today_col or not ss_today_col:
        return 50.0, []

    latest   = df.iloc[-1]
    mp_today = pd.to_numeric(latest.get(mp_today_col, 0), errors="coerce") or 0
    ss_today = pd.to_numeric(latest.get(ss_today_col, 0), errors="coerce") or 0
    mp_limit = pd.to_numeric(latest.get(mp_limit_col, 1) if mp_limit_col else 1,
                              errors="coerce") or 1

    score   = 50.0
    signals = []
    cfg     = SCREENER

    # ── 券資比 ──────────────────────────────────────────────────────────
    if mp_today > 0:
        ratio = ss_today / mp_today
        if ratio < cfg["margin_short_ratio_low"]:
            score += 15
            signals.append(f"券資比{ratio:.2f}↓低")
        elif ratio > cfg["margin_short_ratio_high"]:
            score -= 10
            signals.append(f"券資比{ratio:.2f}↑高")
        else:
            signals.append(f"券資比{ratio:.2f}")

    # ── 5日融資增幅 ──────────────────────────────────────────────────────
    if len(df) >= 6 and mp_today_col in df.columns:
        mp_5d_ago = pd.to_numeric(df[mp_today_col].iloc[-6], errors="coerce") or 0
        if mp_5d_ago > 0:
            chg = (mp_today - mp_5d_ago) / mp_5d_ago
            if cfg["margin_change_healthy_min"] <= chg <= cfg["margin_change_healthy_max"]:
                score += 10
                signals.append(f"融資+{chg*100:.1f}%")
            elif chg > 0.30:
                score -= 5
                signals.append(f"融資暴增+{chg*100:.1f}%⚠️")
            elif chg < -0.10:
                score -= 15
                signals.append(f"融資-{abs(chg)*100:.1f}%↓")

    # ── 融資使用率 ───────────────────────────────────────────────────────
    if mp_limit > 0 and mp_today > 0:
        usage = mp_today / mp_limit
        if usage < cfg["margin_usage_low"]:
            score += 5
            signals.append(f"使用率{usage*100:.0f}%↓")
        elif usage > cfg["margin_usage_high"]:
            score -= 10
            signals.append(f"使用率{usage*100:.0f}%↑高")

    return float(max(0.0, min(100.0, score))), signals


def run(margin_data: dict, stock_ids: list, cutoff_date: str = None) -> pd.DataFrame:
    """
    批次計算所有股票的融資融券評分

    Args:
        margin_data: {stock_id: DataFrame}（TaiwanStockMarginPurchaseShortSale）
        stock_ids:   要評分的股票代號 list

    Returns:
        DataFrame，columns: [stock_id, margin_score, margin_signals]
    """
    records = []
    for sid in stock_ids:
        df = margin_data.get(sid, pd.DataFrame())
        score, signals = score_margin(df, cutoff_date)
        records.append({
            "stock_id":       sid,
            "margin_score":   round(score, 1),
            "margin_signals": " | ".join(signals) if signals else "",
        })
    return pd.DataFrame(records)

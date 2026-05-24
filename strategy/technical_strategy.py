"""
strategy/technical_strategy.py
技術面策略：均線交叉、MACD、突破、RSI、振幅、均量
輸入：日K DataFrame（含 date, open, high, low, close, Trading_Volume）
輸出：含技術評分的 DataFrame（0~100）
"""
import pandas as pd
import numpy as np
from config.settings import SCREENER


def add_ma(df: pd.DataFrame, short: int = None, long: int = None) -> pd.DataFrame:
    """加入均線欄位"""
    s = short or SCREENER["ma_short"]
    l = long  or SCREENER["ma_long"]
    df = df.copy()
    df[f"ma{s}"]  = df["close"].rolling(s).mean()
    df[f"ma{l}"]  = df["close"].rolling(l).mean()
    df["ma60"]    = df["close"].rolling(60).mean()
    return df


def add_macd(df: pd.DataFrame,
             fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """加入 MACD 欄位"""
    df = df.copy()
    ema_fast   = df["close"].ewm(span=fast,   adjust=False).mean()
    ema_slow   = df["close"].ewm(span=slow,   adjust=False).mean()
    df["macd"]        = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """加入 RSI 欄位"""
    df   = df.copy()
    diff = df["close"].diff()
    gain = diff.clip(lower=0).rolling(period).mean()
    loss = (-diff.clip(upper=0)).rolling(period).mean()
    rs   = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def add_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """加入量比欄位（當日成交量 / N日均量）"""
    df = df.copy()
    vol_col = "Trading_Volume" if "Trading_Volume" in df.columns else "volume"
    if vol_col in df.columns:
        df["vol_ma"] = df[vol_col].rolling(period).mean()
        df["vol_ratio"] = df[vol_col] / df["vol_ma"].replace(0, np.nan)
    else:
        df["vol_ratio"] = np.nan
    return df


def add_amplitude(df: pd.DataFrame) -> pd.DataFrame:
    """加入振幅欄位（(high-low)/close）"""
    df = df.copy()
    df["amplitude"] = (df["high"] - df["low"]) / df["close"]
    return df


def add_breakout(df: pd.DataFrame, n: int = None) -> pd.DataFrame:
    """加入突破訊號（收盤 > N日最高）"""
    n  = n or SCREENER["breakout_days"]
    df = df.copy()
    df["high_n"]    = df["high"].rolling(n).max().shift(1)
    df["breakout"]  = df["close"] > df["high_n"]
    return df


def score_stock(df: pd.DataFrame) -> float:
    """
    計算單一股票的技術面評分（0~100）

    評分邏輯：
    - MA 黃金交叉    +20
    - 站上 MA60      +10
    - MACD 柱狀 > 0  +20
    - RSI 30~70 健康  +15（過熱/超賣各扣10）
    - 突破N日高點     +20
    - 量比 > 1.5      +15
    """
    if df.empty or len(df) < 60:
        return 0.0

    short = SCREENER["ma_short"]
    long  = SCREENER["ma_long"]

    df = add_ma(df)
    df = add_macd(df)
    df = add_rsi(df)
    df = add_volume_ratio(df)
    df = add_breakout(df)

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    score = 0.0

    # MA 黃金交叉（短線穿越長線）
    ma_short_now  = last.get(f"ma{short}", np.nan)
    ma_long_now   = last.get(f"ma{long}",  np.nan)
    ma_short_prev = prev.get(f"ma{short}", np.nan)
    ma_long_prev  = prev.get(f"ma{long}",  np.nan)

    if not any(pd.isna([ma_short_now, ma_long_now, ma_short_prev, ma_long_prev])):
        if ma_short_now > ma_long_now and ma_short_prev <= ma_long_prev:
            score += 20   # 黃金交叉
        elif ma_short_now > ma_long_now:
            score += 10   # 多頭排列（已交叉）

    # 站上 MA60
    ma60 = last.get("ma60", np.nan)
    if not pd.isna(ma60) and last["close"] > ma60:
        score += 10

    # MACD 柱狀 > 0（動能向上）
    macd_hist = last.get("macd_hist", np.nan)
    if not pd.isna(macd_hist):
        if macd_hist > 0:
            score += 20
        elif macd_hist > prev.get("macd_hist", np.nan):
            score += 8    # 柱狀轉正中

    # RSI 健康區間
    rsi = last.get("rsi", np.nan)
    if not pd.isna(rsi):
        if SCREENER["rsi_oversold"] < rsi < SCREENER["rsi_overbought"]:
            score += 15
        elif rsi <= SCREENER["rsi_oversold"]:
            score -= 10   # 超賣，扣分
        else:
            score -= 10   # 超買，扣分

    # 突破N日高點
    if last.get("breakout", False):
        vol_ratio = last.get("vol_ratio", 0)
        if vol_ratio >= SCREENER["volume_ratio"]:
            score += 20   # 放量突破
        else:
            score += 10   # 縮量突破

    # 量比 > 1.5（即使無突破也給分）
    vol_ratio = last.get("vol_ratio", np.nan)
    if not pd.isna(vol_ratio) and vol_ratio >= SCREENER["volume_ratio"] \
            and not last.get("breakout", False):
        score += 8

    return float(max(0.0, min(100.0, score)))


def run(price_data: dict, cutoff_date: str = None) -> pd.DataFrame:
    """
    批次計算所有股票的技術面評分

    Args:
        price_data:  {stock_id: DataFrame}（還原股價日K）
        cutoff_date: 若指定，只用 <= 此日期的資料（動態回測用）

    Returns:
        DataFrame，columns: [stock_id, tech_score, signals]
    """
    records = []
    for sid, df in price_data.items():
        # 欄位標準化
        df = df.copy()
        col_map = {c: c.lower() for c in df.columns}
        col_map.update({
            "close":  "close",
            "Close":  "close",
            "open":   "open",
            "Open":   "open",
            "high":   "high",
            "High":   "high",
            "max":    "high",   # FinMind price dataset
            "low":    "low",
            "Low":    "low",
            "min":    "low",    # FinMind price dataset
        })
        df = df.rename(columns=col_map)
        if "date" in df.columns:
            df = df.sort_values("date")
            if cutoff_date:
                df = df[df["date"] <= cutoff_date]

        score = score_stock(df)

        # 收集主要訊號描述
        signals = []
        if len(df) >= 2:
            df2 = add_ma(add_macd(add_rsi(add_volume_ratio(add_breakout(df)))))
            last = df2.iloc[-1]
            short, long = SCREENER["ma_short"], SCREENER["ma_long"]
            if last.get(f"ma{short}", 0) > last.get(f"ma{long}", 0):
                signals.append("MA多頭")
            if last.get("macd_hist", 0) > 0:
                signals.append("MACD↑")
            if last.get("breakout", False):
                signals.append(f"突破{SCREENER['breakout_days']}日高")
            rsi = last.get("rsi", 50)
            if not pd.isna(rsi):
                signals.append(f"RSI={rsi:.0f}")

        records.append({
            "stock_id":   sid,
            "tech_score": round(score, 1),
            "signals":    " | ".join(signals),
        })

    return pd.DataFrame(records).sort_values("tech_score", ascending=False).reset_index(drop=True)

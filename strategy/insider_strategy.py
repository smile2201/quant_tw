"""
strategy/insider_strategy.py
內部人持股申報策略
資料來源：data/mops_fetcher.py（MOPS 公開資訊觀測站）

評分邏輯（0~100，起始 50）：
  無申報轉讓紀錄（近30日）  : +5（籌碼安穩）
  申報轉讓 < 100萬股        : -10（小量賣出）
  申報轉讓 >= 100萬股       : -20（大量賣出，警示）
  申報轉讓 >= 500萬股       : -30（重大出脫）
  若資料不可用（MOPS失敗）  : 回傳 50（中性，不影響選股）
"""
import pandas as pd
from data.mops_fetcher import fetch_insider_transfers


def score_insider(stock_id: str, insider_df: pd.DataFrame = None) -> tuple[float, str]:
    """
    計算單一股票內部人評分

    Args:
        stock_id:   股票代號
        insider_df: 已抓好的 DataFrame（None 時自動抓）

    Returns:
        (score 0~100, signal_str)
    """
    if insider_df is None:
        insider_df = fetch_insider_transfers(stock_id)

    if insider_df is None or insider_df.empty:
        return 50.0, ""

    # 找「申報轉讓股數」欄位
    share_col = next(
        (c for c in insider_df.columns if "股數" in c or "轉讓" in c),
        None,
    )
    if not share_col:
        return 50.0, ""

    # 加總總申報轉讓股數（去掉非數字行）
    shares_series = pd.to_numeric(
        insider_df[share_col].astype(str).str.replace(",", ""), errors="coerce"
    )
    total_shares = shares_series.dropna().sum()

    score  = 50.0
    signal = ""

    if total_shares == 0:
        score  += 5
        signal  = "近月無申報轉讓"
    elif total_shares < 1_000_000:
        score  -= 10
        signal  = f"申報轉讓{total_shares/10000:.0f}萬股"
    elif total_shares < 5_000_000:
        score  -= 20
        signal  = f"⚠️ 申報轉讓{total_shares/10000:.0f}萬股"
    else:
        score  -= 30
        signal  = f"🔴 大量轉讓{total_shares/10000:.0f}萬股"

    return float(max(0.0, min(100.0, score))), signal


def run(stock_ids: list, insider_cache: dict = None) -> pd.DataFrame:
    """
    批次計算所有股票的內部人評分
    insider_cache: {stock_id: DataFrame}（預先抓好；None 時逐支抓）
    """
    insider_cache = insider_cache or {}
    records = []

    for sid in stock_ids:
        df    = insider_cache.get(sid)   # None = 讓 score_insider 自行抓
        score, signal = score_insider(sid, df)
        records.append({
            "stock_id":       sid,
            "insider_score":  round(score, 1),
            "insider_signal": signal,
        })

    return pd.DataFrame(records)

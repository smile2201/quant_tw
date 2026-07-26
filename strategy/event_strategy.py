"""
strategy/event_strategy.py
事件驅動策略：TWSE 重大訊息分析
輸入：twse_fetcher 抓回的重大訊息 DataFrame
輸出：含事件評分的 DataFrame（0~100）
"""
import pandas as pd
from config.settings import SCREENER


# 事件類型權重
# 2026-07-26 review：原關鍵字近乎打不中（event σ≈0），因 TWSE 主旨用正式用語
# （「法人說明會」非「法說會」、「合併營收」非「獲利」）。改用實際公告措辭。
EVENT_WEIGHTS = {
    "positive": {
        # 營收/獲利（TWSE 正式用語）
        "營收創新高":   30,
        "創歷史新高":   30,
        "合併營收":     10,   # 每月例行公告，僅小加分
        "轉虧為盈":     30,
        "轉盈":         30,
        "獲利":         20,
        # 訂單/合約
        "重大契約":     35,
        "重大合約":     35,
        "取得訂單":     30,
        "得標":         30,
        # 合作/擴張
        "策略聯盟":     20,
        "合作備忘錄":   20,
        "策略合作":     20,
        "擴建":         15,
        "新廠":         15,
        # 股東回饋
        "買回":         15,   # 庫藏股買回
        "現金增資":     -5,   # 稀釋，微扣
        # 法說會（例行，微加分）
        "法人說明會":   8,
        "法說會":       8,
    },
    "negative": {
        "財務困難":     -50,
        "全額交割":     -50,
        "重整":         -45,
        "裁罰":         -40,
        "罰鍰":         -30,
        "重大虧損":     -45,
        "減資彌補虧損": -40,
        "下市":         -60,
        "終止上市":     -60,
        "停業":         -50,
        "違約":         -40,
        "掏空":         -60,
        "背信":         -50,
        "起訴":         -30,
        "假扣押":       -35,
        "董事長辭任":   -20,
        "更換會計師":   -25,
    },
}


def classify_event(subject: str, description: str = "") -> tuple[str, int]:
    """
    分類重大訊息事件，回傳 (類型, 分數)

    Returns:
        (event_type, score)
        event_type: "positive" | "negative" | "neutral"
    """
    text = str(subject) + " " + str(description)

    neg_score = 0
    for kw, weight in EVENT_WEIGHTS["negative"].items():
        if kw in text:
            neg_score += weight

    pos_score = 0
    for kw, weight in EVENT_WEIGHTS["positive"].items():
        if kw in text:
            pos_score += weight

    total = pos_score + neg_score  # neg 已是負值

    if neg_score < -30:
        return "negative", max(-100, total)
    elif total > 0:
        return "positive", min(100, total)
    else:
        return "neutral", 0


def score_from_news(news_df: pd.DataFrame, stock_id: str) -> tuple[float, list]:
    """
    從當日重大訊息計算單一股票的事件評分

    Returns:
        (score, event_list)
    """
    if news_df.empty:
        return 0.0, []

    # 過濾此股票
    col = "公司代號"
    if col not in news_df.columns:
        return 0.0, []

    stock_news = news_df[news_df[col].str.strip() == str(stock_id)]
    if stock_news.empty:
        return 0.0, []

    total_score = 0.0
    events = []

    for _, row in stock_news.iterrows():
        subject = str(row.get("主旨", ""))
        desc    = str(row.get("說明", ""))
        etype, score = classify_event(subject, desc)

        if etype != "neutral":
            total_score += score
            events.append(f"[{etype}] {subject[:30]}")

    # 多個事件時，後面的影響遞減
    if len(events) > 1:
        total_score = total_score * 0.8

    return float(max(-100.0, min(100.0, total_score))), events


def run(news_df: pd.DataFrame, stock_ids: list) -> pd.DataFrame:
    """
    批次計算所有股票的事件評分

    Args:
        news_df:   fetch_material_news() 回傳的 DataFrame
        stock_ids: 要評分的股票代號 list

    Returns:
        DataFrame，columns: [stock_id, event_score, events]
    """
    records = []
    for sid in stock_ids:
        score, events = score_from_news(news_df, sid)

        # 事件評分轉換到 0~100（負面事件給0，讓 hybrid 做扣分）
        # 原始分：-100~+100
        # 正規化：正面→50~100，中性→50，負面→0~49
        normalized = 50.0 + score / 2.0
        normalized = max(0.0, min(100.0, normalized))

        records.append({
            "stock_id":    sid,
            "event_score": round(normalized, 1),
            "raw_score":   round(score, 1),
            "events":      " | ".join(events) if events else "無重大訊息",
        })

    return pd.DataFrame(records).sort_values("event_score", ascending=False).reset_index(drop=True)

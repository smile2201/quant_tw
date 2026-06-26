"""
strategy/news_strategy.py
新聞情緒分析（不依賴 NLP 套件）
以關鍵字加權評分，涵蓋繁體中文及英文財經術語

評分設計：
  - 每則新聞正負關鍵字加總 → 單則分數
  - 多則新聞取加權平均（近期新聞權重較高）
  - 最終正規化為 0~100（50 = 中性）
  - 僅作為「補充訊號」顯示在通知，不影響 final_score
"""
from datetime import datetime, timezone

POSITIVE = {
    # 業績/獲利
    "創新高": 25, "獲利": 20, "轉盈": 25, "盈餘": 20, "亮眼": 20,
    "大幅成長": 25, "營收成長": 20, "EPS": 15, "超預期": 25,
    # 訂單/合約
    "重大合約": 30, "訂單": 20, "大單": 25, "取得訂單": 25,
    "合作": 15, "策略聯盟": 20,
    # 法人/分析師
    "買進": 20, "目標價上調": 25, "上調": 20, "看好": 20,
    "強烈買進": 30, "outperform": 20, "buy": 15, "upgrade": 25,
    # 擴張
    "擴產": 20, "布局": 15, "新廠": 20, "新產品": 15, "突破": 15,
    # 市場地位
    "市占": 15, "龍頭": 15, "領先": 15,
}

NEGATIVE = {
    # 財務危機
    "財務困難": -45, "掏空": -60, "違約": -40, "下市": -60,
    "停業": -50, "重整": -40, "破產": -55,
    # 業績衰退
    "虧損": -25, "重大虧損": -40, "下修": -25, "調降": -20,
    "營收衰退": -20, "衰退": -20, "不如預期": -20,
    # 法規/裁罰
    "裁罰": -30, "罰款": -25, "警告": -20, "停工": -30,
    "注意股": -35, "警示股": -40,
    # 法人降評
    "賣出": -20, "降評": -25, "目標價下調": -25, "看壞": -25,
    "underperform": -20, "sell": -15, "downgrade": -25,
    # 人事
    "董事長辭職": -20, "高層異動": -15,
}


def _score_title(title: str) -> int:
    title_lower = title.lower()
    score = 0
    for kw, weight in POSITIVE.items():
        if kw.lower() in title_lower:
            score += weight
    for kw, weight in NEGATIVE.items():
        if kw.lower() in title_lower:
            score += weight   # weight 已是負值
    return score


def score_news(news_list: list) -> tuple[float, str]:
    """
    對單一股票的新聞清單評分

    Args:
        news_list: [{title, publisher, publishTime}]

    Returns:
        (normalized_score 0~100, signal_str)
    """
    if not news_list:
        return 50.0, ""

    now_ts  = datetime.now(timezone.utc).timestamp()
    raw_scores = []

    for item in news_list:
        title = item.get("title", "")
        if not title:
            continue

        raw  = _score_title(title)
        if raw == 0:
            continue

        # 越新的新聞權重越高（48小時內 = 全權重，之後線性遞減至 0.3）
        pub_ts = item.get("publishTime", now_ts)
        age_h  = max(0, (now_ts - pub_ts) / 3600)
        w      = max(0.3, 1.0 - age_h / 48)

        raw_scores.append((raw, w, title[:20]))

    if not raw_scores:
        return 50.0, ""

    total_w    = sum(w for _, w, _ in raw_scores)
    weighted   = sum(r * w for r, w, _ in raw_scores) / total_w
    normalized = max(0.0, min(100.0, 50 + weighted / 2))

    # 找最具代表性的那則
    best_title = max(raw_scores, key=lambda x: abs(x[0]))[2]
    if weighted > 15:
        signal = f"📰 正面 {best_title}…"
    elif weighted < -15:
        signal = f"📰 ⚠️負面 {best_title}…"
    else:
        signal = ""   # 中性不顯示

    return round(normalized, 1), signal


def run(news_data: dict, stock_ids: list) -> "pd.DataFrame":
    import pandas as pd
    records = []
    for sid in stock_ids:
        news_list = news_data.get(sid, [])
        score, signal = score_news(news_list)
        records.append({
            "stock_id":    sid,
            "news_score":  score,
            "news_signal": signal,
        })
    return pd.DataFrame(records)

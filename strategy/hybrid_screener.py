"""
strategy/hybrid_screener.py
混合評分器：技術面 + 基本面 + 事件驅動，加權合成
各模組可獨立開關，方便 ablation 實驗
"""
import pandas as pd
from config.settings import SCREENER
from strategy import technical_strategy as tech
from strategy import fundamental_strategy as fund
from strategy import event_strategy as event


def run(
    price_data:  dict,
    fund_data:   dict,
    news_df:     pd.DataFrame,
    use_tech:    bool = True,
    use_fund:    bool = True,
    use_event:   bool = True,
) -> pd.DataFrame:
    """
    混合評分主函式

    Args:
        price_data:  {stock_id: price_adj_df}（技術面用）
        fund_data:   {stock_id: {"financial":df, "dividend":df, "revenue":df}}
        news_df:     TWSE 重大訊息 DataFrame
        use_tech:    是否啟用技術面（ablation 用）
        use_fund:    是否啟用基本面
        use_event:   是否啟用事件驅動

    Returns:
        DataFrame，columns: [stock_id, final_score, tech_score, fund_score,
                             event_score, tier, tech_signals, fund_signals, events]
        tier: "強力候選" | "觀察股" | "普通"
    """
    stock_ids = list(price_data.keys())

    # ── 各模組評分 ─────────────────────────────────────────────────────────────
    tech_df  = tech.run(price_data)  if use_tech  else _zero_df(stock_ids, "tech_score")
    fund_df  = fund.run(fund_data)   if use_fund  else _zero_df(stock_ids, "fund_score")
    event_df = event.run(news_df, stock_ids) if use_event else _zero_df(stock_ids, "event_score")

    # ── 合併 ──────────────────────────────────────────────────────────────────
    result = pd.DataFrame({"stock_id": stock_ids})
    result = result.merge(tech_df[["stock_id","tech_score","signals"]].rename(
                          columns={"signals":"tech_signals"}), on="stock_id", how="left")
    result = result.merge(fund_df[["stock_id","fund_score","signals"]].rename(
                          columns={"signals":"fund_signals"}), on="stock_id", how="left")
    result = result.merge(event_df[["stock_id","event_score","events"]], on="stock_id", how="left")

    result = result.fillna({"tech_score":0,"fund_score":0,"event_score":50,
                            "tech_signals":"","fund_signals":"","events":""})

    # ── 動態權重（停用模組時重新分配）──────────────────────────────────────────
    w_tech  = SCREENER["weight_technical"]  if use_tech  else 0
    w_fund  = SCREENER["weight_fundamental"] if use_fund  else 0
    w_event = SCREENER["weight_event"]      if use_event else 0
    total_w = w_tech + w_fund + w_event
    if total_w == 0:
        total_w = 1

    result["final_score"] = (
        result["tech_score"]  * (w_tech  / total_w) +
        result["fund_score"]  * (w_fund  / total_w) +
        result["event_score"] * (w_event / total_w)
    ).round(1)

    # ── 分層 ──────────────────────────────────────────────────────────────────
    result["tier"] = result["final_score"].apply(_tier)

    return result.sort_values("final_score", ascending=False).reset_index(drop=True)


def _tier(score: float) -> str:
    if score >= SCREENER["threshold_strong"]:
        return "強力候選"
    elif score >= SCREENER["threshold_watch"]:
        return "觀察股"
    else:
        return "普通"


def _zero_df(stock_ids: list, score_col: str) -> pd.DataFrame:
    """停用某模組時，回傳全0（事件模組用50，代表中性）"""
    default = 50 if "event" in score_col else 0
    return pd.DataFrame({
        "stock_id": stock_ids,
        score_col:  [float(default)] * len(stock_ids),
        "signals":  [""] * len(stock_ids),
        "events":   [""] * len(stock_ids),
    })

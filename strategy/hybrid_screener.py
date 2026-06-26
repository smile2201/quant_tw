"""
strategy/hybrid_screener.py
混合評分器：技術面 + 基本面 + 事件驅動 + 籌碼面，加權合成
各模組可獨立開關，方便 ablation 實驗
"""
import pandas as pd
from config.settings import SCREENER
from strategy import technical_strategy as tech
from strategy import fundamental_strategy as fund
from strategy import event_strategy as event
from strategy import chip_strategy as chip


def run(
    price_data:  dict,
    fund_data:   dict,
    news_df:     pd.DataFrame,
    inst_data:   dict         = None,
    use_tech:    bool         = True,
    use_fund:    bool         = True,
    use_event:   bool         = True,
    use_chip:    bool         = True,
    cutoff_date: str          = None,
) -> pd.DataFrame:
    """
    混合評分主函式

    Args:
        price_data:  {stock_id: price_adj_df}（技術面用）
        fund_data:   {stock_id: {"financial":df, "dividend":df, "revenue":df}}
        news_df:     TWSE 重大訊息 DataFrame
        inst_data:   {stock_id: 三大法人 DataFrame}（籌碼面用，可為 None）
        use_tech:    是否啟用技術面（ablation 用）
        use_fund:    是否啟用基本面
        use_event:   是否啟用事件驅動
        use_chip:    是否啟用籌碼面
        cutoff_date: 若指定，只用 <= 此日期的資料；事件/籌碼改用中性分（動態回測用）

    Returns:
        DataFrame，columns: [stock_id, final_score, tech_score, fund_score,
                             event_score, chip_score, tier,
                             tech_signals, fund_signals, events, chip_signals]
        tier: "強力候選" | "觀察股" | "普通"
    """
    stock_ids = list(price_data.keys())
    inst_data = inst_data or {}

    # ── 各模組評分 ─────────────────────────────────────────────────────────────
    tech_df = tech.run(price_data, cutoff_date=cutoff_date) if use_tech \
              else _zero_df(stock_ids, "tech_score")
    fund_df = fund.run(fund_data,  cutoff_date=cutoff_date) if use_fund \
              else _zero_df(stock_ids, "fund_score")

    # 事件面 & 籌碼面：動態回測時用中性分（50）避免未來資訊偏差
    if cutoff_date:
        event_df = _neutral_df(stock_ids, "event_score")
        chip_df  = _neutral_df(stock_ids, "chip_score")
    else:
        event_df = event.run(news_df, stock_ids) if use_event \
                   else _neutral_df(stock_ids, "event_score")
        chip_df  = chip.run(inst_data, stock_ids) if use_chip \
                   else _neutral_df(stock_ids, "chip_score")

    # ── 合併 ──────────────────────────────────────────────────────────────────
    result = pd.DataFrame({"stock_id": stock_ids})
    result = result.merge(tech_df[["stock_id","tech_score","signals"]].rename(
                          columns={"signals":"tech_signals"}), on="stock_id", how="left")
    result = result.merge(fund_df[["stock_id","fund_score","signals"]].rename(
                          columns={"signals":"fund_signals"}), on="stock_id", how="left")
    result = result.merge(event_df[["stock_id","event_score","events"]], on="stock_id", how="left")
    result = result.merge(chip_df[["stock_id","chip_score","chip_signals"]], on="stock_id", how="left")

    result = result.fillna({
        "tech_score": 0,  "fund_score": 0,
        "event_score": 50, "chip_score": 50,
        "tech_signals": "", "fund_signals": "",
        "events": "", "chip_signals": "",
    })

    # ── 動態權重（停用模組時重新分配）──────────────────────────────────────────
    w_tech  = SCREENER["weight_technical"]   if use_tech  else 0
    w_fund  = SCREENER["weight_fundamental"] if use_fund  else 0
    w_event = SCREENER["weight_event"]       if use_event else 0
    w_chip  = SCREENER["weight_chip"]        if use_chip  else 0
    total_w = w_tech + w_fund + w_event + w_chip
    if total_w == 0:
        total_w = 1

    result["final_score"] = (
        result["tech_score"]  * (w_tech  / total_w) +
        result["fund_score"]  * (w_fund  / total_w) +
        result["event_score"] * (w_event / total_w) +
        result["chip_score"]  * (w_chip  / total_w)
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
    """停用某模組時，回傳全 0 分"""
    return pd.DataFrame({
        "stock_id":    stock_ids,
        score_col:     [0.0] * len(stock_ids),
        "signals":     [""] * len(stock_ids),
        "events":      [""] * len(stock_ids),
        "chip_signals": [""] * len(stock_ids),
    })


def _neutral_df(stock_ids: list, score_col: str) -> pd.DataFrame:
    """回測或停用時用中性分（50）"""
    return pd.DataFrame({
        "stock_id":    stock_ids,
        score_col:     [50.0] * len(stock_ids),
        "signals":     [""] * len(stock_ids),
        "events":      [""] * len(stock_ids),
        "chip_signals": [""] * len(stock_ids),
    })

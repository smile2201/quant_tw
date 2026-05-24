"""
scripts/run_screener.py
每日盤後選股評分腳本
執行：python scripts/run_screener.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import BACKTEST, RESULTS_DIR
from data.finmind_fetcher import fetch_stock, get_tw50_stocks
from data.twse_fetcher import fetch_material_news, load_material_news
from strategy import hybrid_screener

RESULTS_DIR_PATH = Path(os.path.dirname(os.path.dirname(__file__))) / "results"
RESULTS_DIR_PATH.mkdir(exist_ok=True)


def run(stock_ids: list = None, use_cached_news: bool = False) -> pd.DataFrame:
    """
    執行今日選股評分

    Args:
        stock_ids:        要評分的股票清單（預設台灣50）
        use_cached_news:  True=讀今日已存的TWSE資料，False=重新抓

    Returns:
        評分 DataFrame
    """
    stock_ids = stock_ids or get_tw50_stocks()
    today     = datetime.now().strftime("%Y%m%d")

    print(f"=== 選股評分 {today} ===")
    print(f"股票池：{len(stock_ids)} 檔")

    # 1. 抓 TWSE 重大訊息
    print("\n[1/3] TWSE 重大訊息...")
    if use_cached_news:
        news_df = load_material_news()
    else:
        news_df = fetch_material_news()

    # 2. 讀 FinMind cache（只讀 price_adj）
    print("\n[2/3] 載入價格資料...")
    price_data = {}
    fund_data  = {}

    for sid in stock_ids:
        # 技術面：還原股價
        price_df = fetch_stock(sid, "price_adj")
        if not price_df.empty:
            price_data[sid] = price_df

        # 基本面
        fin_df  = fetch_stock(sid, "financial")
        div_df  = fetch_stock(sid, "dividend")
        rev_df  = fetch_stock(sid, "revenue")
        fund_data[sid] = {
            "financial": fin_df,
            "dividend":  div_df,
            "revenue":   rev_df,
        }

    print(f"   有價格資料：{len(price_data)} 檔")

    # 3. 混合評分
    print("\n[3/3] 混合評分...")
    result = hybrid_screener.run(price_data, fund_data, news_df)

    # 4. 存結果
    out_path = RESULTS_DIR_PATH / f"{today}_screener.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n結果已存：{out_path}")

    # 5. 印出摘要
    strong = result[result["tier"] == "強力候選"]
    watch  = result[result["tier"] == "觀察股"]
    print(f"\n{'='*50}")
    print(f"強力候選（{len(strong)} 檔）：{', '.join(strong['stock_id'].tolist())}")
    print(f"觀察股  （{len(watch)} 檔）：{', '.join(watch['stock_id'].tolist())}")
    print(f"{'='*50}")

    return result


if __name__ == "__main__":
    run()

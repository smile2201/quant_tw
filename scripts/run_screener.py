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

from config.settings import FINMIND_PRICE_DATASET
from data.finmind_fetcher import fetch_stock, get_tw50_stocks
from data.twse_fetcher import fetch_material_news, load_material_news
from strategy import hybrid_screener

RESULTS_DIR_PATH = Path(os.path.dirname(os.path.dirname(__file__))) / "results"
RESULTS_DIR_PATH.mkdir(exist_ok=True)


def run(stock_ids: list = None, use_cached_news: bool = False) -> pd.DataFrame:
    stock_ids = stock_ids or get_tw50_stocks()
    today     = datetime.now().strftime("%Y%m%d")

    print(f"=== 選股評分 {today} ===")
    print(f"股票池：{len(stock_ids)} 檔，資料集：{FINMIND_PRICE_DATASET}")

    print("\n[1/3] TWSE 重大訊息...")
    news_df = load_material_news() if use_cached_news else fetch_material_news()

    print("\n[2/3] 載入價格資料...")
    price_data = {}
    fund_data  = {}

    for sid in stock_ids:
        price_df = fetch_stock(sid, FINMIND_PRICE_DATASET)  # 自動讀設定
        if not price_df.empty:
            price_data[sid] = price_df

        fund_data[sid] = {
            "financial": fetch_stock(sid, "financial"),
            "dividend":  fetch_stock(sid, "dividend"),
            "revenue":   fetch_stock(sid, "revenue"),
        }

    print(f"   有價格資料：{len(price_data)} 檔")

    print("\n[3/3] 混合評分...")
    result = hybrid_screener.run(price_data, fund_data, news_df)

    out_path = RESULTS_DIR_PATH / f"{today}_screener.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n結果已存：{out_path}")

    strong = result[result["tier"] == "強力候選"]
    watch  = result[result["tier"] == "觀察股"]
    print(f"\n{'='*50}")
    print(f"強力候選（{len(strong)} 檔）：{', '.join(strong['stock_id'].tolist())}")
    print(f"觀察股  （{len(watch)} 檔）：{', '.join(watch['stock_id'].tolist())}")
    print(f"{'='*50}")

    return result


if __name__ == "__main__":
    run()

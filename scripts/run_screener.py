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
from data.macro_fetcher import fetch_vix, fetch_fed_rate, fetch_tw_futures_foreign, build_context
from data.news_fetcher import fetch_batch as fetch_news_batch
from strategy import hybrid_screener, news_strategy
from notify import line_bot

RESULTS_DIR_PATH = Path(os.path.dirname(os.path.dirname(__file__))) / "results"
RESULTS_DIR_PATH.mkdir(exist_ok=True)


def run(stock_ids: list = None, use_cached_news: bool = False) -> pd.DataFrame:
    stock_ids = stock_ids or get_tw50_stocks()
    today     = datetime.now().strftime("%Y%m%d")

    print(f"=== 選股評分 {today} ===")
    print(f"股票池：{len(stock_ids)} 檔，資料集：{FINMIND_PRICE_DATASET}")

    print("\n[1/6] TWSE 重大訊息...")
    news_df = load_material_news() if use_cached_news else fetch_material_news()

    print("\n[2/6] 載入價格 & 基本面資料...")
    price_data = {}
    fund_data  = {}

    for sid in stock_ids:
        price_df = fetch_stock(sid, FINMIND_PRICE_DATASET)
        if not price_df.empty:
            price_data[sid] = price_df

        fund_data[sid] = {
            "financial": fetch_stock(sid, "financial"),
            "dividend":  fetch_stock(sid, "dividend"),
            "revenue":   fetch_stock(sid, "revenue"),
        }

    print(f"   有價格資料：{len(price_data)} 檔")

    print("\n[3/6] 載入三大法人籌碼資料...")
    inst_data = {}
    for sid in stock_ids:
        df = fetch_stock(sid, "institutional")
        if not df.empty:
            inst_data[sid] = df
    print(f"   有籌碼資料：{len(inst_data)} 檔")

    print("\n[4/6] 載入融資融券資料...")
    margin_data = {}
    for sid in stock_ids:
        df = fetch_stock(sid, "margin")
        if not df.empty:
            margin_data[sid] = df
    print(f"   有融資融券資料：{len(margin_data)} 檔")

    print("\n[5/6] 總體經濟指標...")
    vix_data     = fetch_vix()
    fed_data     = fetch_fed_rate()
    futures_data = fetch_tw_futures_foreign()
    macro_ctx    = build_context(vix_data, fed_data, futures_data)
    if macro_ctx:
        print(f"   {macro_ctx}")

    print("\n[評分] 混合評分...")
    result = hybrid_screener.run(
        price_data, fund_data, news_df,
        inst_data=inst_data,
        margin_data=margin_data,
        macro_context=macro_ctx,
    )

    print("\n[6/6] 新聞情緒（強力候選 + 觀察股）...")
    top_ids  = result[result["tier"].isin(["強力候選", "觀察股"])]["stock_id"].tolist()
    news_raw = fetch_news_batch(top_ids)
    news_df2 = news_strategy.run(news_raw, top_ids)
    result   = result.merge(news_df2[["stock_id", "news_signal"]], on="stock_id", how="left")
    result["news_signal"] = result["news_signal"].fillna("")
    hit = result[result["news_signal"] != ""]
    print(f"   有情緒訊號：{len(hit)} 檔")

    out_path = RESULTS_DIR_PATH / f"{today}_screener.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n結果已存：{out_path}")

    strong = result[result["tier"] == "強力候選"]
    watch  = result[result["tier"] == "觀察股"]
    print(f"\n{'='*50}")
    print(f"強力候選（{len(strong)} 檔）：{', '.join(strong['stock_id'].tolist())}")
    print(f"觀察股  （{len(watch)} 檔）：{', '.join(watch['stock_id'].tolist())}")
    print(f"{'='*50}")

    if os.environ.get("SEND_LINE", "true").lower() != "false":
        msg = line_bot.build_message(result, today)
        if line_bot.send(msg):
            (RESULTS_DIR_PATH / f"{today}_notified.flag").touch()
    else:
        print("[LINE] SEND_LINE=false，靜音模式，稍後由早晨補發流程通知")

    return result


if __name__ == "__main__":
    run()

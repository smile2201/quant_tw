"""
scripts/run_backtest.py
回測執行腳本（三模式）
執行：python scripts/run_backtest.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import BACKTEST, FINMIND_PRICE_DATASET
from data.finmind_fetcher import fetch_stock, get_tw50_stocks
from data.twse_fetcher import load_material_news
from strategy import hybrid_screener
from backtest.engine import run_three_modes_dynamic, compare_modes

RESULTS_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def run(stock_ids: list = None) -> dict:
    stock_ids = stock_ids or get_tw50_stocks()
    today     = datetime.now().strftime("%Y%m%d")

    print(f"=== 回測 {BACKTEST['start_date']} ~ {BACKTEST['end_date']} ===")
    print(f"股票池：{len(stock_ids)} 檔，資料集：{FINMIND_PRICE_DATASET}")

    print("\n載入資料...")
    price_data = {}
    fund_data  = {}
    for sid in stock_ids:
        df = fetch_stock(sid, FINMIND_PRICE_DATASET)  # 自動讀設定
        if not df.empty:
            price_data[sid] = df
        fund_data[sid] = {
            "financial": fetch_stock(sid, "financial"),
            "dividend":  fetch_stock(sid, "dividend"),
            "revenue":   fetch_stock(sid, "revenue"),
        }

    print("\n開始動態回測（三模式，每5個交易日重新評分）...")
    news_df = load_material_news()
    results = run_three_modes_dynamic(price_data, fund_data, news_df)

    comparison = compare_modes(results)
    print(f"\n{'='*60}")
    print(comparison.to_string(index=False))
    print(f"{'='*60}")

    comparison.to_csv(RESULTS_DIR / f"{today}_backtest_comparison.csv",
                      index=False, encoding="utf-8-sig")

    for mode, result in results.items():
        eq = result.equity_curve
        if not eq.empty:
            eq.to_csv(RESULTS_DIR / f"{today}_equity_{mode}.csv",
                      header=["equity"], encoding="utf-8-sig")

    print(f"\n結果已存到 results/")
    return results


if __name__ == "__main__":
    run()

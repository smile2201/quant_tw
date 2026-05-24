"""
scripts/update_cache.py
更新 FinMind cache + TWSE 每日資料
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.finmind_fetcher import fetch_multiple, get_tw50_stocks
from data.twse_fetcher import fetch_material_news, fetch_company_info
from config.settings import FINMIND_PLAN, FINMIND_PRICE_DATASET

if __name__ == "__main__":
    print(f"[設定] 帳號方案：{FINMIND_PLAN}，股價資料集：{FINMIND_PRICE_DATASET}")

    print("\n=== 更新 TWSE 資料 ===")
    fetch_material_news()
    fetch_company_info()

    print(f"\n=== 更新 FinMind cache（台灣50 / {FINMIND_PRICE_DATASET}）===")
    stocks = get_tw50_stocks()
    fetch_multiple(stocks, dataset=FINMIND_PRICE_DATASET)
    print("\n完成")

"""
data/news_fetcher.py
個股新聞抓取（Yahoo Finance，免費無需帳號）
- 只對選股結果中的強力候選+觀察股抓新聞（避免大量 API 呼叫）
- 每支股票抓最新 10 則，帶 TTL cache（同一天不重複抓）
"""
import requests
import json
import time
from pathlib import Path
from datetime import datetime

from config.settings import TWSE_DATA_DIR

YAHOO_NEWS_URL = "https://query2.finance.yahoo.com/v1/finance/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; quant_tw/1.0)"}
NEWS_CACHE_DIR = Path(TWSE_DATA_DIR) / "news_cache"


def _cache_path(stock_id: str, date_str: str) -> Path:
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return NEWS_CACHE_DIR / f"{date_str}_{stock_id}_news.json"


def fetch_stock_news(stock_id: str, count: int = 10) -> list[dict]:
    """
    抓取單一股票最新新聞（優先讀當日 cache）

    Returns:
        list of {title, publisher, publishTime (timestamp)}
    """
    today = datetime.now().strftime("%Y%m%d")
    cache = _cache_path(stock_id, today)

    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    try:
        params = {
            "q":                  f"{stock_id}.TW",
            "newsCount":          count,
            "enableFuzzyQuery":   "false",
            "lang":               "zh-Hant-TW",
            "region":             "TW",
        }
        resp = requests.get(YAHOO_NEWS_URL, headers=HEADERS, params=params, timeout=10)
        data = resp.json()
        news = data.get("news", [])

        result = [
            {
                "title":       item.get("title", ""),
                "publisher":   item.get("publisher", ""),
                "publishTime": item.get("providerPublishTime", 0),
            }
            for item in news
        ]

        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"  [news] {stock_id}：{len(result)} 則新聞")
        time.sleep(0.3)   # 避免連打太快
        return result

    except Exception as e:
        print(f"  [news] {stock_id} 新聞抓取失敗：{e}")
        return []


def fetch_batch(stock_ids: list) -> dict:
    """批次抓取，回傳 {stock_id: [news_list]}"""
    return {sid: fetch_stock_news(sid) for sid in stock_ids}

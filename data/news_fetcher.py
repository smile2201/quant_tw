"""
data/news_fetcher.py
個股新聞抓取（Google News RSS，免費免認證）
2026-07-26 review：原 Yahoo Finance search API 自 7/21 起被持續擋（Actions IP），
改用 Google News RSS——穩定且回傳繁中標題，用「公司名稱+代號」查詢。
- 只對選股結果中的強力候選+觀察股抓新聞（控制請求量）
- 每支股票帶當日 cache（同一天不重複抓）
"""
import requests
import json
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

from config.settings import TWSE_DATA_DIR

GOOGLE_NEWS_RSS = ("https://news.google.com/rss/search?"
                   "q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0.0.0 Safari/537.36")}
NEWS_CACHE_DIR = Path(TWSE_DATA_DIR) / "news_cache"


def _cache_path(stock_id: str, date_str: str) -> Path:
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return NEWS_CACHE_DIR / f"{date_str}_{stock_id}_news.json"


def _query_for(stock_id: str) -> str:
    """查詢字串：優先「公司簡稱 代號」，取不到名稱就用「代號 台股」"""
    try:
        from notify.line_bot import _load_name_map
        name = _load_name_map().get(str(stock_id), "")
    except Exception:
        name = ""
    return f"{name} {stock_id}" if name else f"{stock_id} 台股"


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
        url  = GOOGLE_NEWS_RSS.format(query=quote(_query_for(stock_id)))
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        root   = ET.fromstring(resp.content)
        result = []
        for item in root.iter("item"):
            if len(result) >= count:
                break
            title = (item.findtext("title") or "").strip()
            src   = (item.findtext("source") or "").strip()
            pub   = item.findtext("pubDate") or ""
            try:
                ts = parsedate_to_datetime(pub).timestamp()
            except Exception:
                ts = 0
            if title:
                result.append({"title": title, "publisher": src, "publishTime": ts})

        cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(f"  [news] {stock_id}：{len(result)} 則新聞")
        time.sleep(0.5)   # RSS 禮貌間隔
        return result

    except Exception as e:
        print(f"  [news] {stock_id} 新聞抓取失敗：{e}")
        return []


def fetch_batch(stock_ids: list) -> dict:
    """批次抓取，回傳 {stock_id: [news_list]}"""
    return {sid: fetch_stock_news(sid) for sid in stock_ids}

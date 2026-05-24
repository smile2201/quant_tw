"""
data/twse_fetcher.py
TWSE OpenAPI 每日資料抓取
- 重大訊息 / 公司基本資料 / 股利資料
- 無需 API key，完全免費無限制
"""
import os
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

from config.settings import TWSE_DATA_DIR

# ─── TWSE OpenAPI 端點 ────────────────────────────────────────────────────────
TWSE_BASE = "https://openapi.twse.com.tw/v1"
ENDPOINTS = {
    "material_news": f"{TWSE_BASE}/opendata/t187ap04_L",   # 每日重大訊息
    "company_info":  f"{TWSE_BASE}/opendata/t187ap03_L",   # 上市公司基本資料
    "dividend":      f"{TWSE_BASE}/opendata/t187ap45_L",   # 股利分派
}


def _today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def _save_json(data: list, name: str, date_str: str = None):
    """儲存到 data/twse/YYYYMMDD_name.json"""
    date_str = date_str or _today_str()
    p = Path(TWSE_DATA_DIR) / f"{date_str}_{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  [twse] 已存 {p} ({len(data)} 筆)")
    return p


def fetch_material_news(save: bool = True) -> pd.DataFrame:
    """
    抓取當日上市公司重大訊息
    欄位：出表日期、發言日期、發言時間、公司代號、公司名稱、主旨、符合條款、事實發生日、說明
    """
    try:
        resp = requests.get(ENDPOINTS["material_news"], timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if save:
            _save_json(data, "material_news")

        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()  # TWSE 欄位名稱有尾部空格
        print(f"  [twse] 重大訊息 {len(df)} 筆")
        return df

    except Exception as e:
        print(f"  [twse error] 重大訊息：{e}")
        return pd.DataFrame()


def fetch_company_info(save: bool = True) -> pd.DataFrame:
    """抓取上市公司基本資料（股票清單、產業分類）"""
    try:
        resp = requests.get(ENDPOINTS["company_info"], timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if save:
            _save_json(data, "company_info")

        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()  # TWSE 欄位名稱有尾部空格
        print(f"  [twse] 公司基本資料 {len(df)} 筆")
        return df

    except Exception as e:
        print(f"  [twse error] 公司基本資料：{e}")
        return pd.DataFrame()


def fetch_dividend(save: bool = True) -> pd.DataFrame:
    """抓取股利分派資料"""
    try:
        resp = requests.get(ENDPOINTS["dividend"], timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if save:
            _save_json(data, "dividend")

        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()  # TWSE 欄位名稱有尾部空格
        print(f"  [twse] 股利資料 {len(df)} 筆")
        return df

    except Exception as e:
        print(f"  [twse error] 股利：{e}")
        return pd.DataFrame()


def load_material_news(date_str: str = None) -> pd.DataFrame:
    """從本機讀取已存的重大訊息"""
    date_str = date_str or _today_str()
    p = Path(TWSE_DATA_DIR) / f"{date_str}_material_news.json"
    if not p.exists():
        print(f"  [twse] 找不到 {p}，請先執行 fetch_material_news()")
        return pd.DataFrame()
    data = json.loads(p.read_text())
    return pd.DataFrame(data)


def filter_news_by_keywords(df: pd.DataFrame,
                             positive: list, negative: list) -> pd.DataFrame:
    """
    依關鍵字篩選重大訊息
    回傳：有正面關鍵字且無負面關鍵字的行
    """
    if df.empty or "主旨" not in df.columns:
        return pd.DataFrame()

    pos_mask = df["主旨"].str.contains("|".join(positive), na=False)
    neg_mask = df["主旨"].str.contains("|".join(negative), na=False)
    return df[pos_mask & ~neg_mask].copy()


if __name__ == "__main__":
    print("測試 TWSE OpenAPI...")
    df = fetch_material_news(save=False)
    if not df.empty:
        print(df[["公司代號", "公司名稱", "主旨"]].head(10))

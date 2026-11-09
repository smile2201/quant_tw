"""
data/finmind_fetcher.py
FinMind API 抓取 + parquet cache 管理
- 寬範圍一次抓（CACHE_YEARS 年），避免重複打 API
- empty marker：無資料股票記錄下來，不重複打
- quota 用盡自動退避 65 分鐘後重試
"""
import os
import time
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from config.settings import (
    FINMIND_TOKEN, CACHE_ROOT, EMPTY_MARKER_DIR,
    FINMIND_BACKOFF, CACHE_YEARS
)

# ─── 常數 ─────────────────────────────────────────────────────────────────────
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
DATASETS = {
    "price":         "TaiwanStockPrice",
    "price_adj":     "TaiwanStockPriceAdj",   # 還原股價
    "financial":     "TaiwanStockFinancialRatio",
    "dividend":      "TaiwanStockDividend",
    "revenue":       "TaiwanStockMonthRevenue",
    "institutional": "TaiwanStockInstitutionalInvestorsBuySell",  # 三大法人
    "margin":        "TaiwanStockMarginPurchaseShortSale",         # 融資融券
}


def _cache_path(stock_id: str, dataset: str) -> Path:
    """parquet 檔案路徑"""
    d = Path(CACHE_ROOT) / dataset
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stock_id}.parquet"


def _empty_marker_path(stock_id: str, dataset: str) -> Path:
    """empty marker 路徑"""
    d = Path(EMPTY_MARKER_DIR) / dataset
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stock_id}.empty"


def _is_empty_marked(stock_id: str, dataset: str) -> bool:
    """是否已標記為無資料"""
    return _empty_marker_path(stock_id, dataset).exists()


def _mark_empty(stock_id: str, dataset: str):
    """標記此股票在此 dataset 無資料"""
    p = _empty_marker_path(stock_id, dataset)
    p.write_text(datetime.now().isoformat())
    print(f"  [empty marker] {stock_id} / {dataset}")


def _fetch_from_api(dataset_name: str, stock_id: str,
                     start_date: str, end_date: str) -> pd.DataFrame:
    """
    打 FinMind API，含 quota 退避重試邏輯
    回傳 DataFrame，失敗回傳空 DataFrame
    """
    headers = {}
    if FINMIND_TOKEN:
        headers["Authorization"] = f"Bearer {FINMIND_TOKEN}"

    params = {
        "dataset":    dataset_name,
        "data_id":    stock_id,
        "start_date": start_date,
        "end_date":   end_date,
    }

    for attempt in range(3):
        try:
            resp = requests.get(FINMIND_URL, headers=headers,
                                params=params, timeout=30)
            data = resp.json()

            # quota 用盡
            if data.get("status") == 402:
                wait = FINMIND_BACKOFF
                print(f"  [quota] 用盡，等待 {wait//60} 分鐘後重試...")
                time.sleep(wait)
                continue

            if data.get("status") != 200:
                print(f"  [API error] {stock_id} status={data.get('status')}")
                return pd.DataFrame()

            records = data.get("data", [])
            if not records:
                return pd.DataFrame()

            return pd.DataFrame(records)

        except requests.exceptions.Timeout:
            print(f"  [timeout] {stock_id} attempt {attempt+1}")
            time.sleep(5)
        except Exception as e:
            print(f"  [error] {stock_id}: {e}")
            return pd.DataFrame()

    return pd.DataFrame()


# 各 dataset 的「新鮮度容忍天數」：超過才做增量更新
#   交易型（每日）→ 0：cache 未含今天就補；月營收 → 20；股利/財報（季/年）→ 55
_FRESH_DAYS = {
    "price": 0, "price_adj": 0, "institutional": 0, "margin": 0,
    "revenue": 20, "dividend": 55, "financial": 55,
}


def _dedup_keys(df: pd.DataFrame) -> list:
    """時序去重鍵：以 date 為主，三大法人一天多列再加 name"""
    keys = [c for c in ["date"] if c in df.columns]
    if "name" in df.columns:
        keys.append("name")
    return keys


def _is_stale(cached: pd.DataFrame, fresh_days: int) -> bool:
    """cache 最新日期距今是否超過容忍天數"""
    if cached.empty or "date" not in cached.columns:
        return False
    try:
        last = pd.to_datetime(cached["date"]).max().date()
    except Exception:
        return False
    return (datetime.now().date() - last).days > fresh_days


def _incremental_update(stock_id: str, dataset: str, dataset_name: str,
                        cached: pd.DataFrame) -> pd.DataFrame:
    """
    增量補抓：只抓 cache 最後一天之後到今天的缺口，append 後去重存回。
    任何一步失敗（API 空、網路錯）都回傳原 cache，不讓每日流程因補抓而中斷。
    """
    try:
        last = pd.to_datetime(cached["date"]).max().date()
    except Exception:
        return cached

    start = last + timedelta(days=1)
    today = datetime.now().date()
    if start > today:
        return cached                       # cache 已含今天，不用補

    new = _fetch_from_api(dataset_name, stock_id,
                          start.isoformat(), today.isoformat())
    if new.empty:
        return cached                       # 假日/尚無新資料，保留 cache（非錯誤）

    merged = pd.concat([cached, new], ignore_index=True)
    keys = _dedup_keys(merged)
    if keys:
        merged = merged.drop_duplicates(subset=keys, keep="last")
    if "date" in merged.columns:
        merged = merged.sort_values("date").reset_index(drop=True)

    try:
        merged.to_parquet(_cache_path(stock_id, dataset), index=False)
        print(f"  [incr] {stock_id}/{dataset} +{len(merged)-len(cached)} 筆（至 {today}）")
    except Exception as e:
        print(f"  [incr] {stock_id}/{dataset} 存檔失敗（用記憶體結果）：{e}")
    return merged


def fetch_stock(stock_id: str, dataset: str = "price",
                force_refresh: bool = False) -> pd.DataFrame:
    """
    取得單一股票資料（優先從 cache 讀）

    Args:
        stock_id: 股票代號，如 "2330"
        dataset: "price" | "price_adj" | "financial" | "dividend" | "revenue"
        force_refresh: 強制重打 API（忽略 cache）

    Returns:
        DataFrame
    """
    dataset_name = DATASETS.get(dataset)
    if not dataset_name:
        raise ValueError(f"未知 dataset: {dataset}，可用: {list(DATASETS.keys())}")

    cache_path = _cache_path(stock_id, dataset)

    # 1. 已有 cache → 讀回；有 token 且已過期時做增量補抓（只補缺口，省配額）
    #    無 token（本機僅讀 cache）維持原行為：直接回 cache
    if not force_refresh and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        fresh_days = _FRESH_DAYS.get(dataset, 1)
        if FINMIND_TOKEN and _is_stale(cached, fresh_days):
            return _incremental_update(stock_id, dataset, dataset_name, cached)
        return cached

    # 2. empty marker → 跳過
    if not force_refresh and _is_empty_marked(stock_id, dataset):
        return pd.DataFrame()

    # 3. 打 API
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * CACHE_YEARS)).strftime("%Y-%m-%d")

    print(f"  [fetch] {stock_id} / {dataset} ({start_date} ~ {end_date})")
    df = _fetch_from_api(dataset_name, stock_id, start_date, end_date)

    if df.empty:
        _mark_empty(stock_id, dataset)
        return pd.DataFrame()

    # 4. 存 cache
    df.to_parquet(cache_path, index=False)
    print(f"  [cache] 已存 {cache_path} ({len(df)} 筆)")
    return df


def fetch_multiple(stock_ids: list, dataset: str = "price",
                   delay: float = 0.5) -> dict:
    """
    批次抓多支股票

    Args:
        stock_ids: 股票代號 list
        dataset: 資料集名稱
        delay: 每次 API 呼叫間隔秒數

    Returns:
        dict {stock_id: DataFrame}
    """
    result = {}
    total = len(stock_ids)
    for i, sid in enumerate(stock_ids, 1):
        print(f"[{i}/{total}] {sid}")
        df = fetch_stock(sid, dataset)
        if not df.empty:
            result[sid] = df
        time.sleep(delay)
    return result


def get_tw50_stocks() -> list:
    """
    台灣50成分股（硬編碼，定期更新）
    適合雙核心機器的預設股票池
    """
    return [
        "2330", "2317", "2454", "2382", "2412",
        "2881", "2882", "2886", "2891", "2884",
        "3711", "2308", "2303", "2002", "1301",
        "1303", "2207", "2105", "5880", "2885",
        "2892", "2883", "6505", "2609", "2615",
        "2603", "1326", "2474", "3008", "2395",
        "4938", "3045", "2357", "2353", "2379",
        "2345", "3034", "6669", "2376", "2327",
        "1590", "3017", "6415", "8046", "2408",
        "2337", "3036", "2301", "2354", "2360",
    ]


def get_mid100_stocks() -> list:
    """
    台灣中型100成分股（0051 追蹤標的；2026-11-06 名單，來源 wantgoo 0051 持股明細）
    市值第 51~150 名：文獻上籌碼/營收訊號的 alpha 主要在中型股（大型股太有效率，
    2026-11 樣本外體檢證實 TW50 內所有訊號無穩定預測力）。定期更新此名單。
    """
    return [
        "2379", "3034", "3481", "1301", "3661", "3189", "2801", "1326", "2002", "5876",
        "6770", "4938", "1101", "3044", "2313", "2409", "2376", "2404", "2615", "2207",
        "2337", "1590", "3036", "6239", "3702", "5871", "3533", "2834", "6415", "2324",
        "2356", "2618", "2912", "6213", "2347", "2609", "8996", "2377", "1605", "6805",
        "1102", "1402", "6139", "2027", "6515", "2353", "2049", "2474", "5434", "2492",
        "1504", "1560", "2812", "6257", "1519", "3706", "1476", "2610", "6919", "6531",
        "3026", "6285", "6442", "8464", "2385", "2455", "3023", "9904", "1802", "7750",
        "6409", "1513", "2354", "2105", "2542", "2633", "3006", "1717", "2451", "3005",
        "1503", "3167", "5269", "7610", "9945", "6196", "1229", "6691", "8210", "6789",
        "3030", "9910", "2467", "6949", "6526", "2646", "2838", "6781", "3532", "2645",
    ]


def get_screener_universe() -> list:
    """選股池：依 SCREENER["universe"]（"tw50" 或 "tw50+mid100"）組合，去重保序"""
    from config.settings import SCREENER
    mode = SCREENER.get("universe", "tw50")
    pool = get_tw50_stocks()
    if "mid100" in mode:
        pool += get_mid100_stocks()
    seen, out = set(), []
    for sid in pool:
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


if __name__ == "__main__":
    # 快速測試
    print("測試 fetch 台積電股價...")
    df = fetch_stock("2330", "price")
    if not df.empty:
        print(df.tail())
    else:
        print("無資料或需要設定 FINMIND_TOKEN")

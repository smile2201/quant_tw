"""
data/mops_fetcher.py
公開資訊觀測站（MOPS）內部人持股申報資料
- 董監事持股轉讓申報（t51sb05）
- 完全免費，無需帳號
- 使用 HTML 解析；失敗時回傳空 DataFrame（呼叫端給中性分）
"""
import requests
import pandas as pd
from datetime import datetime

MOPS_URL = "https://mops.twse.com.tw/mops/web/ajax_t51sb05"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (compatible; quant_tw/1.0)",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://mops.twse.com.tw/mops/web/t51sb05",
}


def _roc_year() -> str:
    """西元年轉民國年"""
    return str(datetime.now().year - 1911)


def fetch_insider_transfers(stock_id: str, months: int = 1) -> pd.DataFrame:
    """
    抓取近 N 個月的內部人持股轉讓申報

    Returns:
        DataFrame，columns: [申報人姓名, 職稱, 申報轉讓股數, 申報日期]
        失敗回傳空 DataFrame
    """
    year  = _roc_year()
    month = datetime.now().strftime("%m")

    payload = (
        f"encodeURIComponent=1&step=1&firstin=1&off=1"
        f"&keyword4=&code1=&TYPEK=&co_id={stock_id}"
        f"&year={year}&month={month}"
    )

    try:
        resp = requests.post(MOPS_URL, headers=HEADERS, data=payload, timeout=15)
        resp.raise_for_status()

        tables = pd.read_html(resp.text, encoding="utf-8")
        if not tables:
            return pd.DataFrame()

        # 找有「申報轉讓」的表格
        for t in tables:
            cols = [str(c) for c in t.columns]
            if any("股數" in c or "申報" in c for c in cols):
                df = t.copy()
                df.columns = [str(c).strip() for c in df.columns]
                return df

        return pd.DataFrame()

    except Exception as e:
        print(f"  [mops] {stock_id} 內部人申報失敗（將使用中性分）：{e}")
        return pd.DataFrame()

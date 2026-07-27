"""
notify/line_bot.py
LINE Messaging API 推播選股結果
"""
import os
import json
import glob
import requests

_NAME_MAP     = None   # {stock_id: 公司簡稱}，載入一次後快取
_INDUSTRY_MAP = None   # {stock_id: 產業名稱}

# TWSE 產業別代碼表（穩定，極少變動）
INDUSTRY_CODES = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織", "05": "電機機械",
    "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙", "10": "鋼鐵", "11": "橡膠",
    "12": "汽車", "14": "建材營造", "15": "航運", "16": "觀光餐旅", "17": "金融保險",
    "18": "貿易百貨", "19": "綜合", "20": "其他", "21": "化學", "22": "生技醫療",
    "23": "油電燃氣", "24": "半導體", "25": "電腦週邊", "26": "光電",
    "27": "通信網路", "28": "電子零組件", "29": "電子通路", "30": "資訊服務",
    "31": "其他電子",
}


def _load_company_data() -> list:
    """TWSE 公司基本資料：優先讀本地 json，沒有就打 TWSE API（免費）"""
    data = None
    local = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "twse", "*_company_info.json")), reverse=True)
    if local:
        try:
            data = json.load(open(local[0], encoding="utf-8"))
        except Exception:
            data = None

    if not data:
        try:
            resp = requests.get(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=15)
            data = resp.json()
        except Exception as e:
            print(f"[LINE] 公司資料載入失敗：{e}")
            data = []
    return data


def _load_name_map() -> dict:
    """股票代號→公司簡稱"""
    global _NAME_MAP
    if _NAME_MAP is None:
        _NAME_MAP = {
            str(row.get("公司代號", "")).strip(): str(row.get("公司簡稱", "")).strip()
            for row in _load_company_data()
        }
    return _NAME_MAP


def _load_industry_map() -> dict:
    """股票代號→產業名稱（用於集中度警示）"""
    global _INDUSTRY_MAP
    if _INDUSTRY_MAP is None:
        _INDUSTRY_MAP = {}
        for row in _load_company_data():
            sid  = str(row.get("公司代號", "")).strip()
            code = str(row.get("產業別", "")).strip().zfill(2)
            if sid and code in INDUSTRY_CODES:
                _INDUSTRY_MAP[sid] = INDUSTRY_CODES[code]
    return _INDUSTRY_MAP


def stock_label(stock_id) -> str:
    """回傳「代號 名稱」，查不到名稱就只回代號"""
    sid  = str(stock_id)
    name = _load_name_map().get(sid, "")
    return f"{sid} {name}" if name else sid

LINE_PUSH_URL      = "https://api.line.me/v2/bot/message/push"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def send(message: str) -> bool:
    """
    推播優先序：
      1. LINE_GROUP_ID 有設 → 推到群組（群組內所有人都看得到）
      2. LINE_BROADCAST=true → 廣播給所有加此官方帳號好友的人
      3. LINE_USER_ID → 推給單一使用者（原本行為）
    群組與個人可同時設定（LINE_ALSO_USER=true 時兩邊都推）
    """
    token     = os.environ.get("LINE_CHANNEL_TOKEN", "")
    group_id  = os.environ.get("LINE_GROUP_ID", "")
    user_id   = os.environ.get("LINE_USER_ID", "")
    broadcast = os.environ.get("LINE_BROADCAST", "").lower() == "true"
    also_user = os.environ.get("LINE_ALSO_USER", "").lower() == "true"

    if not token:
        print("[LINE] 未設定 LINE_CHANNEL_TOKEN，跳過推播")
        return False

    headers  = {"Authorization": f"Bearer {token}"}
    messages = [{"type": "text", "text": message}]
    ok = False

    def _push(to: str, label: str) -> bool:
        resp = requests.post(
            LINE_PUSH_URL, headers=headers,
            json={"to": to, "messages": messages}, timeout=10,
        )
        if resp.status_code == 200:
            print(f"[LINE] 推播成功（{label}）")
            return True
        print(f"[LINE] 推播失敗（{label}）：{resp.status_code} {resp.text}")
        return False

    if broadcast:
        resp = requests.post(LINE_BROADCAST_URL, headers=headers,
                             json={"messages": messages}, timeout=10)
        if resp.status_code == 200:
            print("[LINE] 廣播成功（所有好友）")
            ok = True
        else:
            print(f"[LINE] 廣播失敗：{resp.status_code} {resp.text}")

    if group_id:
        ok = _push(group_id, "群組") or ok
        if also_user and user_id:
            ok = _push(user_id, "個人") or ok
    elif not broadcast and user_id:
        ok = _push(user_id, "個人") or ok

    if not ok and not group_id and not user_id and not broadcast:
        print("[LINE] 未設定任何推播對象（LINE_GROUP_ID / LINE_USER_ID / LINE_BROADCAST）")

    return ok


def _sig(row, col) -> str:
    """安全取欄位：CSV 讀回的 NaN/'nan' 一律轉成空字串"""
    v = str(row.get(col, "") or "").strip()
    return "" if v.lower() in ("nan", "none", "無") else v


def build_message(result_df, date: str) -> str:
    strong = result_df[result_df["tier"] == "強力候選"]
    watch  = result_df[result_df["tier"] == "觀察股"]

    # 總體經濟標頭（若有）
    macro_ctx = str(result_df["macro_context"].iloc[0]) \
                if "macro_context" in result_df.columns else ""
    if macro_ctx.lower() == "nan":
        macro_ctx = ""

    lines = []
    if macro_ctx:
        lines.append(macro_ctx)

    lines += [
        f"📈 {date[:4]}/{date[4:6]}/{date[6:]} 台股選股結果",
        f"━━━━━━━━━━━━━━",
        f"💎 強力候選（{len(strong)} 檔）",
    ]

    for _, row in strong.iterrows():
        lines.append(f"\n▶ {stock_label(row['stock_id'])}  總分 {int(row['final_score'])} 分")
        chip_s = int(row.get("chip_score", 50))
        lines.append(
            f"  📊 技術{int(row['tech_score'])} 基本{int(row['fund_score'])} "
            f"事件{int(row['event_score'])} 籌碼{chip_s}"
        )
        for icon, col in [("🔔", "tech_signals"), ("🏦", "chip_signals"),
                          ("📋", "fund_signals"), ("👤", "insider_signal")]:
            v = _sig(row, col)
            if v:
                lines.append(f"  {icon} {v}")
        news_sig = _sig(row, "news_signal")
        if news_sig:
            lines.append(f"  {news_sig}")

    # 產業集中度警示（7月航運三雄同時入選的教訓：同產業齊漲齊跌）
    if len(strong) >= 2:
        ind_map = _load_industry_map()
        from collections import Counter
        inds = Counter(ind_map.get(str(s), "") for s in strong["stock_id"])
        inds.pop("", None)
        crowded = [(ind, n) for ind, n in inds.items() if n >= 2]
        for ind, n in crowded:
            lines.append(f"\n⚠️ 產業集中：{n} 檔同屬{ind}，漲跌連動高，"
                         f"建議只擇一檔，勿全押")

    lines += [
        f"\n━━━━━━━━━━━━━━",
        f"👀 觀察股（{len(watch)} 檔）",
        "  " + "、".join(stock_label(s) for s in watch["stock_id"]),
        f"\n共評估 {len(result_df)} 檔",
        f"🛑 出場紀律：-7% 停損｜+10% 保本｜+15% 起移動停損",
        f"💰 資金紀律：單筆風險 ≤ 總資金 2%（單檔部位 ≤ 28%），",
        f"    同時最多 3 檔新倉、分散不同產業",
        f"（系統每日自動追蹤，觸發會另發通知）",
        f"⚠️ 僅供參考，非投資建議",
    ]
    return "\n".join(lines)

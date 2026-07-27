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


WATCH_TOP_N = 10   # 觀察股只列分數前 N 檔，避免訊息變成一堵牆


def build_message(result_df, date: str) -> str:
    strong = result_df[result_df["tier"] == "強力候選"]
    watch  = result_df[result_df["tier"] == "觀察股"]

    # 總體經濟標頭（若有；build_context 已排成多行）
    macro_ctx = str(result_df["macro_context"].iloc[0]) \
                if "macro_context" in result_df.columns else ""
    if macro_ctx.lower() == "nan":
        macro_ctx = ""

    lines = []
    if macro_ctx:
        lines.append(macro_ctx)
        lines.append("")

    lines.append(f"📈 {date[4:6]}/{date[6:]} 選股（評估 {len(result_df)} 檔）")
    lines.append("━━━━━━━━━━━━━━")

    # ── 強力候選 ─────────────────────────────────────────────────────────
    if strong.empty:
        lines += [
            "💎 今日無強力候選",
            "（濾網收緊或分數未達標，寧缺勿濫）",
        ]
    else:
        lines.append(f"💎 強力候選（{len(strong)} 檔）")

    from config.settings import SCREENER as _SC
    stop_pct = _SC.get("position_stop_loss", -0.07)

    for _, row in strong.iterrows():
        head = f"\n▶ {stock_label(row['stock_id'])}  {int(row['final_score'])}分"
        close = row.get("close")
        try:
            close = float(close)
        except (TypeError, ValueError):
            close = 0
        if close > 0:
            head += f"｜收 {close:g}"
            lines.append(head)
            lines.append(f"  🛑 停損參考 {close * (1 + stop_pct):.1f}")
        else:
            lines.append(head)
        lines.append(
            f"  📊 技{int(row['tech_score'])} 基{int(row['fund_score'])} "
            f"事{int(row['event_score'])} 籌{int(row.get('chip_score', 50))}"
        )
        for icon, col in [("🏦", "chip_signals"), ("🔔", "tech_signals"),
                          ("📋", "fund_signals"), ("👤", "insider_signal")]:
            v = _sig(row, col)
            if v:
                lines.append(f"  {icon} {v.replace(' | ', '｜')}")
        news_sig = _sig(row, "news_signal")
        if news_sig:
            lines.append(f"  {news_sig}")

    # ── 產業集中度警示 ───────────────────────────────────────────────────
    if len(strong) >= 2:
        ind_map = _load_industry_map()
        from collections import Counter
        inds = Counter(ind_map.get(str(s), "") for s in strong["stock_id"])
        inds.pop("", None)
        for ind, n in [(i, c) for i, c in inds.items() if c >= 2]:
            lines.append(f"\n⚠️ {n} 檔同屬{ind}，連動高，建議擇一勿全押")

    # ── 觀察股：只列前 N，附分數 ─────────────────────────────────────────
    lines.append(f"\n👀 觀察股 TOP{min(WATCH_TOP_N, len(watch))}（共 {len(watch)} 檔）")
    for _, row in watch.head(WATCH_TOP_N).iterrows():
        lines.append(f"  {int(row['final_score'])}分 {stock_label(row['stock_id'])}")
    if len(watch) > WATCH_TOP_N:
        lines.append(f"  …其餘 {len(watch) - WATCH_TOP_N} 檔略")

    # ── 尾註（壓縮成三行）────────────────────────────────────────────────
    lines += [
        "━━━━━━━━━━━━━━",
        "🛑 -7%停損｜+10%保本｜+15%移動停損",
        "💰 單筆風險≤2%｜最多3檔新倉｜分散產業",
        "⚠️ 僅供參考，非投資建議",
    ]
    return "\n".join(lines)

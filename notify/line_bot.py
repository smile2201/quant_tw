"""
notify/line_bot.py
LINE Messaging API 推播選股結果
"""
import os
import json
import glob
import requests

_NAME_MAP = None   # {stock_id: 公司簡稱}，載入一次後快取


def _load_name_map() -> dict:
    """股票代號→公司簡稱。優先讀本地 TWSE json，沒有就打 TWSE API（免費）"""
    global _NAME_MAP
    if _NAME_MAP is not None:
        return _NAME_MAP

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
            print(f"[LINE] 公司名稱載入失敗（訊息只顯示代號）：{e}")
            data = []

    _NAME_MAP = {
        str(row.get("公司代號", "")).strip(): str(row.get("公司簡稱", "")).strip()
        for row in data
    }
    return _NAME_MAP


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

    lines += [
        f"\n━━━━━━━━━━━━━━",
        f"👀 觀察股（{len(watch)} 檔）",
        "  " + "、".join(stock_label(s) for s in watch["stock_id"]),
        f"\n共評估 {len(result_df)} 檔",
        f"⚠️ 僅供參考，非投資建議",
    ]
    return "\n".join(lines)

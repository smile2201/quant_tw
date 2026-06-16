"""
notify/line_bot.py
LINE Messaging API 推播選股結果
"""
import os
import requests

LINE_API_URL = "https://api.line.me/v2/bot/message/push"


def send(message: str) -> bool:
    token   = os.environ.get("LINE_CHANNEL_TOKEN", "")
    user_id = os.environ.get("LINE_USER_ID", "")
    if not token or not user_id:
        print("[LINE] 未設定 LINE_CHANNEL_TOKEN 或 LINE_USER_ID，跳過推播")
        return False

    resp = requests.post(
        LINE_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"to": user_id, "messages": [{"type": "text", "text": message}]},
        timeout=10,
    )
    if resp.status_code == 200:
        print("[LINE] 推播成功")
        return True
    else:
        print(f"[LINE] 推播失敗：{resp.status_code} {resp.text}")
        return False


def build_message(result_df, date: str) -> str:
    strong = result_df[result_df["tier"] == "強力候選"]
    watch  = result_df[result_df["tier"] == "觀察股"]

    lines = [
        f"📈 {date[:4]}/{date[4:6]}/{date[6:]} 台股選股結果",
        f"━━━━━━━━━━━━━━",
        f"💎 強力候選（{len(strong)} 檔）",
    ]
    for _, row in strong.iterrows():
        lines.append(f"\n▶ {row['stock_id']}  總分 {int(row['final_score'])} 分")
        lines.append(f"  📊 技術 {int(row['tech_score'])} | 基本 {int(row['fund_score'])} | 事件 {int(row['event_score'])}")
        if row.get("tech_signals"):
            lines.append(f"  🔔 {row['tech_signals']}")
        if row.get("fund_signals") and row["fund_signals"] != "無":
            lines.append(f"  📋 {row['fund_signals']}")

    lines += [
        f"\n━━━━━━━━━━━━━━",
        f"👀 觀察股（{len(watch)} 檔）",
        "  " + "、".join(watch["stock_id"].tolist()),
        f"\n共評估 {len(result_df)} 檔",
        f"⚠️ 僅供參考，非投資建議",
    ]
    return "\n".join(lines)

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
        f"📈 {date} 台股選股結果",
        f"━━━━━━━━━━━━━━",
        f"💎 強力候選（{len(strong)} 檔）",
    ]
    for _, row in strong.iterrows():
        lines.append(f"  {row['stock_id']}  評分 {row['final_score']}")

    lines += [
        f"",
        f"👀 觀察股（{len(watch)} 檔）",
        "  " + "、".join(watch["stock_id"].tolist()),
        f"",
        f"共評估 {len(result_df)} 檔",
    ]
    return "\n".join(lines)

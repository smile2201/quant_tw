"""
scripts/capture_line_group.py
自動抓取 LINE 群組 ID（在 GitHub Actions 執行，token 從 Secrets 來）

流程：
  1. 用 webhook.site API 建立臨時收件匣
  2. 把 LINE Bot 的 webhook 指向它
  3. 等你把 Bot 邀進群組（join 事件會帶 groupId）
  4. 抓到後「推播到該群組」告訴你 ID（公開 repo 的 log 不留任何 ID）
  5. 還原原本的 webhook 設定

注意：公開 repo 的 Actions log 人人可看，本腳本絕不 print groupId。
"""
import os
import sys
import time
import requests

LINE_TOKEN   = os.environ.get("LINE_CHANNEL_TOKEN", "")
LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
WAIT_MINUTES = int(os.environ.get("CAPTURE_WAIT_MINUTES", "30"))

LINE_HEADERS = {"Authorization": f"Bearer {LINE_TOKEN}"}
LINE_ENDPOINT_API = "https://api.line.me/v2/bot/channel/webhook/endpoint"
LINE_PUSH_API     = "https://api.line.me/v2/bot/message/push"


def push(to: str, text: str):
    requests.post(LINE_PUSH_API, headers=LINE_HEADERS,
                  json={"to": to, "messages": [{"type": "text", "text": text}]},
                  timeout=10)


def main():
    if not LINE_TOKEN:
        print("缺 LINE_CHANNEL_TOKEN")
        sys.exit(1)

    # 1. 記下原本的 webhook 設定
    orig = {}
    r = requests.get(LINE_ENDPOINT_API, headers=LINE_HEADERS, timeout=10)
    if r.status_code == 200:
        orig = r.json()
        print(f"原 webhook active={orig.get('active')}（結束後會還原網址）")

    # 2. 建臨時收件匣
    r = requests.post("https://webhook.site/token", json={}, timeout=15)
    r.raise_for_status()
    box_id  = r.json()["uuid"]
    box_url = f"https://webhook.site/{box_id}"
    print("臨時收件匣已建立")

    # 3. 指向臨時收件匣
    r = requests.put(LINE_ENDPOINT_API, headers=LINE_HEADERS,
                     json={"endpoint": box_url}, timeout=10)
    if r.status_code != 200:
        print(f"設定 webhook 失敗：{r.status_code} {r.text}")
        sys.exit(1)

    # 檢查 webhook 是否啟用
    r = requests.get(LINE_ENDPOINT_API, headers=LINE_HEADERS, timeout=10)
    active = r.status_code == 200 and r.json().get("active", False)

    if LINE_USER_ID:
        if active:
            push(LINE_USER_ID,
                 f"🤖 群組設定模式啟動（{WAIT_MINUTES}分鐘內有效）\n"
                 f"請把本機器人邀請進你的群組，\n"
                 f"完成後機器人會在群組裡回報設定資訊。")
        else:
            push(LINE_USER_ID,
                 "⚠️ 請先到 LINE Developers Console →\n"
                 "Messaging API 分頁 → 打開「Use webhook」開關，\n"
                 "然後把機器人邀請進群組。")
    print(f"等待邀請 Bot 進群組（webhook active={active}，最長 {WAIT_MINUTES} 分鐘）...")

    # 4. 輪詢收件匣找 group 事件
    group_id = None
    deadline = time.time() + WAIT_MINUTES * 60
    try:
        while time.time() < deadline:
            time.sleep(10)
            try:
                r = requests.get(
                    f"https://webhook.site/token/{box_id}/requests",
                    params={"sorting": "newest"}, timeout=15)
                for req in r.json().get("data", []):
                    content = req.get("content", "") or ""
                    if '"groupId"' in content:
                        import json as _json
                        events = _json.loads(content).get("events", [])
                        for ev in events:
                            src = ev.get("source", {})
                            if src.get("type") == "group" and src.get("groupId"):
                                group_id = src["groupId"]
                                break
                    if group_id:
                        break
            except Exception:
                pass
            if group_id:
                break
        if not group_id:
            print("時間內未收到群組事件，請重跑 workflow 再試一次")
            if LINE_USER_ID:
                push(LINE_USER_ID, "⏰ 群組設定逾時，請到 GitHub Actions 重跑 setup-line-group")
            sys.exit(2)

        # 5. 推播到群組告知 ID（log 絕不輸出）
        print("已抓到群組 ID（不顯示於 log），推播設定指示到群組...")
        push(group_id,
             f"✅ 群組連線成功！\n"
             f"━━━━━━━━━━━━━━\n"
             f"群組 ID：\n{group_id}\n"
             f"━━━━━━━━━━━━━━\n"
             f"最後一步：複製上面這串 C 開頭的 ID，\n"
             f"到 GitHub repo → Settings → Secrets and variables\n"
             f"→ Actions → New repository secret\n"
             f"名稱：LINE_GROUP_ID\n"
             f"設定完成後，之後所有選股通知都會推到這個群組 📈")

    finally:
        # 6. 還原 webhook
        restore = orig.get("endpoint", "")
        if restore and restore != box_url:
            requests.put(LINE_ENDPOINT_API, headers=LINE_HEADERS,
                         json={"endpoint": restore}, timeout=10)
            print("已還原原本的 webhook 網址")
        else:
            print("原本沒有 webhook 網址；臨時網址失效後不影響推播功能")

    print("完成")


if __name__ == "__main__":
    main()

# LINE 群組推播設定 SOP

推播優先序（程式已支援，改 GitHub Secrets 即可切換）：

| 設定 | 效果 |
|------|------|
| `LINE_GROUP_ID`（Secret） | 推到群組，群組內所有人看得到 ← **推薦** |
| `LINE_BROADCAST=true`（env） | 廣播給所有加官方帳號好友的人 |
| `LINE_USER_ID`（Secret） | 原本行為，只推給你一人 |
| `LINE_ALSO_USER=true`（Variable） | 群組+個人都推 |

---

## 取得群組 ID（一次性，約 5 分鐘）

群組 ID 只能從 webhook 事件拿到，用 webhook.site 免費服務接一次即可：

### Step 1：開臨時 webhook
1. 開 https://webhook.site → 複製你的唯一網址（`https://webhook.site/#!/xxxx...` 中的 `https://webhook.site/xxxx...`）

### Step 2：設定 LINE Bot webhook
1. 登入 https://developers.line.biz/console/
2. 選你的 Messaging API channel → **Messaging API** 分頁
3. **Webhook URL** 貼上 webhook.site 網址 → **Update** → **Verify**（顯示 Success）
4. 打開 **Use webhook** 開關

### Step 3：把 Bot 拉進群組
1. LINE 手機 App → 建立群組（或用現有群組），把要看通知的人都加進來
2. 群組設定 → 邀請 → 搜尋你的官方帳號名稱 → 邀請 Bot 進群
   - 若搜不到：LINE Official Account Manager → 設定 → 功能切換 →「加入群組」設為允許
3. 在群組裡隨便發一句話

### Step 4：抓 groupId
1. 回到 webhook.site，會看到新的 POST 請求
2. 內容裡找 `"source":{"type":"group","groupId":"Cxxxxxxxx..."}`
3. 複製 `C` 開頭那串就是群組 ID

### Step 5：設定 GitHub Secret
```bash
gh secret set LINE_GROUP_ID --repo smile2201/quant_tw
# 貼上 C 開頭的群組 ID
```
或到 GitHub repo → Settings → Secrets and variables → Actions → New repository secret

### Step 6：清理
- 回 LINE Developers Console 把 Webhook URL 清空、關掉 Use webhook（避免 webhook.site 網址過期後報錯）

---

## 驗證

手動觸發一次選股 workflow：
```bash
gh workflow run daily_screener.yml --repo smile2201/quant_tw
```
群組內所有人應該都會收到選股通知。

## 注意：免費方案訊息額度

LINE Messaging API 免費方案每月 **500 則**。推到群組算 **1 則**（不管群組幾個人），
所以群組推播比 broadcast（每個好友算 1 則）省很多。
目前每日最多：盤後 1 + 盤中 5 + 補發 1 = 7 則/日 × 22 交易日 ≈ 154 則/月，額度充足。

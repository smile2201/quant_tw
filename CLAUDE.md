# CLAUDE.md — 台股量化交易系統 AI Context

> 這份文件是給 Claude Code 看的，每次新對話自動載入。

---

## 專案概覽

**目標**：台股混合策略量化回測系統 + 每日盤後自動選股
**語言**：Python 3.11+
**執行環境**：Mac（雙核 Intel m3，8GB RAM）+ Google Colab（重量級任務）
**資料來源**：
- FinMind（歷史K線，600次/小時，帳號：Smile01）
- TWSE OpenAPI（每日重大訊息，完全免費無限制）

---

## 環境設定

### FinMind Token
```bash
export FINMIND_TOKEN="你的token"
```
Token 過期 SOP：登入 finmindtrade.com → 更新 token（橘色按鈕）→ 更新 ~/.zshrc

### 安裝套件
```bash
pip install pandas pyarrow requests finmind pytest numpy
```

---

## FinMind 雷區

- 600次/小時：初次建 cache 會超過，程式自動退避 65 分鐘後繼續
- Cache 壞掉：刪除 data/cache/[dataset]/[stock_id].parquet 重跑
- Empty marker 清除：刪除 data/empty_markers/[dataset]/[stock_id].empty

---

## 三模式

| 模式 | 滑價 | 用途 |
|------|------|------|
| ideal | 無 | 上界估計 |
| realistic | 買0.2%/賣0.3% | 主要看這個 |
| pessimistic | realistic×1.5 | 壓力測試 |

---

## 開發鐵則

1. 一次只做一件事，做完驗收再繼續
2. 遇到錯誤先讀訊息，不要直接叫我重寫
3. 新功能掛旁邊，不改舊的（並行擴充原則）
4. 每個 Playbook 完成後 git commit

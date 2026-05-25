"""
dashboard.py - 台股量化系統操作面板
本機：streamlit run dashboard.py
雲端：Streamlit Cloud 連接 GitHub repo
"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from auth.user_manager import (
    init_default_admin, verify, list_users,
    add_user, reset_password, toggle_active,
    delete_user, change_role, change_own_password,
    user_count, has_permission, ROLES,
)

st.set_page_config(page_title="台股量化系統", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

PROJECT_ROOT  = Path(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.py"
CACHE_DIR     = PROJECT_ROOT / "data" / "cache"
TWSE_DIR      = PROJECT_ROOT / "data" / "twse"
RESULTS_DIR   = PROJECT_ROOT / "results"
LOGS_DIR      = PROJECT_ROOT / "logs"
IS_CLOUD      = not os.path.exists("/Users")

init_default_admin()

# ══════════════════════════════════════════════════════════════════════════════
# 登入頁
# ══════════════════════════════════════════════════════════════════════════════
def show_login():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 📈 台股量化系統")
        st.markdown("---")
        username = st.text_input("帳號", placeholder="請輸入帳號")
        password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
        if st.button("登入", type="primary", use_container_width=True):
            user = verify(username, password)
            if user:
                st.session_state.user = user
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")
        st.caption("首次使用預設帳號：admin / admin1234（請登入後立即修改密碼）")

if "user" not in st.session_state or not st.session_state.user:
    show_login()
    st.stop()

CURRENT_USER = st.session_state.user["username"]
CURRENT_ROLE = st.session_state.user["role"]
IS_ADMIN     = CURRENT_ROLE == "admin"

# ══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 台股量化系統")
    st.caption("🌐 雲端" if IS_CLOUD else "💻 本機")
    st.markdown("---")

    # 使用者資訊
    role_label = ROLES.get(CURRENT_ROLE, CURRENT_ROLE)
    st.markdown(f"**👤 {CURRENT_USER}**")
    st.caption(f"角色：{role_label}")

    if st.button("🔒 登出", use_container_width=True):
        st.session_state.user = None
        st.rerun()

    st.markdown("---")

    # 依角色顯示不同頁面
    if IS_ADMIN:
        pages = ["🏠 今日選股", "📊 回測結果", "📁 資料狀態",
                 "⚙️ 方案設定", "▶️ 執行腳本", "📋 執行記錄",
                 "👥 帳號管理", "🔑 修改密碼"]
    else:
        pages = ["🏠 今日選股", "📊 回測結果", "🔑 修改密碼"]

    page = st.radio("導航", pages, label_visibility="collapsed")

    st.markdown("---")
    cfg_plan = "未知"
    if SETTINGS_PATH.exists():
        for line in SETTINGS_PATH.read_text().splitlines():
            if line.startswith("FINMIND_PLAN"):
                cfg_plan = line.split("=")[1].split("#")[0].strip().strip('"\'')
    st.caption(f"方案：{'💎 付費' if cfg_plan == 'sponsor' else '🆓 免費'}")

# ══════════════════════════════════════════════════════════════════════════════
# 工具函式
# ══════════════════════════════════════════════════════════════════════════════
def read_plan():
    if not SETTINGS_PATH.exists():
        return {"plan": "register", "dataset": "price", "rate_limit": 600}
    plan, dataset, rate = "register", "price", 600
    for line in SETTINGS_PATH.read_text().splitlines():
        if line.startswith("FINMIND_PLAN"):
            plan = line.split("=")[1].split("#")[0].strip().strip('"\'')
        elif line.startswith("FINMIND_PRICE_DATASET"):
            dataset = line.split("=")[1].split("#")[0].strip().strip('"\'')
        elif line.startswith("FINMIND_RATE_LIMIT"):
            try: rate = int(line.split("=")[1].split("#")[0].strip())
            except: pass
    return {"plan": plan, "dataset": dataset, "rate_limit": rate}

def write_plan(plan: str):
    vals = {
        "sponsor":  {"FINMIND_PLAN": '"sponsor"',  "FINMIND_PRICE_DATASET": '"price_adj"', "FINMIND_RATE_LIMIT": "6000"},
        "register": {"FINMIND_PLAN": '"register"', "FINMIND_PRICE_DATASET": '"price"',     "FINMIND_RATE_LIMIT": "600"},
    }[plan]
    lines = []
    for line in SETTINGS_PATH.read_text().splitlines():
        replaced = False
        for key, val in vals.items():
            if line.startswith(key):
                comment = ("  " + line[line.index("#"):]) if "#" in line else ""
                lines.append(f"{key:<24} = {val}{comment}")
                replaced = True; break
        if not replaced:
            lines.append(line)
    SETTINGS_PATH.write_text("\n".join(lines))

def get_screener_results():
    if not RESULTS_DIR.exists(): return []
    return sorted([f for f in RESULTS_DIR.glob("*screener*.csv")], reverse=True)

def get_comparison_results():
    if not RESULTS_DIR.exists(): return []
    return sorted(RESULTS_DIR.glob("*comparison*.csv"), reverse=True)

def get_logs():
    if not LOGS_DIR.exists(): return []
    return sorted(LOGS_DIR.glob("*.log"), reverse=True)[:10]

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：今日選股（所有人可看）
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 今日選股":
    st.title("🏠 今日選股結果")
    csvs = get_screener_results()
    if not csvs:
        st.warning("尚無選股結果")
        if IS_ADMIN:
            st.code("python scripts/run_screener.py", language="bash")
    else:
        dates = [f.stem.split("_")[0] for f in csvs]
        sel   = st.selectbox("選擇日期", dates)
        df    = pd.read_csv(next(f for f in csvs if f.stem.startswith(sel)))

        strong = df[df["tier"] == "強力候選"]
        watch  = df[df["tier"] == "觀察股"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("日期", sel)
        c2.metric("強力候選", f"{len(strong)} 檔")
        c3.metric("觀察股",   f"{len(watch)} 檔")
        c4.metric("評估總數", f"{len(df)} 檔")
        st.markdown("---")

        if len(strong) > 0:
            st.subheader("💎 強力候選")
            cols = [c for c in ["stock_id","final_score","tech_score","fund_score","event_score","tech_signals"] if c in df.columns]
            st.dataframe(strong[cols].reset_index(drop=True), hide_index=True, use_container_width=True)

        if len(watch) > 0:
            st.subheader("👀 觀察股")
            cols = [c for c in ["stock_id","final_score","tech_score","fund_score","tech_signals"] if c in df.columns]
            st.dataframe(watch[cols].reset_index(drop=True), hide_index=True, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 分數分布")
        score_col = "final_score" if "final_score" in df.columns else df.columns[1]
        st.bar_chart(df.set_index("stock_id")[score_col].sort_values(ascending=False))

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：回測結果（所有人可看）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 回測結果":
    st.title("📊 回測結果")
    files = list(get_comparison_results())
    if not files:
        st.info("尚無回測結果")
        if IS_ADMIN:
            st.code("python scripts/run_backtest.py", language="bash")
    else:
        sel = st.selectbox("選擇結果", [f.name for f in files])
        df  = pd.read_csv(RESULTS_DIR / sel)
        st.markdown("### 三模式比較")
        c1, c2, c3 = st.columns(3)
        labels = {"ideal":"🟢 Ideal", "realistic":"🔵 Realistic", "pessimistic":"🔴 Pessimistic"}
        for i, (_, row) in enumerate(df.iterrows()):
            with [c1,c2,c3][i]:
                st.markdown(f"**{labels.get(row.get('mode',''), row.get('mode',''))}**")
                ann = row.get("annual_return", 0)
                st.metric("年化報酬", f"{ann:.2f}%")
                st.metric("Sharpe",   f"{row.get('sharpe',0):.3f}")
                st.metric("MDD",      f"{row.get('mdd',0):.2f}%")
                st.metric("勝率",     f"{row.get('win_rate',0):.1f}%")
                st.metric("交易筆數", int(row.get("total_trades",0)))
        st.markdown("---")
        st.dataframe(df, hide_index=True, use_container_width=True)
        eq_files = sorted(RESULTS_DIR.glob("*equity_realistic*.csv"), reverse=True)
        if eq_files:
            st.markdown("### Realistic Equity Curve")
            st.line_chart(pd.read_csv(eq_files[0], index_col=0))

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：資料狀態（管理員）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📁 資料狀態":
    if not IS_ADMIN:
        st.error("權限不足"); st.stop()
    st.title("📁 資料狀態")
    cache_stats = {}
    if CACHE_DIR.exists():
        cache_stats = {d.name: len(list(d.glob("*.parquet")))
                       for d in sorted(CACHE_DIR.iterdir()) if d.is_dir()}
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("📦 FinMind Cache")
        if cache_stats:
            for ds, cnt in cache_stats.items():
                st.progress(min(cnt/50, 1.0), text=f"{ds}：{cnt} 檔")
        else:
            st.warning("尚無 cache")
    with col_r:
        st.subheader("📰 TWSE 資料")
        if TWSE_DIR.exists():
            files = [{"檔案": f.name, "大小": f"{f.stat().st_size/1024:.1f} KB"}
                     for f in sorted(TWSE_DIR.glob("*.json"), reverse=True)[:8]]
            if files:
                st.dataframe(pd.DataFrame(files), hide_index=True, use_container_width=True)
    if cache_stats and not IS_CLOUD:
        st.markdown("---")
        st.subheader("🧹 清除 Cache")
        ds_sel = st.selectbox("選擇資料集", list(cache_stats.keys()))
        if st.button("🗑️ 清除", type="secondary"):
            import shutil
            t = CACHE_DIR / ds_sel; shutil.rmtree(t); t.mkdir()
            st.success(f"已清除 {ds_sel}"); st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：方案設定（管理員）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ 方案設定":
    if not IS_ADMIN:
        st.error("權限不足"); st.stop()
    st.title("⚙️ FinMind 方案設定")
    cfg = read_plan()
    c1, c2, c3 = st.columns(3)
    c1.metric("方案", cfg["plan"])
    c2.metric("資料集", cfg["dataset"])
    c3.metric("速率上限", f"{cfg['rate_limit']} 次/hr")
    st.markdown("---")
    if IS_CLOUD:
        st.info("雲端模式請直接修改 config/settings.py 後推送到 GitHub")
    else:
        tab_free, tab_paid = st.tabs(["🆓 免費方案", "💎 付費方案"])
        with tab_free:
            st.markdown("`price`（未還原）｜600次/hr｜**免費**")
            if cfg["plan"] != "register":
                if st.button("切換到免費方案", type="secondary", use_container_width=True):
                    write_plan("register"); st.success("已切換"); st.rerun()
            else:
                st.success("✅ 目前使用中")
        with tab_paid:
            st.markdown("`price_adj`（還原股價）｜6000次/hr｜需贊助 FinMind")
            if cfg["plan"] != "sponsor":
                if st.button("切換到付費方案", type="primary", use_container_width=True):
                    write_plan("sponsor"); st.success("已切換"); st.rerun()
            else:
                st.success("✅ 目前使用中")
    token = os.environ.get("FINMIND_TOKEN", "")
    st.markdown("---")
    st.subheader("Token 狀態")
    st.success(f"✅ 已設定（{token[:8]}...）") if token else st.error("❌ 未設定")

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：執行腳本（管理員）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "▶️ 執行腳本":
    if not IS_ADMIN:
        st.error("權限不足"); st.stop()
    st.title("▶️ 執行腳本")
    if IS_CLOUD:
        st.info("雲端模式由 GitHub Actions 自動執行")
        st.markdown("請到 GitHub repo → Actions 查看執行記錄")
    else:
        scripts = {
            "🔄 更新資料": "scripts/update_cache.py",
            "🔍 選股評分": "scripts/run_screener.py",
            "📊 三模式回測": "scripts/run_backtest.py",
        }
        sel  = st.selectbox("選擇腳本", list(scripts.keys()))
        path = scripts[sel]
        st.code(f"python3 {path}", language="bash")
        if st.button(f"執行 {sel}", type="primary", use_container_width=True):
            with st.spinner("執行中..."):
                r = subprocess.run(["python3", path], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                st.success("執行完成")
                st.text_area("輸出", r.stdout, height=300)
            else:
                st.error("執行失敗")
                st.text_area("錯誤", r.stderr, height=200)

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：執行記錄（管理員）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 執行記錄":
    if not IS_ADMIN:
        st.error("權限不足"); st.stop()
    st.title("📋 執行記錄")
    logs = get_logs()
    if not logs:
        st.info("尚無執行記錄")
    else:
        sel     = st.selectbox("選擇記錄", [f.name for f in logs])
        content = (LOGS_DIR / sel).read_text(encoding="utf-8", errors="replace")
        errors  = [l for l in content.splitlines() if "Error" in l or "錯誤" in l]
        if errors:
            st.error(f"發現 {len(errors)} 個錯誤")
            for e in errors[:3]: st.code(e)
        else:
            st.success("執行正常")
        st.text_area("記錄內容", content, height=400)

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：帳號管理（管理員）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👥 帳號管理":
    if not IS_ADMIN:
        st.error("權限不足"); st.stop()
    st.title("👥 帳號管理")

    # ── 帳號列表 ────────────────────────────────────────────────────────────
    st.subheader("目前帳號")
    users = list_users()
    if users:
        df = pd.DataFrame(users)[["帳號","角色","狀態","建立時間","最後登入"]]
        st.dataframe(df, hide_index=True, use_container_width=True)
    st.markdown(f"共 **{user_count()}** 個帳號")

    st.markdown("---")

    # ── 帳號操作 ────────────────────────────────────────────────────────────
    tab_add, tab_edit, tab_pwd = st.tabs(["➕ 新增帳號", "✏️ 編輯帳號", "🔑 重設密碼"])

    with tab_add:
        st.markdown("#### 新增帳號")
        col1, col2 = st.columns(2)
        new_user = col1.text_input("帳號", placeholder="至少 3 個字元")
        new_pwd  = col2.text_input("密碼", type="password", placeholder="至少 6 個字元")
        new_role = st.selectbox("角色", options=list(ROLES.keys()),
                                format_func=lambda x: f"{x}（{ROLES[x]}）")
        st.caption({
            "admin":  "管理員：可看所有頁面、執行腳本、管理帳號",
            "viewer": "瀏覽者：只能看今日選股和回測結果",
        }.get(new_role, ""))

        if st.button("新增", type="primary"):
            ok, msg = add_user(new_user, new_pwd, new_role)
            st.success(msg) if ok else st.error(msg)
            if ok: st.rerun()

    with tab_edit:
        st.markdown("#### 編輯帳號")
        other_users = [u["帳號"] for u in users if u["帳號"] != CURRENT_USER]
        if not other_users:
            st.info("沒有其他帳號可編輯")
        else:
            sel_user = st.selectbox("選擇帳號", other_users)
            sel_info = next((u for u in users if u["帳號"] == sel_user), {})

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**變更角色**")
                cur_role = sel_info.get("role", "viewer")
                new_role_sel = st.selectbox("新角色", list(ROLES.keys()),
                                            index=list(ROLES.keys()).index(cur_role),
                                            format_func=lambda x: ROLES[x],
                                            key="role_sel")
                if st.button("變更角色", use_container_width=True):
                    ok, msg = change_role(sel_user, new_role_sel, CURRENT_USER)
                    st.success(msg) if ok else st.error(msg)
                    if ok: st.rerun()

            with col2:
                st.markdown("**啟用 / 停用**")
                is_active = sel_info.get("active", True)
                btn_label = "🔴 停用帳號" if is_active else "✅ 啟用帳號"
                btn_type  = "secondary" if is_active else "primary"
                st.write(f"目前：{'✅ 啟用' if is_active else '🔴 停用'}")
                if st.button(btn_label, type=btn_type, use_container_width=True):
                    ok, msg = toggle_active(sel_user, CURRENT_USER)
                    st.success(msg) if ok else st.error(msg)
                    if ok: st.rerun()

            with col3:
                st.markdown("**刪除帳號**")
                st.write("⚠️ 刪除後無法復原")
                if st.button("🗑️ 刪除帳號", type="secondary", use_container_width=True):
                    ok, msg = delete_user(sel_user, CURRENT_USER)
                    st.success(msg) if ok else st.error(msg)
                    if ok: st.rerun()

    with tab_pwd:
        st.markdown("#### 重設其他帳號密碼")
        all_others = [u["帳號"] for u in users if u["帳號"] != CURRENT_USER]
        if not all_others:
            st.info("沒有其他帳號")
        else:
            sel_for_pwd = st.selectbox("選擇帳號", all_others, key="pwd_sel")
            new_pwd_reset = st.text_input("新密碼", type="password",
                                          placeholder="至少 6 個字元", key="new_pwd_reset")
            if st.button("重設密碼", type="primary"):
                ok, msg = reset_password(sel_for_pwd, new_pwd_reset)
                st.success(msg) if ok else st.error(msg)

# ══════════════════════════════════════════════════════════════════════════════
# 頁面：修改密碼（所有人）
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔑 修改密碼":
    st.title("🔑 修改密碼")
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown(f"帳號：**{CURRENT_USER}**")
        st.markdown("---")
        old_pwd  = st.text_input("目前密碼", type="password")
        new_pwd1 = st.text_input("新密碼", type="password", placeholder="至少 6 個字元")
        new_pwd2 = st.text_input("確認新密碼", type="password")

        if st.button("確認修改", type="primary", use_container_width=True):
            if new_pwd1 != new_pwd2:
                st.error("兩次輸入的新密碼不一致")
            else:
                ok, msg = change_own_password(CURRENT_USER, old_pwd, new_pwd1)
                st.success(msg) if ok else st.error(msg)
                if ok:
                    st.info("密碼已修改，請重新登入")
                    st.session_state.user = None
                    st.rerun()

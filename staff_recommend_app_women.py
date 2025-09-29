
import streamlit as st
from datetime import date, timedelta

# ---------- Page config (App icon will be provided post-deploy) ----------
st.set_page_config(
    page_title="and st 女生組",
    page_icon="icon.png",
    layout="wide",
)

# ---------- Helpers: ISO week ----------
def iso_year_week(d: date):
    iso_year, iso_week, _ = d.isocalendar()
    return iso_year, iso_week

# ---------- Session State Init ----------
if "weekly_targets" not in st.session_state:
    # {(year, week): target_int}
    st.session_state.weekly_targets = {}

if "records" not in st.session_state:
    # Minimal local memory dataset for women team, in case you want to log counts too.
    # Each record: {"date": date, "staff": str, "new": int, "exist": int, "line": int}
    st.session_state.records = []

# ---------- Sidebar ----------
st.sidebar.title("and st 女生組")
st.sidebar.caption("週目標設定＋桌面縮圖（已設定 icon.png）")

# ---------- Tabs ----------
tab1, tab2, tab3 = st.tabs(["📌 週目標設定", "📈 當週達成率", "📝 測試紀錄（可選）"])

# ---------- Tab 1: 週目標設定 ----------
with tab1:
    st.subheader("週目標設定（Local Memory）")
    target_date = st.date_input("選擇任意一日（用來判定週數）", value=date.today())
    y, w = iso_year_week(target_date)
    st.write(f"ISO 週：**{y} 年 第 {w} 週**")

    current_target = st.session_state.weekly_targets.get((y, w), 0)
    new_target = st.number_input("本週目標（件）", min_value=0, step=1, value=int(current_target))
    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("💾 儲存 / 更新本週目標"):
            st.session_state.weekly_targets[(y, w)] = int(new_target)
            st.success(f"已更新 {y} 年 第 {w} 週 的目標為 {int(new_target)} 件")
    with colB:
        if st.button("🗑️ 清除本週目標"):
            if (y, w) in st.session_state.weekly_targets:
                del st.session_state.weekly_targets[(y, w)]
                st.warning(f"已清除 {y} 年 第 {w} 週 的目標")
            else:
                st.info("本週尚未設定目標")

    if st.session_state.weekly_targets:
        st.divider()
        st.markdown("#### 目前已設定的週目標")
        rows = []
        for (yy, ww), tgt in sorted(st.session_state.weekly_targets.items()):
            rows.append(f"- **{yy} 年 第 {ww} 週**：{tgt} 件")
        st.markdown("\\n".join(rows))

# ---------- Utility: 計算某週的實績（合計件數） ----------
def weekly_total_for(d: date) -> int:
    # 如果你已有正式的資料來源，可以在此替換/串接。
    # 這裡先以 st.session_state.records 為示範：
    yy, ww = iso_year_week(d)
    total = 0
    for rec in st.session_state.records:
        ryy, rww = iso_year_week(rec["date"])
        if (ryy, rww) == (yy, ww):
            total += int(rec.get("new", 0)) + int(rec.get("exist", 0)) + int(rec.get("line", 0))
    return total

# ---------- Tab 2: 當週達成率 ----------
with tab2:
    st.subheader("當週達成率")
    today = date.today()
    y2, w2 = iso_year_week(today)
    tgt = st.session_state.weekly_targets.get((y2, w2), 0)
    actual = weekly_total_for(today)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("本週目標", f"{tgt} 件")
    with col2:
        st.metric("本週實績", f"{actual} 件")
    with col3:
        if tgt > 0:
            rate = actual / tgt * 100
        else:
            rate = 0.0
        st.metric("達成率", f"{rate:.1f}%")

    st.caption("※ 週的判定採用 ISO 週（週一開始）。")

# ---------- Tab 3: 測試紀錄（可選） ----------
# 若你想在女生組 app 端也暫存紀錄以測試『達成率』，可用這頁面新增測試資料。
with tab3:
    st.subheader("測試紀錄（僅本地記憶體）")
    c1, c2 = st.columns([1, 1])
    with c1:
        rec_date = st.date_input("日期", value=date.today(), key="rec_date")
        staff = st.text_input("員工姓名", value="", placeholder="例：山田")
    with c2:
        new_cnt = st.number_input("新規（App）件數", min_value=0, step=1, value=0)
        exist_cnt = st.number_input("既存（App）件數", min_value=0, step=1, value=0)
        line_cnt = st.number_input("LINE 件數", min_value=0, step=1, value=0)

    if st.button("➕ 新增一筆測試紀錄"):
        st.session_state.records.append({
            "date": rec_date,
            "staff": staff.strip(),
            "new": int(new_cnt),
            "exist": int(exist_cnt),
            "line": int(line_cnt),
        })
        st.success("已新增一筆測試紀錄")

    if st.session_state.records:
        st.divider()
        st.markdown("#### 當前測試紀錄")
        # 簡易表格
        import pandas as pd
        df = pd.DataFrame([
            {
                "日期": r["date"],
                "員工": r["staff"],
                "新規": r["new"],
                "既存": r["exist"],
                "LINE": r["line"],
                "合計": int(r["new"]) + int(r["exist"]) + int(r["line"]),
                "ISO週": f"{iso_year_week(r['date'])[0]}-{iso_year_week(r['date'])[1]}",
            }
            for r in st.session_state.records
        ])
        st.dataframe(df, use_container_width=True)
        st.caption("※ 這些是為了驗證『週達成率』而設的本地暫存資料。實際部署請串接正式資料來源。")

st.info("✅ 已啟用：1) 週目標設定（Local Memory）  2) 桌面縮圖（icon.png）")

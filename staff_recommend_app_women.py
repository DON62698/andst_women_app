
import streamlit as st
import pandas as pd
from datetime import date, datetime
import calendar

# ---- External backends ----
# These functions exist in your bundled modules.
try:
    from db_gsheets import (
        init_db,
        init_target_table,
        load_all_records,
        insert_or_update_record,
        set_target,
        get_target,
    )
    from data_management import show_data_management
    GSHEETS_AVAILABLE = True
except Exception:
    GSHEETS_AVAILABLE = False

# ---- Page config ----
st.set_page_config(page_title="and st 女生組", page_icon="icon.png", layout="wide")

# ---- Utilities ----
def ymd(d: date) -> str:
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")

def current_year_month(d: date | None = None) -> str:
    d = d or date.today()
    return d.strftime("%Y-%m")

def ensure_dataframe(records) -> pd.DataFrame:
    """Ensure records (list[dict]) -> DataFrame with typed columns."""
    if not records:
        return pd.DataFrame(columns=["date", "name", "type", "count"])
    df = pd.DataFrame(records).copy()
    # normalize columns
    for col in ["date", "name", "type", "count"]:
        if col not in df.columns:
            df[col] = None
    # parse date
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except Exception:
        pass
    # enforce dtypes
    df["name"] = df["name"].astype(str)
    df["type"] = df["type"].astype(str)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return df[(pd.to_datetime(df["date"]).dt.strftime("%Y-%m") == ym)].copy()

def week_of(d: date) -> tuple[int, int]:
    y, w, _ = d.isocalendar()
    return int(y), int(w)

def get_target_safe(ym: str, t: str) -> int:
    """Wrap db get_target -> int, default 0 if missing or backend not ready."""
    if not GSHEETS_AVAILABLE:
        return 0
    try:
        val = get_target(ym, t)
        return int(val) if val is not None and str(val).strip() != "" else 0
    except Exception:
        return 0

# ---- Cached data loader ----
@st.cache_data(show_spinner=False)
def load_all_records_cached():
    if not GSHEETS_AVAILABLE:
        return []
    try:
        return load_all_records()
    except Exception:
        return []

# ---- Init backend (graceful) ----
@st.cache_resource
def _init_once():
    """Init Google Sheets tables if secrets are configured; otherwise local-only mode."""
    if not GSHEETS_AVAILABLE:
        st.warning("Google Sheets バックエンドが読み込めませんでした。ローカル機能のみ有効です。")
        return False
    try:
        # If secrets are set, this will succeed.
        init_db()
        init_target_table()
        return True
    except Exception:
        st.warning("Google Sheets の設定が見つからないため、ローカル機能のみ有効です。")
        return False

BACKEND_OK = _init_once()

# ---- Sidebar status ----
with st.sidebar:
    st.markdown("### 接続状態")
    st.write("Google Sheets:", "✅" if BACKEND_OK else "❌")
    if BACKEND_OK:
        st.caption("目標（月）の保存・データ読込が有効")
    else:
        st.caption("登錄は動作しますが、月目標や記録の永続化は無効の場合があります。")

# ---- Load initial data and names ----
if "data" not in st.session_state:
    st.session_state.data = load_all_records_cached()

if "names" not in st.session_state:
    # 現有資料中的姓名清單
    df0 = ensure_dataframe(st.session_state.data)
    st.session_state.names = sorted(df0["name"].dropna().unique().tolist())

# ---- Tabs ----
tab_reg, tab_app_ana, tab_survey_ana, tab_manage = st.tabs(["件数登録", "and st 分析", "アンケート分析", "データ管理"])

# =============================
# 件数登録（統合フォーム + 達成率）
# =============================
with tab_reg:
    st.subheader("件数登録（and st / アンケート）")
    with st.form("unified_form"):
        c1, c2 = st.columns([2, 1])
        with c1:
            existing_names = st.session_state.names
            if existing_names:
                name_select = st.selectbox("スタッフ名（選択）", options=existing_names, index=0, key="reg_name_select")
                st.caption("未登録の場合は下で新規入力")
            else:
                name_select = ""
                st.info("登録済みの名前がありません。下で新規入力してください。")
            name_new = st.text_input("スタッフ名（新規入力）", key="reg_name_text").strip()
            name = name_new or name_select
        with c2:
            d = st.date_input("日付", value=date.today(), key="reg_date")

        st.markdown("#### 件数（and st）")
        colA, colB, colC = st.columns(3)
        with colA:
            new_cnt   = st.number_input("新規", min_value=0, step=1, value=0, key="reg_new")
        with colB:
            exist_cnt = st.number_input("既存", min_value=0, step=1, value=0, key="reg_exist")
        with colC:
            line_cnt  = st.number_input("LINE",  min_value=0, step=1, value=0, key="reg_line")

        st.markdown("#### 件数（アンケート）")
        survey_cnt = st.number_input("アンケート", min_value=0, step=1, value=0, key="reg_survey")

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                total = int(new_cnt) + int(exist_cnt) + int(line_cnt) + int(survey_cnt)
                try:
                    if total == 0:
                        # 名前だけ登録
                        if name and name not in st.session_state.names:
                            st.session_state.names.append(name)
                            st.session_state.names.sort()
                        st.info("名前を登録しました。（件数は 0 ）")
                    else:
                        if new_cnt   > 0: insert_or_update_record(ymd(d), name, "new",    int(new_cnt))
                        if exist_cnt > 0: insert_or_update_record(ymd(d), name, "exist",  int(exist_cnt))
                        if line_cnt  > 0: insert_or_update_record(ymd(d), name, "line",   int(line_cnt))
                        if survey_cnt> 0: insert_or_update_record(ymd(d), name, "survey", int(survey_cnt))

                        st.session_state.data = load_all_records_cached()
                        # refresh names
                        df0 = ensure_dataframe(st.session_state.data)
                        st.session_state.names = sorted(df0["name"].dropna().unique().tolist())
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存に失敗しました: {e}")

    st.divider()
    st.subheader("達成率（週 / 月）")

    # データ
    df_all = ensure_dataframe(st.session_state.get("data", []))
    ym = current_year_month()
    y, w = week_of(date.today())

    # 週目標（ローカル保存）
    if "weekly_targets_app" not in st.session_state:
        st.session_state.weekly_targets_app = {}   # {(y,w): int}
    if "weekly_targets_survey" not in st.session_state:
        st.session_state.weekly_targets_survey = {}

    colW, colM = st.columns(2)

    with colW:
        st.markdown("#### 週目標（今週）")
        t_app_w = int(st.session_state.weekly_targets_app.get((y, w), 0))
        t_sur_w = int(st.session_state.weekly_targets_survey.get((y, w), 0))
        t_app_w_new = st.number_input("and st（週）", min_value=0, step=1, value=t_app_w, key=f"wk_app_{y}_{w}")
        t_sur_w_new = st.number_input("アンケート（週）", min_value=0, step=1, value=t_sur_w, key=f"wk_survey_{y}_{w}")
        if st.button("週目標を保存", key=f"save_wk_{y}_{w}"):
            st.session_state.weekly_targets_app[(y, w)] = int(t_app_w_new)
            st.session_state.weekly_targets_survey[(y, w)] = int(t_sur_w_new)
            st.success("今週の目標を保存しました。")

    with colM:
        st.markdown(f"#### 月目標（{ym}）")
        t_app_m = get_target_safe(ym, "app")
        t_sur_m = get_target_safe(ym, "survey")
        t_app_m_new = st.number_input("and st（月）", min_value=0, step=1, value=int(t_app_m), key=f"mon_app_{ym}")
        t_sur_m_new = st.number_input("アンケート（月）", min_value=0, step=1, value=int(t_sur_m), key=f"mon_survey_{ym}")
        if st.button("月目標を保存", key=f"save_mon_{ym}"):
            try:
                set_target(ym, "app", int(t_app_m_new))
                set_target(ym, "survey", int(t_sur_m_new))
                # 無限ループを避けるため cache は次回自動更新でOK
                st.success("月目標を保存しました。")
            except Exception as e:
                st.error(f"月目標の保存に失敗しました: {e}")

    # 実績集計（今週 / 今月、and st / アンケート）
    def is_this_week(d0: date) -> bool:
        yy, ww, _ = datetime(d0.year, d0.month, d0.day).isocalendar()
        return (yy, ww) == (y, w)

    week_app = week_survey = month_app = month_survey = 0
    if not df_all.empty:
        df_week = df_all[df_all["date"].apply(is_this_week)]
        week_app = int(df_week[df_week["type"].isin(["new", "exist", "line"])]["count"].sum())
        week_survey = int(df_week[df_week["type"] == "survey"]["count"].sum())

        df_m = month_filter(df_all, ym)
        month_app = int(df_m[df_m["type"].isin(["new", "exist", "line"])]["count"].sum())
        month_survey = int(df_m[df_m["type"] == "survey"]["count"].sum())

    tgt_app_w = int(st.session_state.weekly_targets_app.get((y, w), 0))
    tgt_sur_w = int(st.session_state.weekly_targets_survey.get((y, w), 0))
    tgt_app_m = get_target_safe(ym, "app")
    tgt_sur_m = get_target_safe(ym, "survey")

    def pct(a, b):
        return (a / b * 100.0) if b and b > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("and st（週）実績", f"{week_app} 件")
    with c2: st.metric("and st（週）目標", f"{tgt_app_w} 件")
    with c3: st.metric("and st（月）実績", f"{month_app} 件")
    with c4: st.metric("and st（月）目標", f"{tgt_app_m} 件")

    c5, c6, c7, c8 = st.columns(4)
    with c5: st.metric("アンケート（週）実績", f"{week_survey} 件")
    with c6: st.metric("アンケート（週）目標", f"{tgt_sur_w} 件")
    with c7: st.metric("アンケート（月）実績", f"{month_survey} 件")
    with c8: st.metric("アンケート（月）目標", f"{tgt_sur_m} 件")

    st.caption(f"and st（週） 達成率：{pct(week_app, tgt_app_w):.1f}% ／ 月：{pct(month_app, tgt_app_m):.1f}%")
    st.caption(f"アンケート（週） 達成率：{pct(week_survey, tgt_sur_w):.1f}% ／ 月：{pct(month_survey, tgt_sur_m):.1f}%")

# =============================
# 分析共通関数
# =============================
def show_statistics(category: str, label: str):
    """
    category: "app" or "survey"
    label: 見出し名
    """
    st.subheader(label)
    df = ensure_dataframe(st.session_state.get("data", []))
    if df.empty:
        st.info("データがありません。")
        return

    if category == "app":
        df_cat = df[df["type"].isin(["new", "exist", "line"])].copy()
    else:
        df_cat = df[df["type"] == "survey"].copy()

    # 週別合計
    st.markdown("#### 週別合計")
    if not df_cat.empty:
        wdf = pd.DataFrame({
            "week": pd.to_datetime(df_cat["date"]).dt.isocalendar().week,
            "year": pd.to_datetime(df_cat["date"]).dt.isocalendar().year,
            "count": df_cat["count"].values,
        })
        wdf["year_week"] = wdf["year"].astype(str) + "-W" + wdf["week"].astype(str)
        g = wdf.groupby("year_week", as_index=False)["count"].sum()
        st.bar_chart(g.set_index("year_week"))

    # 構成比（and st のみ）
    if category == "app":
        st.markdown("#### 構成比（新規・既存・LINE）")
        comp = df_cat.groupby("type", as_index=False)["count"].sum()
        comp = comp.rename(columns={"type": "タイプ", "count": "件数"})
        st.dataframe(comp, use_container_width=True)

    # スタッフ別 合計
    st.markdown("#### スタッフ別 合計")
    by_staff = df_cat.groupby("name", as_index=False)["count"].sum().sort_values("count", ascending=False)
    by_staff = by_staff.rename(columns={"name": "スタッフ", "count": "件数"})
    st.bar_chart(by_staff.set_index("スタッフ"))

    # 月別累計（年次）
    st.markdown("#### 月別累計（年次）")
    mdf = pd.DataFrame({
        "ym": pd.to_datetime(df_cat["date"]).dt.strftime("%Y-%m"),
        "count": df_cat["count"].values,
    })
    mg = mdf.groupby("ym", as_index=False)["count"].sum()
    st.line_chart(mg.set_index("ym"))

# =============================
# and st 分析
# =============================
with tab_app_ana:
    show_statistics("app", "and st 分析")

# =============================
# アンケート分析
# =============================
with tab_survey_ana:
    show_statistics("survey", "アンケート分析")

# =============================
# データ管理
# =============================
with tab_manage:
    try:
        show_data_management()
    except Exception as e:
        st.error(f"データ管理画面の読み込みに失敗しました: {e}")

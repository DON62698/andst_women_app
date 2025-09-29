import streamlit as st
import pandas as pd
from datetime import date
import matplotlib.pyplot as plt

# --- 強制載入專案內的日文字型（避免標題/括號/年 亂碼） ---
import os
from matplotlib import font_manager, rcParams

JP_FONT_READY = False
try:
    # 依你的專案結構放置字型：andst_staff_recommend/fonts/NotoSansJP-Regular.otf
    font_path = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansJP-Regular.otf")
    font_manager.fontManager.addfont(font_path)
    _prop = font_manager.FontProperties(fname=font_path)
    rcParams["font.family"] = _prop.get_name()
    JP_FONT_READY = True
except Exception:
    JP_FONT_READY = False  # 找不到字型檔就維持 False

# 若專案沒放字型，再嘗試系統已裝字型（雲端環境常常沒有）
if not JP_FONT_READY:
    _JP_FONT_CANDIDATES = [
        "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAexGothic",
        "TakaoGothic", "Yu Gothic", "Hiragino Sans", "Meiryo", "MS Gothic",
        "PingFang TC", "PingFang SC", "Heiti TC", "Heiti SC"
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for _name in _JP_FONT_CANDIDATES:
        if _name in available:
            rcParams["font.family"] = _name
            JP_FONT_READY = True
            break

rcParams["axes.unicode_minus"] = False  # 避免負號亂碼

# ✅ Google Sheets 後端
from db_gsheets import (
    init_db,
    init_target_table,
    load_all_records,
    insert_or_update_record,
    get_target,
    set_target,
)

# ✅ 資料管理頁
from data_management import show_data_management


# -----------------------------
# Cache / 初始化（避免每次互動都狂打 API）
# -----------------------------
@st.cache_resource
def _init_once():
    init_db()
    init_target_table()
    return True

@st.cache_data(ttl=60)
def load_all_records_cached():
    return load_all_records()

@st.cache_data(ttl=60)
def get_target_safe(month: str, category: str) -> int:
    try:
        return get_target(month, category)
    except Exception:
        return 0


# -----------------------------
# 共用工具
# -----------------------------
def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def current_year_month() -> str:
    return date.today().strftime("%Y-%m")

def ensure_dataframe(records) -> pd.DataFrame:
    df = pd.DataFrame(records or [])
    for col in ["date", "name", "type", "count"]:
        if col not in df.columns:
            df[col] = None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    return df

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if "date" not in df.columns:
        return df.iloc[0:0]
    return df[(df["date"].dt.strftime("%Y-%m") == ym)]

def names_from_records(records) -> list[str]:
    return sorted({(r.get("name") or "").strip() for r in (records or []) if r.get("name")})

# ---- 年份 / 週處理 ----
def year_options(df: pd.DataFrame) -> list[int]:
    if "date" not in df.columns or df["date"].isna().all():
        return [date.today().year]
    years = sorted(set(df["date"].dropna().dt.year.astype(int).tolist()))
    if not years:
        years = [date.today().year]
    return years

def _week_num_to_label(w: int) -> str:
    w = int(w); w_display = ((w - 1) % 52) + 1
    return f"w{w_display}"

def _labels_for_weeks(weeks: list[int]) -> list[str]:
    return sorted({_week_num_to_label(w) for w in weeks}, key=lambda s: int(s[1:]))

def _actual_weeks_for_label(df_year: pd.DataFrame, label: str) -> list[int]:
    if "date" not in df_year.columns or df_year.empty:
        return []
    iso_weeks = sorted(set(df_year["date"].dt.isocalendar().week.astype(int).tolist()))
    want = int(label.lower().lstrip("w"))
    return [w for w in iso_weeks if int(_week_num_to_label(w)[1:]) == want]

# ---- 期間選項 / 過濾 ----
def _period_options(df: pd.DataFrame, mode: str, selected_year: int):
    if "date" not in df.columns or df["date"].isna().all():
        today = date.today()
        if mode == "週（単週）":
            return [f"w{today.isocalendar().week if today.isocalendar().week <= 52 else 1}"], f"w{today.isocalendar().week if today.isocalendar().week <= 52 else 1}"
        elif mode == "月（単月）":
            dft = today.strftime("%Y-%m"); return [dft], dft
        else:
            return [today.year], today.year

    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        weeks = sorted(set(dyear["date"].dt.isocalendar().week.astype(int).tolist()))
        labels = _labels_for_weeks(weeks) or ["w1"]
        today_w = date.today().isocalendar().week
        default = f"w{today_w if today_w <= 52 else 1}"
        if default not in labels: default = labels[0]
        return labels, default
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        months = sorted(set(dyear["date"].dt.strftime("%Y-%m").tolist()))
        if not months: months = [f"{selected_year}-01"]
        default = date.today().strftime("%Y-%m") if date.today().year == int(selected_year) else months[-1]
        if default not in months: default = months[0]
        return months, default
    else:  # 年（単年）
        ys = year_options(dfx)
        default = date.today().year if date.today().year in ys else ys[-1]
        return ys, default

def _filter_by_period(df: pd.DataFrame, mode: str, value, selected_year: int) -> pd.DataFrame:
    if "date" not in df.columns or df["date"].isna().all():
        return df.iloc[0:0]
    dfx = df.dropna(subset=["date"]).copy()
    if mode == "週（単週）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        weeks = _actual_weeks_for_label(dyear, str(value))
        if not weeks: return dyear.iloc[0:0]
        return dyear[dyear["date"].dt.isocalendar().week.isin(weeks)]
    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        return dyear[dyear["date"].dt.strftime("%Y-%m") == str(value)]
    else:
        return dfx[dfx["date"].dt.year == int(selected_year)]


# -----------------------------
# Session 初始化
# -----------------------------
def init_session():
    if "data" not in st.session_state:
        st.session_state.data = load_all_records_cached()
    if "names" not in st.session_state:
        st.session_state.names = names_from_records(st.session_state.data)
    if "app_target" not in st.session_state:
        st.session_state.app_target = 0
    if "survey_target" not in st.session_state:
        st.session_state.survey_target = 0

# ✅ 只做一次外部初始化
_init_once()
# ✅ 每次 rerun 都整理好 UI 狀態
init_session()

def render_refresh_button(btn_key: str = "refresh_btn"):
    # 右側窄欄，讓按鈕看起來在右下角
    spacer, right = st.columns([12, 1])
    with right:
        if st.button("↻", key=btn_key, help="重新整理資料"):
            load_all_records_cached.clear()
            st.session_state.data = load_all_records_cached()
            st.rerun()


# -----------------------------
# 版頭
# -----------------------------
st.title("and st 統計記録 Team Men's")

tab1, tab2, tab3 = st.tabs(["APP推薦紀錄", "アンケート紀錄", "データ管理"])

# -----------------------------
# 統計區塊（含 構成比 + スタッフ別 合計 + 週別合計 + 月別累計）
# -----------------------------
def show_statistics(category: str, label: str):
    df_all = ensure_dataframe(st.session_state.data)
    ym = current_year_month()

    # 目標值
    target = get_target_safe(ym, "app" if category == "app" else "survey")

    # === 目標區塊 ===
    if category == "app":
        df_m_app = month_filter(df_all, ym)
        current_total = int(df_m_app[df_m_app["type"].isin(["new", "exist", "line"])]["count"].sum())
    else:
        df_m = month_filter(df_all, ym)
        current_total = int(df_m[df_m["type"] == "survey"]["count"].sum())

    st.subheader(f"{label}（{ym}）")
    colA, colB = st.columns([2, 1])
    with colA:
        st.write(f"今月累計：**{current_total}** 件")
        if target > 0:
            ratio = min(1.0, current_total / max(1, target))
            st.progress(ratio, text=f"目標 {target} 件・達成率 {ratio*100:.1f}%")
        else:
            st.info("目標未設定")
    with colB:
        with st.popover("🎯 目標を設定/更新"):
            new_target = st.number_input("今月目標", min_value=0, step=1, value=int(target))
            if st.button(f"保存（{label}）"):
                try:
                    set_target(ym, "app" if category == "app" else "survey", int(new_target))
                    get_target_safe.clear()
                    st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存失敗: {e}")

    # === 週別合計（w）— 預設當月；可選 年 + 月 ===
    st.subheader("週別合計")
    yearsW = year_options(df_all)
    default_yearW = date.today().year if date.today().year in yearsW else yearsW[-1]

    colY, colM = st.columns(2)
    with colY:
        yearW = st.selectbox("年（週集計）", options=yearsW, index=yearsW.index(default_yearW), key=f"weekly_year_{category}")

    months_in_year = sorted(set(
        df_all[df_all["date"].dt.year == int(yearW)]["date"].dt.strftime("%Y-%m").dropna().tolist()
    ))
    if not months_in_year:
        months_in_year = [f"{yearW}-{str(date.today().month).zfill(2)}"]

    default_monthW = (
        date.today().strftime("%Y-%m")
        if (date.today().year == int(yearW) and date.today().strftime("%Y-%m") in months_in_year)
        else months_in_year[-1]
    )
    with colM:
        monthW = st.selectbox("月", options=months_in_year, index=months_in_year.index(default_monthW), key=f"weekly_month_{category}")

    df_monthW = df_all[df_all["date"].dt.strftime("%Y-%m") == monthW].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]

    if df_monthW.empty:
        st.info("この月のデータがありません。")
    else:
        df_monthW["week_iso"] = df_monthW["date"].dt.isocalendar().week.astype(int)
        df_monthW["w_num"] = df_monthW["week_iso"].apply(lambda w: int(_week_num_to_label(w)[1:]))

        weekly = df_monthW.groupby("w_num")["count"].sum().reset_index().sort_values("w_num")
        weekly["w"] = weekly["w_num"].apply(lambda x: f"w{x}")
        st.caption(f"表示中：{yearW}年・{monthW}")
        st.dataframe(weekly[["w", "count"]].rename(columns={"count": "合計"}), use_container_width=True)

    # === 構成比（新規・既存・LINE）— 年份 + 期間 ===
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        colYc, colp1, colp2 = st.columns([1, 1, 2])
        years = year_options(df_all)
        default_year = date.today().year if date.today().year in years else years[-1]
        with colYc:
            year_sel = st.selectbox("年", options=years, index=years.index(default_year), key=f"comp_year_{category}")
        with colp1:
            ptype = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"comp_period_type_{category}")
        with colp2:
            opts, default = _period_options(df_all, ptype, year_sel)
            idx = opts.index(default) if default in opts else 0
            sel = st.selectbox("表示する期間", options=opts, index=idx if len(opts) > 0 else 0, key=f"comp_period_value_{category}")

        df_comp_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
        df_comp = _filter_by_period(df_comp_base, ptype, sel, year_sel)

        new_sum  = int(df_comp[df_comp["type"] == "new"]["count"].sum())
        exist_sum= int(df_comp[df_comp["type"] == "exist"]["count"].sum())
        line_sum = int(df_comp[df_comp["type"] == "line"]["count"].sum())
        total = new_sum + exist_sum + line_sum

        if total > 0:
            st.caption(f"表示中：{year_sel}年" if ptype=="年（単年）" else f"表示中：{year_sel}年・{sel}")
            plt.figure()
            labels = ["新規", "既存", "LINE"] if JP_FONT_READY else ["new", "exist", "LINE"]
            plt.pie([new_sum, exist_sum, line_sum], labels=labels, autopct="%1.1f%%", startangle=90)
            st.pyplot(plt.gcf())
        else:
            st.info("対象データがありません。")

    # === スタッフ別 合計 — 年份 + 期間（週/月/年） ===
    st.subheader("スタッフ別 合計")
    colYs, cpt1, cpt2 = st.columns([1, 1, 2])
    years2 = year_options(df_all)
    default_year2 = date.today().year if date.today().year in years2 else years2[-1]
    with colYs:
        year_sel2 = st.selectbox("年", options=years2, index=years2.index(default_year2), key=f"staff_year_{category}")
    with cpt1:
        ptype2 = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"staff_period_type_{category}", index=0)
    with cpt2:
        opts2, default2 = _period_options(df_all, ptype2, year_sel2)
        idx2 = opts2.index(default2) if default2 in opts2 else 0
        sel2 = st.selectbox("表示する期間", options=opts2, index=idx2 if len(opts2) > 0 else 0, key=f"staff_period_value_{category}")
    st.caption(f"（{year_sel2}年・{sel2 if ptype2!='年（単年）' else '年合計'}）")

    if category == "app":
        df_staff_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
    else:
        df_staff_base = df_all[df_all["type"] == "survey"].copy()

    df_staff = _filter_by_period(df_staff_base, ptype2, sel2, year_sel2)
    if df_staff.empty:
        st.info("対象データがありません。")
    else:
        # 只讓第 1 名顯示 👑
        staff_sum = (
            df_staff.groupby("name")["count"].sum()
            .reset_index()
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )
        staff_sum.insert(0, "順位", staff_sum.index + 1)
        if len(staff_sum) > 0:
            staff_sum.loc[0, "順位"] = f"{staff_sum.loc[0, '順位']} 👑"

        staff_sum = staff_sum.rename(columns={"name": "スタッフ", "count": "合計"})
        st.dataframe(staff_sum[["順位", "スタッフ", "合計"]], use_container_width=True)

    # === 月別累計（年次）長條圖（顯數字、Y 細格線、英文月份簡寫） ===
    st.subheader("月別累計（年次）")
    years3 = year_options(df_all)
    default_year3 = date.today().year if date.today().year in years3 else years3[-1]
    year_sel3 = st.selectbox("年を選択", options=years3, index=years3.index(default_year3), key=f"monthly_year_{category}")

    if category == "app":
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"].isin(["new", "exist", "line"]))]
        title_label = "and st"
    else:
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"] == "survey")]
        title_label = "Survey"

    if df_year.empty:
        st.info("対象データがありません。")
    else:
        import calendar
        monthly = (
            df_year.groupby(df_year["date"].dt.strftime("%Y-%m"))["count"]
            .sum()
            .reindex([f"{year_sel3}-{str(m).zfill(2)}" for m in range(1, 13)], fill_value=0)
        )
        labels = [calendar.month_abbr[int(s.split("-")[1])] for s in monthly.index.tolist()]  # Jan, Feb, ...
        values = monthly.values.tolist()

        plt.figure()
        bars = plt.bar(labels, values)
        plt.grid(True, axis="y", linestyle="--", linewidth=0.5)
        plt.xticks(rotation=0, ha="center")
        # <<< 這裡直接固定英文標題，App = and st / Survey = Survey >>>
        plt.title(f"{title_label} Monthly totals ({int(year_sel3)})")

        ymax = max(values) if values else 0
        if ymax > 0:
            plt.ylim(0, ymax * 1.15)
        for bar, val in zip(bars, values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{int(val)}", ha="center", va="bottom", fontsize=9)

        st.pyplot(plt.gcf())


# -----------------------------
# 表單：APP 推薦紀錄
# -----------------------------
with tab1:
    st.subheader("and st 会員登録")
    with st.form("app_form"):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            existing_names = st.session_state.names
            if existing_names:
                name_select = st.selectbox("スタッフ名（選択）", options=existing_names, index=0, key="app_name_select")
                st.caption("未登録の場合は下で新規入力")
            else:
                name_select = ""
                st.info("登録済みの名前がありません。下で新規入力してください。")
            name_new = st.text_input("スタッフ名（新規入力）", key="app_name_text").strip()
            name = name_new or name_select
        with c2:
            d = st.date_input("日付", value=date.today())
        with c3:
            pass

        coln1, coln2, coln3 = st.columns(3)
        with coln1: new_cnt = st.number_input("新規（件）", min_value=0, step=1, value=0)
        with coln2: exist_cnt = st.number_input("既存（件）", min_value=0, step=1, value=0)
        with coln3: line_cnt = st.number_input("LINE（件）", min_value=0, step=1, value=0)

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                total_cnt = int(new_cnt) + int(exist_cnt) + int(line_cnt)
                try:
                    if total_cnt == 0:
                        st.session_state.names = sorted(set(st.session_state.names) | {name})
                        st.success("名前を登録しました。（データは追加していません）")
                    else:
                        if new_cnt > 0:   insert_or_update_record(ymd(d), name, "new",   int(new_cnt))
                        if exist_cnt > 0: insert_or_update_record(ymd(d), name, "exist", int(exist_cnt))
                        if line_cnt > 0:  insert_or_update_record(ymd(d), name, "line",  int(line_cnt))
                        load_all_records_cached.clear()
                        st.session_state.data = load_all_records_cached()
                        st.session_state.names = names_from_records(st.session_state.data)
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存失敗: {e}")

    show_statistics("app", "APP")
    render_refresh_button("refresh_app_tab")


# -----------------------------
# 表單：アンケート（問卷取得件數）
# -----------------------------
with tab2:
    st.subheader("アンケート")
    with st.form("survey_form"):
        c1, c2 = st.columns([2, 2])
        with c1:
            existing_names2 = st.session_state.names
            if existing_names2:
                name_select2 = st.selectbox("スタッフ名（選択）", options=existing_names2, index=0, key="survey_name_select")
                st.caption("未登録の場合は下で新規入力")
            else:
                name_select2 = ""
                st.info("登録済みの名前がありません。下で新規入力してください。")
            name_new2 = st.text_input("スタッフ名（新規入力）", key="survey_name_text").strip()
            name2 = name_new2 or name_select2
        with c2:
            d2 = st.date_input("日付", value=date.today(), key="survey_date")

        cnt = st.number_input("アンケート（件）", min_value=0, step=1, value=0)
        submitted2 = st.form_submit_button("保存")
        if submitted2:
            if not name2:
                st.warning("名前を入力してください。")
            else:
                try:
                    if int(cnt) == 0:
                        st.session_state.names = sorted(set(st.session_state.names) | {name2})
                        st.success("名前を登録しました。（データは追加していません）")
                    else:
                        insert_or_update_record(ymd(d2), name2, "survey", int(cnt))
                        load_all_records_cached.clear()
                        st.session_state.data = load_all_records_cached()
                        st.session_state.names = names_from_records(st.session_state.data)
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存失敗: {e}")

    show_statistics("survey", "アンケート")
    render_refresh_button("refresh_survey_tab")


# -----------------------------
# データ管理
# -----------------------------
with tab3:
    show_data_management()

# -*- coding: utf-8 -*-
import os
from datetime import date
import uuid
import calendar

import pandas as pd
import streamlit as st
import html
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials

from ui_theme_dark import apply_dark_theme, render_kpi_row, render_section_title
from charts_dark import weekly_progress_chart

# -----------------------------
# Page config & title
# -----------------------------
try:
    st.set_page_config(page_title="and st 統計Team W’s", page_icon="icon.png", layout="wide")
except Exception:
    pass

st.title("and st W’s")
apply_dark_theme()

# -----------------------------
# Japanese font (best-effort; 防止日文亂碼)
# -----------------------------
from matplotlib import font_manager, rcParams

JP_FONT_READY = False
try_candidates = [
    os.path.join(os.path.dirname(__file__), "fonts", "NotoSansJP-Regular.otf"),
    os.path.join(os.path.dirname(__file__), "NotoSansJP-Regular.otf"),
    "/mnt/data/NotoSansJP-Regular.otf",
]
try:
    for fp in try_candidates:
        if os.path.exists(fp):
            font_manager.fontManager.addfont(fp)
            _prop = font_manager.FontProperties(fname=fp)
            rcParams["font.family"] = _prop.get_name()
            JP_FONT_READY = True
            break
    if not JP_FONT_READY:
        _JP_FONT_CANDIDATES = [
            "Noto Sans CJK JP", "Noto Sans JP", "IPAGothic", "IPAexGothic",
            "TakaoGothic", "Yu Gothic", "Hiragino Sans", "Meiryo", "MS Gothic",
        ]
        available = {f.name for f in font_manager.fontManager.ttflist}
        for _name in _JP_FONT_CANDIDATES:
            if _name in available:
                rcParams["font.family"] = _name
                JP_FONT_READY = True
                break
except Exception:
    JP_FONT_READY = False

rcParams["axes.unicode_minus"] = False

# -----------------------------
# Backend（reuse your modules）
# -----------------------------
from db_gsheets import (
    init_db,
    init_target_table,
    load_all_records,
    insert_or_update_record,
    get_target,
    set_target,
)
from data_management import show_data_management

# -----------------------------
# Cache / Init
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
# Utils
# -----------------------------
def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def current_year_month() -> str:
    return date.today().strftime("%Y-%m")

# -----------------------------
# Refund attendance (Google Sheets)
# -----------------------------
@st.cache_resource
def get_refund_attendance_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes,
    )

    gc = gspread.authorize(creds)

    spreadsheet = gc.open("and_st_recommend")

    try:
        ws = spreadsheet.worksheet("refund_attendance")
    except Exception:
        ws = spreadsheet.add_worksheet(title="refund_attendance", rows=200, cols=10)
        ws.append_row(["year", "staff", "attendance_days"])

    return ws


def load_refund_attendance():
    try:
        ws = get_refund_attendance_ws()
        records = ws.get_all_records()

        data = {}
        for r in records:
            year = str(r.get("year", "")).strip()
            staff = str(r.get("staff", "")).strip()
            days = int(r.get("attendance_days", 0))

            if not year or not staff:
                continue

            if year not in data:
                data[year] = {}

            data[year][staff] = days

        return data

    except Exception:
        return {}


def save_refund_attendance(data):
    ws = get_refund_attendance_ws()

    ws.clear()
    ws.append_row(["year", "staff", "attendance_days"])

    rows = []

    for year, staffs in data.items():
        for staff, days in staffs.items():
            rows.append([year, staff, int(days)])

    if rows:
        ws.append_rows(rows)




def get_chart_theme_key(category: str) -> str:
    return f"chart_theme_{category}"


def get_chart_theme(category: str) -> str:
    return st.session_state.get(get_chart_theme_key(category), "dark")


def render_chart_theme_toggle(category: str):
    key = get_chart_theme_key(category)
    current = st.session_state.get(key, "dark")
    label = "表示モード（Chart）"
    options = ["Dark", "Print"]
    index = 0 if current == "dark" else 1
    choice = st.radio(label, options=options, index=index, horizontal=True, key=f"{key}_radio")
    st.session_state[key] = "dark" if choice == "Dark" else "light"


def ensure_dataframe(records) -> pd.DataFrame:
    """
    records: list[dict] with at least date, name, type, count
    Adds:
      - iso_year / iso_week  (ISO week-year / week)  ✅跨年週正解
      - year_month           (calendar month)        ✅月別統計不受影響
    """
    df = pd.DataFrame(records or [])
    for col in ["date", "name", "type", "count"]:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)

    # ISO week-year / week (跨年週対策：2025/12/29 は 2026-W01)
    try:
        iso = df["date"].dt.isocalendar()
        df["iso_year"] = iso["year"].astype("Int64")
        df["iso_week"] = iso["week"].astype("Int64")
    except Exception:
        df["iso_year"] = pd.NA
        df["iso_week"] = pd.NA

    # Calendar month/year for monthly charts
    try:
        df["year_month"] = df["date"].dt.strftime("%Y-%m")
    except Exception:
        df["year_month"] = None

    return df

def month_filter(df: pd.DataFrame, ym: str) -> pd.DataFrame:
    if "date" not in df.columns:
        return df.iloc[0:0]
    return df[(df["date"].dt.strftime("%Y-%m") == ym)]

def names_from_records(records) -> list:
    return sorted({(r.get("name") or "").strip() for r in (records or []) if r.get("name")})

def year_options_calendar(df: pd.DataFrame) -> list:
    """公曆年（用在月別/年別顯示用）"""
    if "date" not in df.columns or df["date"].isna().all():
        return [date.today().year]
    years = sorted(set(df["date"].dropna().dt.year.astype(int).tolist()))
    return years or [date.today().year]

def year_options_iso(df: pd.DataFrame) -> list:
    """ISO 週年（用在週別分析用：跨年週正確歸類）"""
    if "iso_year" in df.columns and not df["iso_year"].isna().all():
        years = sorted(set(df["iso_year"].dropna().astype(int).tolist()))
        return years or [date.today().isocalendar().year]
    if "date" not in df.columns or df["date"].isna().all():
        return [date.today().isocalendar().year]
    iso = df["date"].dropna().dt.isocalendar()
    years = sorted(set(iso["year"].astype(int).tolist()))
    return years or [date.today().isocalendar().year]

def _period_options(df: pd.DataFrame, mode: str, selected_year: int):
    """
    期間選択:
      - 週（単週）: ISO 年で扱う ✅
      - 月（単月）: 公曆年月
      - 年（単年）: 公曆年（表示・月別集計の整合）
    """
    if "date" not in df.columns or df["date"].isna().all():
        today = date.today()
        if mode == "週（単週）":
            ww = today.isocalendar().week
            return [f"w{ww:02d}"], f"w{ww:02d}"
        elif mode == "月（単月）":
            dft = today.strftime("%Y-%m")
            return [dft], dft
        else:
            return [today.year], today.year

    dfx = df.dropna(subset=["date"]).copy()

    if mode == "週（単週）":
        if "iso_year" in dfx.columns and "iso_week" in dfx.columns:
            dyear = dfx[dfx["iso_year"].astype(int) == int(selected_year)]
            weeks = sorted(set(dyear["iso_week"].dropna().astype(int).tolist()))
        else:
            iso = dfx["date"].dt.isocalendar()
            dyear = dfx[iso["year"].astype(int) == int(selected_year)]
            weeks = sorted(set(iso.loc[dyear.index, "week"].astype(int).tolist()))

        labels = [f"w{w:02d}" for w in weeks] or [f"w{date.today().isocalendar().week:02d}"]
        default = f"w{date.today().isocalendar().week:02d}"
        if default not in labels:
            default = labels[0]
        return labels, default

    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        months = sorted(set(dyear["date"].dt.strftime("%Y-%m").tolist()))
        if not months:
            months = [f"{selected_year}-01"]
        default = date.today().strftime("%Y-%m") if date.today().year == int(selected_year) else months[-1]
        if default not in months:
            default = months[0]
        return months, default

    else:  # 年（公曆）
        ys = year_options_calendar(dfx)
        default = date.today().year if date.today().year in ys else ys[-1]
        return ys, default

def _filter_by_period(df: pd.DataFrame, mode: str, value, selected_year: int) -> pd.DataFrame:
    """週（単週）は ISO 年で扱う ✅"""
    if "date" not in df.columns or df["date"].isna().all():
        return df.iloc[0:0]
    dfx = df.dropna(subset=["date"]).copy()

    if mode == "週（単週）":
        try:
            want_week = int(str(value).lower().lstrip("w"))
        except Exception:
            return dfx.iloc[0:0]

        if "iso_year" in dfx.columns and "iso_week" in dfx.columns:
            dyear = dfx[dfx["iso_year"].astype(int) == int(selected_year)]
            return dyear[dyear["iso_week"].astype(int) == int(want_week)]

        iso = dfx["date"].dt.isocalendar()
        dyear = dfx[iso["year"].astype(int) == int(selected_year)]
        return dyear[iso.loc[dyear.index, "week"].astype(int) == int(want_week)]

    elif mode == "月（単月）":
        dyear = dfx[dfx["date"].dt.year == int(selected_year)]
        return dyear[dyear["date"].dt.strftime("%Y-%m") == str(value)]

    else:  # 年（公曆）
        return dfx[dfx["date"].dt.year == int(selected_year)]

# -----------------------------
# Session init
# -----------------------------
def init_session():
    if "data" not in st.session_state:
        st.session_state.data = load_all_records_cached()
    if "names" not in st.session_state:
        st.session_state.names = names_from_records(st.session_state.data)

_init_once()
init_session()

def render_refresh_button(btn_key: str = "refresh_btn"):
    spacer, right = st.columns([12, 1])
    with right:
        if st.button("↻", key=btn_key, help="重新整理資料"):
            load_all_records_cached.clear()
            st.session_state.data = load_all_records_cached()
            st.rerun()

# -----------------------------
# Rate block（能量條達成率）
# -----------------------------
def render_rate_block(category: str, label: str, current_total: int, target: int, ym: str):
    pct = 0 if target <= 0 else min(100.0, round(current_total * 100.0 / max(1, target), 1))
    bar_id = f"meter_{category}_{uuid.uuid4().hex[:6]}"

    st.markdown(
        f"""
<div style="font-size:14px;opacity:.85;">
  {ym} の累計：<b>{current_total}</b> 件 ／ 目標：<b>{target}</b> 件
</div>
<div id="{bar_id}" style="
  margin-top:8px;height:18px;border-radius:9px;
  background:rgba(0,0,0,.10);overflow:hidden;">
  <div style="height:100%;width:{pct}%;
    background:linear-gradient(90deg,#16a34a,#22c55e,#4ade80);
    box-shadow:0 0 12px rgba(34,197,94,.45) inset;"></div>
</div>
<div style="margin-top:6px;font-size:13px;opacity:.8;">
  達成率：<b>{pct:.1f}%</b>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.popover(f"🎯 目標を設定/更新（{label}）", use_container_width=True):
        new_target = st.number_input("月目標", min_value=0, step=1, value=int(target), key=f"target_input_{category}")
        if st.button("保存", key=f"target_save_{category}"):
            try:
                set_target(ym, "app" if category == "app" else "survey", int(new_target))
                st.success("保存しました。")
            except Exception as e:
                st.error(f"保存失敗: {e}")

# -----------------------------
# Statistics page
# -----------------------------
def week_count_in_month(ym: str) -> int:
    try:
        y, m = [int(x) for x in str(ym).split("-")]
        first = pd.Timestamp(year=y, month=m, day=1)
        last = first + pd.offsets.MonthEnd(1)
        days = pd.date_range(first, last, freq="D")
        return max(1, int(days.isocalendar()["week"].nunique()))
    except Exception:
        return 4


def weeks_touching_month(df: pd.DataFrame, ym: str) -> list[tuple[int, int]]:
    if df.empty or "date" not in df.columns:
        return []
    dfx = df.dropna(subset=["date"]).copy()
    if dfx.empty:
        return []
    month_rows = dfx[dfx["date"].dt.strftime("%Y-%m") == str(ym)].copy()
    if month_rows.empty:
        return []
    if "iso_year" not in month_rows.columns or "iso_week" not in month_rows.columns:
        iso = month_rows["date"].dt.isocalendar()
        month_rows["iso_year"] = iso["year"].astype(int)
        month_rows["iso_week"] = iso["week"].astype(int)
    pairs = (
        month_rows[["iso_year", "iso_week"]]
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
    )
    return [tuple(x) for x in pairs[["iso_year", "iso_week"]].itertuples(index=False, name=None)]


def week_label(iso_year: int, iso_week: int) -> str:
    return f"{int(iso_year)}-w{int(iso_week):02d}"


def previous_iso_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    try:
        monday = date.fromisocalendar(int(iso_year), int(iso_week), 1)
        py, pw, _ = (monday - pd.Timedelta(days=7)).isocalendar()
        return int(py), int(pw)
    except Exception:
        return int(iso_year), max(1, int(iso_week) - 1)


def get_full_week_df(df: pd.DataFrame, iso_year: int, iso_week: int, category: str) -> pd.DataFrame:
    if df.empty:
        return df.iloc[0:0].copy()
    dfx = df.copy()
    if "iso_year" not in dfx.columns or "iso_week" not in dfx.columns:
        iso = dfx["date"].dt.isocalendar()
        dfx["iso_year"] = iso["year"].astype(int)
        dfx["iso_week"] = iso["week"].astype(int)
    dfx = dfx[(dfx["iso_year"].astype(int) == int(iso_year)) & (dfx["iso_week"].astype(int) == int(iso_week))].copy()
    if category == "app":
        return dfx[dfx["type"].isin(["new", "exist", "line"])]
    return dfx[dfx["type"] == "survey"]


def get_week_total(df: pd.DataFrame, iso_year: int, iso_week: int, category: str) -> int:
    dfx = get_full_week_df(df, iso_year, iso_week, category)
    return int(dfx["count"].sum()) if not dfx.empty else 0


def get_week_range_label(iso_year: int, iso_week: int) -> str:
    try:
        start = date.fromisocalendar(int(iso_year), int(iso_week), 1)
        end = date.fromisocalendar(int(iso_year), int(iso_week), 7)
        return f"{start.strftime('%m/%d')} - {end.strftime('%m/%d')}"
    except Exception:
        return ""

def build_weekly_progress_df(df_month: pd.DataFrame, monthly_target: int, category: str) -> pd.DataFrame:
    if df_month.empty:
        return pd.DataFrame(columns=["week_label", "new", "exist", "line", "survey", "total", "target", "progress_rate"])

    dfx = df_month.copy()
    if "iso_year" not in dfx.columns or "iso_week" not in dfx.columns:
        iso = dfx["date"].dt.isocalendar()
        dfx["iso_year"] = iso["year"].astype(int)
        dfx["iso_week"] = iso["week"].astype(int)

    grouped = dfx.groupby(["iso_year", "iso_week", "type"])["count"].sum().unstack(fill_value=0).reset_index()
    for col in ["new", "exist", "line", "survey"]:
        if col not in grouped.columns:
            grouped[col] = 0

    if category == "app":
        grouped["total"] = grouped[["new", "exist", "line"]].sum(axis=1)
    else:
        grouped["total"] = grouped[["survey"]].sum(axis=1)

    grouped = grouped.sort_values(["iso_year", "iso_week"]).reset_index(drop=True)
    grouped["week_label"] = grouped["iso_week"].astype(int).apply(lambda x: f"Week {x}")
    weeks_n = max(1, len(grouped.index))
    weekly_target = (monthly_target / weeks_n) if monthly_target > 0 else 0
    grouped["target"] = weekly_target
    grouped["progress_rate"] = grouped["total"].apply(lambda x: round((x / weekly_target) * 100, 1) if weekly_target > 0 else 0)
    return grouped[["week_label", "new", "exist", "line", "survey", "total", "target", "progress_rate"]]

def show_statistics(category: str, label: str):
    df_all = ensure_dataframe(st.session_state.data)

    render_section_title(label, "獲得数管理ツール")
    render_chart_theme_toggle(category)
    chart_theme = get_chart_theme(category)

    # --- 週別合計（選月→該月按 ISO 週分組；label 會顯示 ISO 年） ---
    st.subheader("週別合計")
    yearsW = year_options_calendar(df_all)
    default_yearW = date.today().year if date.today().year in yearsW else yearsW[-1]
    colY, colM, colW = st.columns([1, 1, 1])
    with colY:
        yearW = st.selectbox("年（週集計）", options=yearsW, index=yearsW.index(default_yearW), key=f"weekly_year_{category}")

    months_in_year = sorted(set(
        df_all[df_all["date"].dt.year == int(yearW)]["date"].dt.strftime("%Y-%m").dropna().tolist()
    )) or [f"{yearW}-{str(date.today().month).zfill(2)}"]

    default_monthW = (
        date.today().strftime("%Y-%m")
        if (date.today().year == int(yearW) and date.today().strftime("%Y-%m") in months_in_year)
        else months_in_year[-1]
    )
    with colM:
        monthW = st.selectbox("月", options=months_in_year, index=months_in_year.index(default_monthW), key=f"weekly_month_{category}")

    week_pairs = weeks_touching_month(df_all, monthW)
    week_options = [week_label(y, w) for y, w in week_pairs]
    today_iso = date.today().isocalendar()
    current_week_label = week_label(int(today_iso.year), int(today_iso.week))
    default_week_label = current_week_label if current_week_label in week_options else (week_options[-1] if week_options else current_week_label)
    with colW:
        selected_week_label = st.selectbox(
            "週",
            options=week_options or [default_week_label],
            index=(week_options or [default_week_label]).index(default_week_label),
            key=f"weekly_focus_week_{category}",
        )

    try:
        selected_week_year = int(str(selected_week_label).split("-w")[0])
        selected_week_num = int(str(selected_week_label).split("-w")[1])
    except Exception:
        selected_week_year = int(today_iso.year)
        selected_week_num = int(today_iso.week)

    df_monthW = df_all[df_all["date"].dt.strftime("%Y-%m") == monthW].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]

    monthly_target = get_target_safe(monthW, category)
    weekly_progress = build_weekly_progress_df(df_monthW, monthly_target, category)
    month_total = int(weekly_progress["total"].sum()) if not weekly_progress.empty else 0
    month_rate = round((month_total / monthly_target) * 100, 1) if monthly_target > 0 else 0

    weekly_total = get_week_total(df_all, selected_week_year, selected_week_num, category)
    prev_year, prev_week_num = previous_iso_week(selected_week_year, selected_week_num)
    prev_total = get_week_total(df_all, prev_year, prev_week_num, category)
    delta_value = weekly_total - prev_total
    delta_pct = round(((weekly_total - prev_total) / prev_total) * 100, 1) if prev_total > 0 else (100.0 if weekly_total > 0 else 0.0)
    week_range_text = get_week_range_label(selected_week_year, selected_week_num)

    render_kpi_row([
        ("月間累計", f"{month_total}", "件", None),
        ("月間目標", f"{monthly_target}", "件", None),
        ("遂行率", f"{month_rate}", "%", "月基準"),
        (f"w{selected_week_num:02d}週累計", f"{weekly_total}", "件", f"前週 {prev_total}件 ({delta_pct:+.1f}%)"),
    ])
    if week_range_text:
        st.caption(f"選択週: {selected_week_label} / {week_range_text}　※完整週ベースで集計")

    if df_monthW.empty:
        st.info("この月のデータがありません。")
    else:
        if "iso_year" not in df_monthW.columns or "iso_week" not in df_monthW.columns:
            iso = df_monthW["date"].dt.isocalendar()
            df_monthW["iso_year"] = iso["year"].astype(int)
            df_monthW["iso_week"] = iso["week"].astype(int)

        weekly = (
            df_monthW.groupby(["iso_year", "iso_week"])["count"]
            .sum()
            .reset_index()
            .sort_values(["iso_year", "iso_week"])
        )
        weekly["w"] = weekly.apply(lambda r: f'{int(r["iso_year"])}-w{int(r["iso_week"]):02d}', axis=1)

        st.caption(f"表示中：{monthW}（ISO週）")
        st.dataframe(weekly[["w", "count"]].rename(columns={"count": "合計"}), use_container_width=True)

    st.subheader("週別推移グラフ")
    if not weekly_progress.empty:
        weekly_progress_chart(weekly_progress, category=category, theme=chart_theme)
    else:
        st.info("表示できる週別データがありません。")

    # --- 週ごとの曜日別表（上の選択週に連動） ---
    st.caption(f"曜日別明細：{selected_week_label}")
    df_week = get_full_week_df(df_all, selected_week_year, selected_week_num, category).copy()
    df_week["weekday"] = df_week["date"].dt.weekday if not df_week.empty else pd.Series(dtype=int)

    daily = df_week.groupby("weekday")["count"].sum().reindex(range(7), fill_value=0).reset_index()
    daily["label"] = daily["weekday"].map({0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"})

    st.dataframe(
        daily[["label", "count"]].rename(columns={"label": "Day", "count": "Total"}),
        use_container_width=True
    )

    # --- 構成比（App only）: 週選択は ISO 年で ✅ ---
    if category == "app":
        st.subheader("構成比（新規・既存・LINE）")
        colYc, colp1, colp2 = st.columns([1, 1, 2])

        years = year_options_iso(df_all)
        default_year = date.today().isocalendar().year if date.today().isocalendar().year in years else years[-1]

        with colYc:
            year_sel = st.selectbox("年", options=years, index=years.index(default_year), key=f"comp_year_{category}")
        with colp1:
            ptype = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"comp_period_type_{category}")
        with colp2:
            # 年（単年）/月（単月）時は公曆年的 year_sel 可能不直覺，但這裡主要用在週分析
            opts, default = _period_options(df_all, ptype, int(year_sel))  # ✅選択した年に合わせて週/月/年の候補を生成
            idx = opts.index(default) if default in opts else 0
            sel = st.selectbox("表示する期間", options=opts, index=idx if len(opts) > 0 else 0, key=f"comp_period_value_{category}")

        df_comp_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
        if ptype == "週（単週）":
            df_comp = _filter_by_period(df_comp_base, ptype, sel, year_sel)
            caption = f"表示中：{year_sel}年・{sel}"
        elif ptype == "月（単月）":
            df_comp = df_comp_base[df_comp_base["date"].dt.strftime("%Y-%m") == str(sel)]
            caption = f"表示中：{sel}"
        else:
            # 年（単年）：公曆年
            y_cal = int(str(sel))
            df_comp = df_comp_base[df_comp_base["date"].dt.year == y_cal]
            caption = f"表示中：{y_cal}年"

        new_sum = int(df_comp[df_comp["type"] == "new"]["count"].sum())
        exist_sum = int(df_comp[df_comp["type"] == "exist"]["count"].sum())
        line_sum = int(df_comp[df_comp["type"] == "line"]["count"].sum())
        total = new_sum + exist_sum + line_sum

        if total > 0:
            st.caption(caption)
            pie_bg = "#FFFFFF" if chart_theme == "light" else "#151A2D"
            pie_fg = "#111827" if chart_theme == "light" else "#F3F4F6"
            fig, ax = plt.subplots(figsize=(6, 4), facecolor=pie_bg)
            ax.set_facecolor(pie_bg)
            labels = ["New", "Existing", "LINE"]
            colors = ["#3B82F6", "#F59E0B", "#22C55E"]
            wedges, texts, autotexts = ax.pie(
                [new_sum, exist_sum, line_sum],
                labels=labels,
                autopct="%1.1f%%",
                startangle=90,
                colors=colors,
                textprops={"color": pie_fg, "fontsize": 10},
                wedgeprops={"edgecolor": pie_bg, "linewidth": 1},
            )
            ax.set_title("Composition (New / Existing / LINE)", color=pie_fg)
            for t in autotexts:
                t.set_color(pie_fg)
                t.set_fontsize(10)
            fig.patch.set_facecolor(pie_bg)
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("対象データがありません。")

    # --- スタッフ別 合計（週選択は ISO 年で ✅）---
    st.subheader("スタッフ別 合計")
    colYs, cpt1, cpt2 = st.columns([1, 1, 2])

    years2 = year_options_iso(df_all)
    default_year2 = date.today().isocalendar().year if date.today().isocalendar().year in years2 else years2[-1]
    with colYs:
        year_sel2 = st.selectbox("年", options=years2, index=years2.index(default_year2), key=f"staff_year_{category}")
    with cpt1:
        ptype2 = st.selectbox("対象期間", ["週（単週）", "月（単月）", "年（単年）"], key=f"staff_period_type_{category}", index=0)
    with cpt2:
        # ✅ 選んだ「年」に応じて期間候補を作る（2025が出ない不具合の修正）
        #   週（単週）: ISO 年で扱う
        #   月（単月）: 公暦年で扱う
        #   年（単年）: 公暦年（選択肢はデータから生成）
        opts2, default2 = _period_options(df_all, ptype2, year_sel2)

        idx2 = opts2.index(default2) if default2 in opts2 else 0
        sel2 = st.selectbox("表示する期間", options=opts2, index=idx2 if len(opts2) > 0 else 0, key=f"staff_period_value_{category}")

    if category == "app":
        df_staff_base = df_all[df_all["type"].isin(["new", "exist", "line"])].copy()
    else:
        df_staff_base = df_all[df_all["type"] == "survey"].copy()

    if ptype2 == "週（単週）":
        df_staff = _filter_by_period(df_staff_base, ptype2, sel2, year_sel2)
        st.caption(f"表示中：{year_sel2}年・{sel2}")
    elif ptype2 == "月（単月）":
        df_staff = df_staff_base[df_staff_base["date"].dt.strftime("%Y-%m") == str(sel2)]
        st.caption(f"表示中：{sel2}")
    else:
        y_cal = int(str(sel2))
        df_staff = df_staff_base[df_staff_base["date"].dt.year == y_cal]
        st.caption(f"表示中：{y_cal}年")

    if df_staff.empty:
        st.info("対象データがありません。")
    else:
        staff_sum = (
            df_staff.groupby("name")["count"].sum()
            .reset_index()
            .sort_values("count", ascending=False)
            .reset_index(drop=True)
        )
        staff_sum.insert(0, "順位", (staff_sum.index + 1).astype(str))
        if len(staff_sum) > 0:
            staff_sum.loc[0, "順位"] = f'{staff_sum.loc[0, "順位"]} 👑'
        staff_sum = staff_sum.rename(columns={"name": "スタッフ", "count": "合計"})
        st.dataframe(staff_sum[["順位", "スタッフ", "合計"]], use_container_width=True)

    # --- 月別累計（年次）：公曆年/月，不受 ISO 影響 ✅ ---
    st.subheader("月別累計（年次）")
    years3 = year_options_calendar(df_all)
    default_year3 = date.today().year if date.today().year in years3 else years3[-1]
    year_sel3 = st.selectbox("年を選択", options=years3, index=years3.index(default_year3), key=f"monthly_year_{category}")

    if category == "app":
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"].isin(["new", "exist", "line"]))]
        title_label = "and st W’s"
    else:
        df_year = df_all[(df_all["date"].dt.year == int(year_sel3)) & (df_all["type"] == "survey")]
        title_label = "Survey"

    if df_year.empty:
        st.info("対象データがありません。")
    else:
        monthly = (
            df_year.groupby(df_year["date"].dt.strftime("%Y-%m"))["count"]
            .sum()
            .reindex([f"{year_sel3}-{str(m).zfill(2)}" for m in range(1, 13)], fill_value=0)
        )
        labels = [calendar.month_abbr[int(s.split("-")[1])] for s in monthly.index.tolist()]
        values = monthly.values.tolist()

        bar_bg = "#FFFFFF" if chart_theme == "light" else "#151A2D"
        bar_fg = "#111827" if chart_theme == "light" else "#F3F4F6"
        grid_c = "#D1D5DB" if chart_theme == "light" else "#2A314D"
        palette = ["#3B82F6", "#F59E0B", "#22C55E"]
        fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=bar_bg)
        ax.set_facecolor(bar_bg)
        bar_colors = [palette[i % len(palette)] for i in range(len(labels))]
        bars = ax.bar(labels, values, color=bar_colors)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.5, color=grid_c)
        ax.tick_params(axis="x", colors=bar_fg)
        ax.tick_params(axis="y", colors=bar_fg)
        ax.set_title(f"{title_label} Monthly totals ({int(year_sel3)})", color=bar_fg)
        for spine in ax.spines.values():
            spine.set_color(grid_c)
        ymax = max(values) if values else 0
        if ymax > 0:
            ax.set_ylim(0, ymax * 1.15)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(), f"{int(val)}", ha="center", va="bottom", fontsize=9, color=bar_fg)
        fig.patch.set_facecolor(bar_bg)
        st.pyplot(fig)
        plt.close(fig)

def show_refund_event():
    """5/13〜5/20 の and st 限定・臨時ランキング画面。"""
    df_all = ensure_dataframe(st.session_state.data)

    st.subheader("還元イベント")

    # 年だけ選べるようにして、来年以降も同じ画面を使えるようにする
    years = year_options_calendar(df_all)
    this_year = date.today().year
    if this_year not in years:
        years = sorted(set(years + [this_year]))
    default_year = this_year if this_year in years else years[-1]
    event_year = st.selectbox(
        "イベント年",
        options=years,
        index=years.index(default_year),
        key="refund_event_year",
    )

    start_dt = pd.Timestamp(year=int(event_year), month=5, day=13)
    end_dt = pd.Timestamp(year=int(event_year), month=5, day=20)

    df_event = df_all[
        (df_all["date"] >= start_dt)
        & (df_all["date"] <= end_dt)
        & (df_all["type"].isin(["new", "exist", "line"]))
    ].copy()

    st.markdown(f"#### 集計期間：{start_dt.strftime('%Y/%m/%d')} 〜 {end_dt.strftime('%Y/%m/%d')}")

    if df_event.empty:
        st.info("この期間の and st データがありません。")
        return

    # 日別×スタッフ別の and st 合計
    daily_staff = (
        df_event.groupby(["date", "name"], as_index=False)["count"]
        .sum()
        .rename(columns={"count": "daily_total"})
    )

    # 累計ランキング用
    staff_total = (
        df_event.groupby("name", as_index=False)["count"]
        .sum()
        .rename(columns={"count": "total"})
        .sort_values(["total", "name"], ascending=[False, True])
        .reset_index(drop=True)
    )

    staff_names = staff_total["name"].tolist()

    st.markdown("### 出勤日数入力")

    # 出勤日数をローカルJSONに保存して、再読み込み後も保持する
    attendance_store = load_refund_attendance()
    year_key = str(event_year)
    if year_key not in attendance_store or not isinstance(attendance_store.get(year_key), dict):
        attendance_store[year_key] = {}

    attendance_days = {}
    cols = st.columns(4)
    for i, staff in enumerate(staff_names):
        widget_key = f"refund_attendance_{event_year}_{staff}"
        saved_value = int(attendance_store[year_key].get(staff, 0))
        if widget_key not in st.session_state:
            st.session_state[widget_key] = saved_value

        with cols[i % 4]:
            attendance_days[staff] = st.number_input(
                f"{staff}",
                min_value=0,
                max_value=8,
                step=1,
                key=widget_key,
            )

    # 入力内容を毎回保存
    attendance_store[year_key] = {staff: int(attendance_days.get(staff, 0)) for staff in staff_names}
    try:
        save_refund_attendance(attendance_store)
    except Exception as e:
        st.warning(f"出勤日数の保存に失敗しました：{e}")

    ranking = staff_total.copy()
    ranking["出勤日数"] = ranking["name"].map(attendance_days).fillna(0).astype(float)
    ranking["AVG"] = ranking.apply(
        lambda r: round(float(r["total"]) / float(r["出勤日数"]), 2) if float(r["出勤日数"]) > 0 else 0,
        axis=1,
    )

    # 1. AVG
    avg_rank = ranking.sort_values(["AVG", "total", "name"], ascending=[False, False, True]).reset_index(drop=True)
    avg_winner = avg_rank.iloc[0]

    # 2. 期間中の単日最多
    max_daily_count = int(daily_staff["daily_total"].max())
    max_daily_rows = daily_staff[daily_staff["daily_total"] == max_daily_count].copy()
    max_daily_rows = max_daily_rows.sort_values(["date", "name"])
    max_daily_names = "、".join(max_daily_rows["name"].astype(str).unique().tolist())

    # 3. 累計最多
    total_rank = ranking.sort_values(["total", "AVG", "name"], ascending=[False, False, True]).reset_index(drop=True)
    total_winner = total_rank.iloc[0]

    # 4. 単日最多達成回数（日ごとの1位。タイの場合は同点者全員に1回カウント）
    max_by_day = daily_staff.groupby("date")["daily_total"].transform("max")
    daily_winners = daily_staff[daily_staff["daily_total"] == max_by_day].copy()
    win_counts = (
        daily_winners.groupby("name", as_index=False)["date"]
        .nunique()
        .rename(columns={"date": "単日最多達成回数"})
    )
    win_rank = (
        ranking[["name", "total", "AVG"]]
        .merge(win_counts, on="name", how="left")
        .fillna({"単日最多達成回数": 0})
    )
    win_rank["単日最多達成回数"] = win_rank["単日最多達成回数"].astype(int)
    win_rank = win_rank.sort_values(["単日最多達成回数", "total", "AVG", "name"], ascending=[False, False, False, True]).reset_index(drop=True)
    win_winner = win_rank.iloc[0]

    # 全スタッフ合計
    overall_total = int(df_event["count"].sum())

    # 全体ダウンロード率：app（新規＋既存）/ and st総数（新規＋既存＋LINE）
    app_total = int(df_event[df_event["type"].isin(["new", "exist"])]["count"].sum())
    app_rate = round(app_total * 100.0 / overall_total, 1) if overall_total > 0 else 0.0

    # 還元イベント専用カード：画像イメージに合わせたUI
    refund_cards = [
        ("全体累計", "全スタッフ", f"{overall_total}", "件"),
        ("全体DL率", f"app {app_total}件", f"{app_rate:.1f}", "%"),
        ("AVG 1位", str(avg_winner["name"]), f'{avg_winner["AVG"]:.2f}', f'累計 {int(avg_winner["total"])}件 / 出勤 {avg_winner["出勤日数"]:g}日'),
        ("単日最多", max_daily_names, f"{max_daily_count}", "件"),
        ("累計最多", str(total_winner["name"]), f'{int(total_winner["total"])}', "件"),
        ("単日MVP", str(win_winner["name"]), f'{int(win_winner["単日最多達成回数"])}', "回"),
    ]

    st.markdown(
        """
        <style>
        .refund-card {
            background:
                radial-gradient(circle at 20% 0%, rgba(34,197,94,0.10), transparent 32%),
                linear-gradient(180deg, rgba(15,23,42,0.98) 0%, rgba(3,10,24,0.98) 100%);
            border: 1px solid rgba(74, 96, 154, 0.62);
            border-radius: 18px;
            padding: 1.25rem 1.05rem 1.15rem 1.05rem;
            min-height: 205px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.24);
        }
        .refund-card-title {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: #86efac;
            font-size: 0.95rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            margin-bottom: 1.35rem;
            white-space: nowrap;
        }
        .refund-crown {
            font-size: 1.35rem;
            line-height: 1;
            filter: drop-shadow(0 0 8px rgba(134,239,172,0.35));
        }
        .refund-staff {
            color: #f8fafc;
            font-size: 0.92rem;
            font-weight: 700;
            line-height: 1.25;
            min-height: 1.6em;
            margin-bottom: 1.25rem;
            word-break: break-word;
        }
        .refund-number-row {
            display: flex;
            align-items: flex-end;
            gap: 0.42rem;
            margin-bottom: 1.05rem;
        }
        .refund-number {
            color: #7ee787;
            font-size: 2.35rem;
            font-weight: 900;
            line-height: 0.95;
            letter-spacing: 0.01em;
            text-shadow: 0 0 14px rgba(126,231,135,0.22);
        }
        .refund-unit {
            color: #e2e8f0;
            font-size: 0.95rem;
            font-weight: 800;
            line-height: 1.4;
            margin-bottom: 0.12rem;
        }
        .refund-sub {
            color: #22d3ee;
            font-size: 0.92rem;
            font-weight: 800;
            line-height: 1.25;
            min-height: 1.2em;
        }
        @media (max-width: 900px) {
            .refund-card { min-height: 180px; padding: 1.15rem; }
            .refund-card-title { font-size: 0.95rem; }
            .refund-staff { font-size: 1rem; }
            .refund-number { font-size: 2.45rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    refund_cols = st.columns(len(refund_cards))
    for col, (label, staff_name, main_value, sub) in zip(refund_cols, refund_cards):
        with col:
            unit_html = html.escape(sub) if sub in ["件", "回", "%"] else ""
            sub_html = "" if sub in ["件", "回", "%"] else html.escape(sub)
            st.markdown(
                f"""
                <div class="refund-card">
                    <div class="refund-card-title"><span class="refund-crown">♛</span><span>{html.escape(label)}</span></div>
                    <div class="refund-staff">{html.escape(staff_name)}</div>
                    <div class="refund-number-row">
                        <span class="refund-number">{html.escape(main_value)}</span>
                        <span class="refund-unit">{unit_html}</span>
                    </div>
                    <div class="refund-sub">{sub_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("### 個人タイトル一覧")
    title_table = pd.DataFrame([
        {
            "項目": "全体累計",
            "スタッフ": "全スタッフ",
            "数値": f"{overall_total}件",
            "補足": "期間中のand st合計",
        },
        {
            "項目": "全体DL率",
            "スタッフ": "app",
            "数値": f"{app_rate:.1f}%",
            "補足": f"app {app_total}件 / 全体 {overall_total}件",
        },
        {
            "項目": "AVG",
            "スタッフ": avg_winner["name"],
            "数値": f'{avg_winner["AVG"]:.2f}',
            "補足": f'累計 {int(avg_winner["total"])}件 / 出勤 {avg_winner["出勤日数"]:g}日',
        },
        {
            "項目": "期間中 単日最多",
            "スタッフ": max_daily_names,
            "数値": f"{max_daily_count}件",
            "補足": " / ".join([f'{r["date"].strftime("%m/%d")} {r["name"]}' for _, r in max_daily_rows.iterrows()]),
        },
        {
            "項目": "累計最多",
            "スタッフ": total_winner["name"],
            "数値": f'{int(total_winner["total"])}件',
            "補足": "期間累計",
        },
        {
            "項目": "単日MVP",
            "スタッフ": win_winner["name"],
            "数値": f'{int(win_winner["単日最多達成回数"])}回',
            "補足": "日別1位の回数。同点の場合は全員カウント",
        },
    ])
    st.dataframe(title_table, use_container_width=True, hide_index=True)

    st.markdown("### スタッフ別 詳細")
    detail = ranking.merge(win_counts, on="name", how="left").fillna({"単日最多達成回数": 0})
    detail["単日最多達成回数"] = detail["単日最多達成回数"].astype(int)
    detail = detail.sort_values(["total", "AVG", "単日最多達成回数", "name"], ascending=[False, False, False, True]).reset_index(drop=True)
    detail.insert(0, "順位", detail.index + 1)
    detail = detail.rename(columns={"name": "スタッフ", "total": "累計"})
    detail_display = detail[["順位", "スタッフ", "累計", "出勤日数", "AVG", "単日最多達成回数"]].rename(columns={"単日最多達成回数": "単日MVP"})
    st.dataframe(detail_display, use_container_width=True, hide_index=True)

    st.markdown("### 日別スタッフ別 明細")
    detail_daily = daily_staff.copy()
    detail_daily["date"] = detail_daily["date"].dt.strftime("%m/%d")
    detail_daily = detail_daily.rename(columns={"date": "日付", "name": "スタッフ", "daily_total": "and st 合計"})
    st.dataframe(detail_daily.sort_values(["日付", "and st 合計", "スタッフ"], ascending=[True, False, True]), use_container_width=True, hide_index=True)


# -----------------------------
# Tabs
# -----------------------------
tab_reg, tab_event, tab3, tab4, tab5 = st.tabs(["件数登録", "還元イベント", "and st 分析", "アンケート分析", "データ管理"])

# -----------------------------
# 件数登録（and st + アンケート 合併）
# -----------------------------
with tab_reg:
    st.subheader("件数登録")
    with st.form("reg_form"):
        c1, c2 = st.columns([2, 2])
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

        st.markdown("#### and st（新規 / 既存 / LINE）")
        coln1, coln2, coln3 = st.columns(3)
        with coln1:
            new_cnt = st.number_input("新規（件）", min_value=0, step=1, value=0, key="reg_new")
        with coln2:
            exist_cnt = st.number_input("既存（件）", min_value=0, step=1, value=0, key="reg_exist")
        with coln3:
            line_cnt = st.number_input("LINE（件）", min_value=0, step=1, value=0, key="reg_line")

        st.markdown("#### アンケート")
        survey_cnt = st.number_input("アンケート（件）", min_value=0, step=1, value=0, key="reg_survey")

        submitted = st.form_submit_button("保存")
        if submitted:
            if not name:
                st.warning("名前を入力してください。")
            else:
                try:
                    # and st
                    if int(new_cnt) > 0:
                        insert_or_update_record(ymd(d), name, "new", int(new_cnt))
                    if int(exist_cnt) > 0:
                        insert_or_update_record(ymd(d), name, "exist", int(exist_cnt))
                    if int(line_cnt) > 0:
                        insert_or_update_record(ymd(d), name, "line", int(line_cnt))

                    # survey
                    if int(survey_cnt) > 0:
                        insert_or_update_record(ymd(d), name, "survey", int(survey_cnt))

                    # if all 0, just register the name
                    if sum([int(new_cnt), int(exist_cnt), int(line_cnt), int(survey_cnt)]) == 0:
                        st.session_state.names = sorted(set(st.session_state.names) | {name})
                        st.success("名前を登録しました。（データは追加していません）")
                    else:
                        load_all_records_cached.clear()
                        st.session_state.data = load_all_records_cached()
                        st.session_state.names = names_from_records(st.session_state.data)
                        st.success("保存しました。")
                except Exception as e:
                    st.error(f"保存失敗: {e}")

    # 達成率（能量條）
    df_all = ensure_dataframe(st.session_state.data)
    ym = current_year_month()
    df_m = month_filter(df_all, ym)

    app_total = int(df_m[df_m["type"].isin(["new", "exist", "line"])]["count"].sum())
    survey_total = int(df_m[df_m["type"] == "survey"]["count"].sum())

    try:
        app_target = get_target(ym, "app")
    except Exception:
        app_target = 0
    try:
        survey_target = get_target(ym, "survey")
    except Exception:
        survey_target = 0

    st.markdown("### 達成率")
    _c1, _c2 = st.columns(2)
    with _c1:
        st.caption("and st")
        render_rate_block("app", "and st", app_total, app_target, ym)
    with _c2:
        st.caption("アンケート")
        render_rate_block("survey", "アンケート", survey_total, survey_target, ym)

    render_refresh_button("refresh_reg_tab")

# -----------------------------
# 還元イベント
# -----------------------------
with tab_event:
    show_refund_event()

# -----------------------------
# and st 分析
# -----------------------------
with tab3:
    show_statistics("app", "and st")

# -----------------------------
# アンケート分析
# -----------------------------
with tab4:
    show_statistics("survey", "アンケート")

# -----------------------------
# データ管理
# -----------------------------
with tab5:
    try:
        show_data_management()
    except Exception as e:
        st.error(f"データ管理画面の読み込みに失敗しました: {e}")

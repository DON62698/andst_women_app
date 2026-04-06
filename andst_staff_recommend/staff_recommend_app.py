# -*- coding: utf-8 -*-
import os
from datetime import date
import uuid
import calendar

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from ui_theme_dark import apply_dark_theme, render_kpi_row, render_section_title
from charts_dark import weekly_progress_chart

# -----------------------------
# Page config & title
# -----------------------------
try:
    st.set_page_config(page_title="and st 統計 Team Men's", layout="wide")
except Exception:
    pass

st.title("and st Men's")
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
    st.caption("Print を選ぶと、円グラフ・月別棒グラフ・週別推移グラフを白背景で表示できます。")


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

    render_section_title(label, "Dark SaaS dashboard")
    render_chart_theme_toggle(category)
    chart_theme = get_chart_theme(category)

    # --- 週別合計（選月→該月按 ISO 週分組；label 會顯示 ISO 年） ---
    st.subheader("週別合計")
    yearsW = year_options_calendar(df_all)
    default_yearW = date.today().year if date.today().year in yearsW else yearsW[-1]
    colY, colM = st.columns(2)
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

    df_monthW = df_all[df_all["date"].dt.strftime("%Y-%m") == monthW].copy()
    if category == "app":
        df_monthW = df_monthW[df_monthW["type"].isin(["new", "exist", "line"])]
    else:
        df_monthW = df_monthW[df_monthW["type"] == "survey"]

    monthly_target = get_target_safe(monthW, category)
    weekly_progress = build_weekly_progress_df(df_monthW, monthly_target, category)
    month_total = int(weekly_progress["total"].sum()) if not weekly_progress.empty else 0
    month_rate = round((month_total / monthly_target) * 100, 1) if monthly_target > 0 else 0
    weekly_total = int(weekly_progress["total"].iloc[-1]) if not weekly_progress.empty else 0
    prev_total = int(weekly_progress["total"].iloc[-2]) if len(weekly_progress) > 1 else 0
    delta_pct = round(((weekly_total - prev_total) / prev_total) * 100, 1) if prev_total > 0 else (100.0 if weekly_total > 0 else 0.0)

    render_kpi_row([
        ("月間累計", f"{month_total}", "件", None),
        ("月間目標", f"{monthly_target}", "件", None),
        ("遂行率", f"{month_rate}", "%", f"前週比 {delta_pct:+.1f}%"),
        ("週間累計", f"{weekly_total}", "件", None),
    ])

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

    # --- 週ごとの曜日別表（既存機能は維持） ---
    yearsD = year_options_iso(df_all)
    default_yearD = date.today().isocalendar().year if date.today().isocalendar().year in yearsD else yearsD[-1]
    colDY, colDW = st.columns([1, 1])
    with colDY:
        yearD = st.selectbox("年（曜日別明細）", options=yearsD, index=yearsD.index(default_yearD), key=f"daily_year_{category}")

    df_yearD = df_all[df_all["iso_year"].astype("Int64") == int(yearD)].copy()
    if category == "app":
        df_yearD = df_yearD[df_yearD["type"].isin(["new", "exist", "line"])]
    else:
        df_yearD = df_yearD[df_yearD["type"] == "survey"]

    weeksD = sorted(set(df_yearD["iso_week"].dropna().astype(int).tolist()))
    week_labels = [f"w{w:02d}" for w in weeksD] or [f"w{date.today().isocalendar().week:02d}"]
    default_wlabel = f"w{date.today().isocalendar().week:02d}"
    if default_wlabel not in week_labels:
        default_wlabel = week_labels[0]
    with colDW:
        sel_week_label = st.selectbox("週", options=week_labels, index=week_labels.index(default_wlabel), key=f"daily_week_{category}")

    try:
        sel_week_num = int(sel_week_label.lstrip("w"))
    except Exception:
        sel_week_num = date.today().isocalendar().week

    df_week = df_yearD.copy()
    df_week["iso_week"] = df_week["iso_week"].astype(int)
    df_week = df_week[df_week["iso_week"] == sel_week_num].copy()
    df_week["weekday"] = df_week["date"].dt.weekday

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
        staff_sum.insert(0, "順位", staff_sum.index + 1)
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
        title_label = "and st"
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

# -----------------------------
# Tabs
# -----------------------------
tab_reg, tab3, tab4, tab5 = st.tabs(["件数登録", "and st 分析", "アンケート分析", "データ管理"])

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

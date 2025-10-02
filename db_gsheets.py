# db_gsheets.py
# 強化版：所有 gspread I/O 皆加上重試、刪除前二次確認、append/update 安全處理
from __future__ import annotations

import os
import json
import time
import datetime as dt
from typing import Optional, List, Dict, Any

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

import gspread
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound

# =========================
# 基本設定
# =========================

DEFAULT_SPREADSHEET_NAME = "and_st_recommend"
RECORD_SHEET_NAME = "records"
RECORD_HEADERS = ["date", "week", "name", "type", "count"]

# =========================
# 共用工具：重試包裝
# =========================

def _with_retry(fn, *args, retries: int = 3, delay: float = 0.6, **kwargs):
    """
    對 gspread 操作做簡單重試：
    - 捕捉 APIError 並針對 429/5xx 做指數退避
    - 其他偶發 Exception 也給少量重試
    """
    last_err = None
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            last_err = e
            status = None
            if getattr(e, "response", None) is not None:
                status = getattr(e.response, "status_code", None)
            if status in (429, 500, 502, 503, 504) or status is None:
                time.sleep(delay * (2 ** i))
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(delay * (2 ** i))
    raise last_err

# =========================
# 認證 / 開啟試算表
# =========================

def _load_service_account_info() -> Dict[str, Any]:
    """
    優先從 st.secrets 讀服務帳戶（推薦）
    備援：環境變數 GOOGLE_SERVICE_ACCOUNT_JSON（整段 JSON）
    """
    # 1) Streamlit secrets
    if st is not None:
        # 常見兩種配置鍵名：gcp_service_account 或 google_service_account
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
        if "google_service_account" in st.secrets:
            return dict(st.secrets["google_service_account"])
        # 也可能用分組
        if "gcp" in st.secrets and "service_account" in st.secrets["gcp"]:
            return dict(st.secrets["gcp"]["service_account"])

    # 2) 環境變數
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        return json.loads(raw)

    raise RuntimeError(
        "Service account credentials not found. "
        "Please set st.secrets['gcp_service_account'] or env GOOGLE_SERVICE_ACCOUNT_JSON."
    )

def _get_client() -> gspread.Client:
    sa_info = _load_service_account_info()
    return _with_retry(gspread.service_account_from_dict, sa_info)

def _get_spreadsheet_name() -> str:
    if st is not None:
        if "gsheets" in st.secrets and "spreadsheet_name" in st.secrets["gsheets"]:
            return str(st.secrets["gsheets"]["spreadsheet_name"])
    return DEFAULT_SPREADSHEET_NAME

def _open_workbook():
    client = _get_client()
    name = _get_spreadsheet_name()
    try:
        return _with_retry(client.open, name)
    except SpreadsheetNotFound:
        # 若不存在則用 title 新建
        sh = _with_retry(client.create, name)
        # 需要與服務帳戶共享（通常已擁有）
        return sh

def _ensure_worksheet(sh, title: str, headers: List[str]):
    try:
        ws = _with_retry(sh.worksheet, title)
    except WorksheetNotFound:
        ws = _with_retry(sh.add_worksheet, title=title, rows=1000, cols=max(10, len(headers)))
        # 寫入表頭
        _with_retry(ws.update, "A1", [headers])
    else:
        # 若表頭缺失或不同，嘗試補齊
        first_row = _with_retry(ws.row_values, 1)
        if first_row != headers:
            # 直接覆蓋第一列為 headers
            _with_retry(ws.update, "A1", [headers])
    return ws

# =========================
# 週字串工具
# =========================

def _week_str(date_str: str) -> str:
    """
    將 'YYYY-MM-DD' -> '32w' 這類表示（ISO週）
    """
    d = dt.date.fromisoformat(date_str)
    iso_year, iso_week, _ = d.isocalendar()
    # 不需要年份，沿用既有範例「32w」
    return f"{iso_week}w"

# =========================
# 資料操作：查、增、改、刪
# =========================

def _find_row(ws, date_str: str, name: str, category: str) -> Optional[int]:
    """
    回傳符合條件的第一列 index（1-based）。找不到回傳 None。
    """
    all_values = _with_retry(ws.get_all_values)
    if not all_values:
        return None
    # 跳過表頭，從第2列開始
    for idx, row in enumerate(all_values[1:], start=2):
        # 以當前 schema: ["date","week","name","type","count"]
        d, w, n, t, c = (row + ["", "", "", "", ""])[:5]
        if d == date_str and n == name and t == category:
            return idx
    return None

def load_all_records() -> List[Dict[str, Any]]:
    """
    讀取 records 工作表所有資料（去掉表頭），回傳 list[dict]
    欄位：date, week, name, type, count
    """
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, RECORD_SHEET_NAME, RECORD_HEADERS)
    recs = _with_retry(ws.get_all_records, empty2zero=False, default_blank="")
    # count 欄位轉 int（若空白則 0）
    for r in recs:
        try:
            r["count"] = int(str(r.get("count", "") or 0))
        except Exception:
            r["count"] = 0
    return recs

def insert_or_update_record(date_str: str, name: str, category: str, count: int) -> None:
    """
    若該 (date, name, category) 已存在 -> 覆寫 count
    否則 -> 新增一列
    """
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, RECORD_SHEET_NAME, RECORD_HEADERS)

    row_idx = _find_row(ws, date_str, name, category)
    if row_idx:
        # 更新（二次確認）
        row_vals = _with_retry(ws.row_values, row_idx)
        d, w, n, t, c = (row_vals + ["", "", "", "", ""])[:5]
        if not (d == date_str and n == name and t == category):
            # 若內容已位移，重新搜尋
            row_idx = _find_row(ws, date_str, name, category)

        if row_idx:
            # 只更新 count 欄（第5欄）
            try_val = int(count) if str(count).strip() != "" else 0
            _with_retry(ws.update_cell, row_idx, 5, try_val)
            return

    # 走新增
    week = _week_str(date_str)
    try_val = int(count) if str(count).strip() != "" else 0
    _with_retry(ws.append_row, [date_str, week, name, category, try_val], value_input_option="RAW")

def delete_record(date_str: str, name: str, category: str) -> bool:
    """
    刪除符合 (date, name, category) 的第一筆資料。
    成功刪除回傳 True，找不到回傳 False。
    """
    sh = _open_workbook()
    ws = _ensure_worksheet(sh, RECORD_SHEET_NAME, RECORD_HEADERS)

    # 第一次尋找
    row_idx = _find_row(ws, date_str, name, category)
    if not row_idx:
        return False

    # 刪除前再次確認該 row 仍是目標（避免位移/併發）
    row_vals = _with_retry(ws.row_values, row_idx)
    d, w, n, t, c = (row_vals + ["", "", "", "", ""])[:5]
    if not (d == date_str and n == name and t == category):
        # 若不同，再全表重找一次；仍找不到就視為已被移除
        row_idx = _find_row(ws, date_str, name, category)
        if not row_idx:
            return False

    _with_retry(ws.delete_rows, row_idx)
    return True

# =========================
# 其他小幫手（可選）
# =========================

def upsert_from_form(date_str: str, name: str, category: str, count: Any) -> Dict[str, Any]:
    """
    方便在表單流程中直接呼叫的 upsert 包裝。
    自動轉換 count -> int，並回傳結果訊息。
    """
    try:
        c = int(str(count).strip())
    except Exception:
        c = 0
    insert_or_update_record(date_str, name, category, c)
    return {"ok": True, "message": "Saved."}

def ensure_schema() -> None:
    """
    啟動時可呼叫：確保試算表與工作表存在且有正確表頭。
    """
    sh = _open_workbook()
    _ensure_worksheet(sh, RECORD_SHEET_NAME, RECORD_HEADERS)


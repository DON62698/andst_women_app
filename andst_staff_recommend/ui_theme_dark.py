import streamlit as st


PC_BREAKPOINT_PX = 1100


def apply_dark_theme():
    st.markdown(
        f"""
        <style>
        :root {{
            --bg-dark: #090d16;
            --bg-dark-2: #0b0f1a;
            --surface-dark: #12182a;
            --surface-dark-2: #151A2D;
            --border-dark: #232845;
            --text-dark: #F3F4F6;
            --muted-dark: #A8B0BF;
            --subtle-dark: #C3C9D4;

            --bg-light: #FFFFFF;
            --surface-light: #F8FAFC;
            --surface-light-2: #F7F7F8;
            --border-light: #D1D5DB;
            --border-light-2: #E5E7EB;
            --text-light: #111827;
            --muted-light: #6B7280;
            --hover-light: #F3F4F6;

            --primary: #2563EB;
            --primary-2: #3B82F6;
            --success: #059669;
        }}

        .stApp {{
            background: linear-gradient(180deg, var(--bg-dark) 0%, var(--bg-dark-2) 100%);
            color: var(--text-dark);
        }}
        [data-testid="stAppViewContainer"],
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        .block-container {{
            max-width: 1300px;
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }}
        h1, h2, h3, h4, h5, h6, p, label, span, div,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"] {{
            color: var(--text-dark);
        }}
        .stCaption, .section-sub {{
            color: var(--muted-dark) !important;
        }}

        [data-testid="stTabs"] button {{
            color: #cdd5df;
            border-radius: 10px 10px 0 0;
            padding: 0.5rem 1rem;
            background: transparent !important;
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
            color: #ffffff;
            border-bottom: 2px solid var(--primary-2);
        }}

        [data-testid="stSelectbox"],
        [data-testid="stDateInput"],
        [data-testid="stNumberInput"],
        [data-testid="stTextInput"] {{
            background: transparent;
        }}
        [data-testid="stSelectbox"] > div,
        [data-testid="stDateInput"] > div,
        [data-testid="stNumberInput"] > div,
        [data-testid="stTextInput"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div {{
            background: var(--surface-dark) !important;
            border: 1px solid var(--border-dark) !important;
            border-radius: 12px;
            color: var(--text-dark) !important;
            box-shadow: none !important;
        }}
        [data-baseweb="select"] input,
        [data-baseweb="select"] span,
        [data-baseweb="select"] div,
        [data-baseweb="input"] input,
        [data-baseweb="input"] div,
        [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {{
            color: var(--text-dark) !important;
            -webkit-text-fill-color: var(--text-dark) !important;
            caret-color: var(--text-dark) !important;
        }}
        [data-baseweb="select"] svg,
        [data-testid="stDateInput"] svg {{
            fill: var(--text-dark) !important;
            color: var(--text-dark) !important;
        }}
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] * ,
        div[role="listbox"],
        div[role="listbox"] *,
        div[role="option"],
        ul[role="listbox"],
        li[role="option"] {{
            background: var(--surface-dark) !important;
            color: var(--text-dark) !important;
            border-color: var(--border-dark) !important;
            -webkit-text-fill-color: var(--text-dark) !important;
        }}
        div[role="option"]:hover,
        li[role="option"]:hover,
        div[role="option"][aria-selected="true"],
        li[role="option"][aria-selected="true"] {{
            background: #1B2440 !important;
            color: var(--text-dark) !important;
        }}

        .stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {{
            background: var(--primary) !important;
            color: #FFFFFF !important;
            border: 1px solid var(--primary) !important;
            border-radius: 12px;
            padding: 0.55rem 1rem;
            font-weight: 700;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
            transition: all 0.2s ease;
        }}
        .stButton > button *, .stDownloadButton > button *, div[data-testid="stFormSubmitButton"] > button * {{
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {{
            background: #1D4ED8 !important;
            border-color: #1D4ED8 !important;
            box-shadow: 0 6px 18px rgba(37, 99, 235, 0.45) !important;
        }}
        .stButton > button:active, .stDownloadButton > button:active, div[data-testid="stFormSubmitButton"] > button:active {{
            background: #1E40AF !important;
            border-color: #1E40AF !important;
            transform: scale(0.98);
        }}

        .dark-card {{
            background: linear-gradient(180deg, rgba(21,26,45,0.96) 0%, rgba(15,19,34,0.96) 100%);
            border: 1px solid var(--border-dark);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 6px 24px rgba(0,0,0,0.22);
            min-height: 112px;
        }}
        .dark-card .label {{
            font-size: 0.95rem;
            color: var(--subtle-dark);
            margin-bottom: 0.45rem;
        }}
        .dark-card .value {{
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.1;
            color: #f8fafc;
        }}
        .dark-card .unit {{
            font-size: 1rem;
            color: var(--subtle-dark);
            margin-left: 0.2rem;
        }}
        .dark-card .sub {{
            margin-top: 0.35rem;
            color: #8ce99a;
            font-size: 0.9rem;
        }}
        .section-wrap {{
            margin-bottom: 0.8rem;
        }}
        .section-title {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.15rem;
        }}
        .section-sub {{
            font-size: 0.98rem;
            margin-bottom: 1rem;
        }}

        /* DataFrame / table readability */
        [data-testid="stDataFrame"] {{
            border: 1px solid var(--border-dark);
            border-radius: 16px;
            overflow: hidden;
            background: var(--surface-dark-2) !important;
        }}
        [data-testid="stDataFrame"] [role="grid"],
        [data-testid="stDataFrame"] [role="table"],
        [data-testid="stDataFrame"] table {{
            background: var(--surface-dark-2) !important;
            color: var(--text-dark) !important;
        }}
        [data-testid="stDataFrame"] [role="columnheader"],
        [data-testid="stDataFrame"] thead th {{
            background: #111827 !important;
            color: var(--text-dark) !important;
            border-bottom: 1px solid var(--border-dark) !important;
            font-weight: 700 !important;
        }}
        [data-testid="stDataFrame"] [role="gridcell"],
        [data-testid="stDataFrame"] tbody td {{
            background: var(--surface-dark-2) !important;
            color: var(--text-dark) !important;
            border-color: var(--border-dark) !important;
        }}

        /* Desktop / PC only: avoid applying to touch-first tablets such as iPad */
        @media (min-width: {PC_BREAKPOINT_PX}px) and (hover: hover) and (pointer: fine) {{
            .stApp {{
                background: var(--bg-light) !important;
                color: var(--text-light) !important;
            }}
            [data-testid="stAppViewContainer"],
            [data-testid="stHeader"] {{
                background: var(--bg-light) !important;
            }}
            [data-testid="stSidebar"],
            [data-testid="stSidebar"] > div {{
                background: var(--bg-light) !important;
                border-right: 1px solid var(--border-light-2);
            }}
            h1, h2, h3, h4, h5, h6, p, label, span, div,
            [data-testid="stMarkdownContainer"],
            [data-testid="stCaptionContainer"] {{
                color: var(--text-light) !important;
            }}
            .section-sub,
            .dark-card .label,
            .dark-card .unit,
            .stCaption {{
                color: var(--muted-light) !important;
            }}
            [data-testid="stTabs"] button {{
                color: var(--muted-light) !important;
            }}
            [data-testid="stTabs"] button[aria-selected="true"] {{
                color: var(--text-light) !important;
                border-bottom: 2px solid var(--text-light) !important;
            }}
            [data-testid="stSelectbox"] > div,
            [data-testid="stDateInput"] > div,
            [data-testid="stNumberInput"] > div,
            [data-testid="stTextInput"] > div,
            [data-baseweb="select"] > div,
            [data-baseweb="input"] > div {{
                background: var(--bg-light) !important;
                border: 1px solid var(--border-light) !important;
                color: var(--text-light) !important;
            }}
            [data-baseweb="select"] input,
            [data-baseweb="select"] span,
            [data-baseweb="select"] div,
            [data-baseweb="input"] input,
            [data-baseweb="input"] div,
            [data-testid="stDateInput"] input,
            [data-testid="stNumberInput"] input,
            [data-testid="stTextInput"] input {{
                color: var(--text-light) !important;
                -webkit-text-fill-color: var(--text-light) !important;
                caret-color: var(--text-light) !important;
            }}
            [data-baseweb="select"] svg,
            [data-testid="stDateInput"] svg {{
                fill: var(--text-light) !important;
                color: var(--text-light) !important;
            }}
            div[data-baseweb="popover"],
            div[data-baseweb="popover"] *,
            div[role="listbox"],
            div[role="listbox"] *,
            div[role="option"],
            ul[role="listbox"],
            li[role="option"] {{
                background: var(--bg-light) !important;
                color: var(--text-light) !important;
                border-color: var(--border-light-2) !important;
                -webkit-text-fill-color: var(--text-light) !important;
            }}
            div[role="option"]:hover,
            li[role="option"]:hover,
            div[role="option"][aria-selected="true"],
            li[role="option"][aria-selected="true"] {{
                background: var(--hover-light) !important;
                color: var(--text-light) !important;
            }}
            .stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {{
                background: var(--primary) !important;
                color: #FFFFFF !important;
                border: 1px solid var(--primary) !important;
            }}
            .stButton > button *, .stDownloadButton > button *, div[data-testid="stFormSubmitButton"] > button * {{
                color: #FFFFFF !important;
                -webkit-text-fill-color: #FFFFFF !important;
            }}
            .dark-card {{
                background: var(--surface-light-2) !important;
                border: 1px solid var(--border-light-2) !important;
                box-shadow: 0 4px 14px rgba(17, 24, 39, 0.06) !important;
            }}
            .dark-card .value {{
                color: var(--text-light) !important;
            }}
            .dark-card .sub {{
                color: var(--success) !important;
            }}
            [data-testid="stDataFrame"] {{
                border: 1px solid var(--border-light-2) !important;
                background: var(--bg-light) !important;
            }}
            [data-testid="stDataFrame"] [role="grid"],
            [data-testid="stDataFrame"] [role="table"],
            [data-testid="stDataFrame"] table {{
                background: var(--bg-light) !important;
                color: var(--text-light) !important;
            }}
            [data-testid="stDataFrame"] [role="columnheader"],
            [data-testid="stDataFrame"] thead th {{
                background: #F8FAFC !important;
                color: var(--text-light) !important;
                border-bottom: 1px solid var(--border-light-2) !important;
            }}
            [data-testid="stDataFrame"] [role="gridcell"],
            [data-testid="stDataFrame"] tbody td {{
                background: var(--bg-light) !important;
                color: var(--text-light) !important;
                border-color: var(--border-light-2) !important;
            }}
        }}


        /* Mobile/tablet preview hardening: keep dataframe dark on touch-width layouts */
        @media (max-width: {PC_BREAKPOINT_PX - 1}px) {{
            [data-testid="stDataFrame"],
            [data-testid="stDataFrame"] [role="grid"],
            [data-testid="stDataFrame"] [role="table"],
            [data-testid="stDataFrame"] table,
            [data-testid="stDataFrame"] [role="columnheader"],
            [data-testid="stDataFrame"] thead th,
            [data-testid="stDataFrame"] [role="gridcell"],
            [data-testid="stDataFrame"] tbody td {{
                background: var(--surface-dark-2) !important;
                color: var(--text-dark) !important;
                border-color: var(--border-dark) !important;
                -webkit-text-fill-color: var(--text-dark) !important;
            }}
            [data-testid="stDataFrame"] [role="columnheader"],
            [data-testid="stDataFrame"] thead th {{
                background: #111827 !important;
            }}
        }}

        /* Mobile + iPad */
        @media (max-width: {PC_BREAKPOINT_PX - 1}px) {{
            .block-container {{ padding-left: 0.8rem; padding-right: 0.8rem; }}
            .dark-card {{ min-height: 100px; padding: 0.9rem; }}
            .dark-card .value {{ font-size: 1.7rem; }}
            .section-title {{ font-size: 1.7rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_title(title: str, subtitle: str = ""):
    subtitle_html = f'<div class="section-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="section-wrap">
            <div class="section-title">{title}</div>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_row(cards):
    cols = st.columns(len(cards))
    for col, (label, value, unit, sub) in zip(cols, cards):
        with col:
            sub_html = f'<div class="sub">{sub}</div>' if sub else '<div class="sub">&nbsp;</div>'
            st.markdown(
                f"""
                <div class="dark-card">
                    <div class="label">{label}</div>
                    <div><span class="value">{value}</span><span class="unit">{unit}</span></div>
                    {sub_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

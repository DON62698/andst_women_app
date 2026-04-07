
import streamlit as st

def apply_theme():
    st.markdown("""
    <style>

    /* ===== Mobile + iPad = DARK ===== */
    @media (max-width: 1024px) {

        .stApp {
            background-color: #0E1117 !important;
            color: #FFFFFF !important;
        }

        div[data-testid="stAppViewContainer"] {
            background-color: #0E1117 !important;
        }

        section[data-testid="stSidebar"] {
            background-color: #0E1117 !important;
            color: #FFFFFF !important;
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataFrame"] div {
            background-color: #0E1117 !important;
            color: #FFFFFF !important;
        }

        div[data-baseweb="select"],
        div[data-baseweb="input"],
        textarea {
            background-color: #262730 !important;
            color: #FFFFFF !important;
        }

        div[data-baseweb="select"] * {
            color: #FFFFFF !important;
        }

        input::placeholder,
        textarea::placeholder {
            color: #AAAAAA !important;
        }
    }

    /* ===== PC ONLY = WHITE ===== */
    @media (min-width: 1025px) {

        .stApp {
            background-color: #FFFFFF !important;
            color: #111111 !important;
        }

        div[data-testid="stAppViewContainer"] {
            background-color: #FFFFFF !important;
        }

        section[data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            color: #111111 !important;
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataFrame"] div {
            background-color: #FFFFFF !important;
            color: #111111 !important;
        }

        div[data-baseweb="select"],
        div[data-baseweb="input"],
        textarea {
            background-color: #FFFFFF !important;
            color: #111111 !important;
        }

        div[data-baseweb="select"] * {
            color: #111111 !important;
        }

        input::placeholder,
        textarea::placeholder {
            color: #888888 !important;
        }
    }

    </style>
    """, unsafe_allow_html=True)

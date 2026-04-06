
import streamlit as st

def set_pixel_background():
    st.markdown("""
        <style>
        .stApp {
            background-image: url('https://cdn.openai.com/chat-assets/user-uploads/file_0000000027ac61faa89173c216cc3682/A_graphic_design_advertisement_poster_for_%22niko_an.png');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }
        </style>
    """, unsafe_allow_html=True)

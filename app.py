import streamlit as st
import os
import pandas as pd
import json
from ocr_process import process_single_pdf
from excel_handler import append_to_excel

st.set_page_config(page_title="Smart Cash Flow OCR", layout="wide")

st.title("💰 Smart Cash Flow OCR")
st.markdown("---")

# Sidebar Configuration
st.sidebar.header("Settings")
source_path = st.sidebar.text_input("Source PDF Path", value=os.getcwd() + r"\source")
master_path = st.sidebar.text_input("AC Master Path", value=os.getcwd() + r"\Master\AC_Master.xlsx")
export_path = st.sidebar.text_input("Export Excel Path", value=os.getcwd() + r"\output\CashFlow_Report.xlsx")

ocr_engine = st.sidebar.selectbox("OCR Engine", ["Tesseract", "Typhoon"])
api_key = ""
if ocr_engine == "Typhoon":
    api_key = st.sidebar.text_input("Typhoon API Key", type="password")
    if not api_key:
        # Try loading from config if exists
        config_path = "config.json"
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                api_key = json.load(f).get("API_KEY", "")

# Main UI
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📁 Process PDFs")
    if st.button("🔍 Scan Source Folder"):
        if os.path.exists(source_path):
            files = [f for f in os.listdir(source_path) if f.lower().endswith(".pdf")]
            st.session_state.pdf_files = files
            st.success(f"Found {len(files)} PDF files.")
        else:
            st.error("Invalid source path.")

    if "pdf_files" in st.session_state:
        selected_file = st.selectbox("Select PDF to process", st.session_state.pdf_files)
        
        if st.button("🚀 Run OCR"):
            with st.spinner(f"Processing {selected_file}..."):
                pdf_full_path = os.path.join(source_path, selected_file)
                results, raw_text = process_single_pdf(
                    pdf_full_path, 
                    engine=ocr_engine, 
                    api_key=api_key, 
                    master_path=master_path
                )
                st.session_state.current_results = results
                st.session_state.raw_text = raw_text
                st.success("OCR Completed!")

with col2:
    st.subheader("📄 Raw Text Preview")
    if "raw_text" in st.session_state:
        st.text_area("OCR Output", st.session_state.raw_text, height=300)

st.markdown("---")
st.subheader("📊 Data Validation & Export")

if "current_results" in st.session_state:
    df = pd.DataFrame(st.session_state.current_results)
    
    # Data Editor
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    
    if st.button("💾 Export & Append to Excel"):
        msg = append_to_excel(edited_df, export_path)
        st.info(msg)
else:
    st.info("Run OCR to see data here.")

# Style
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    .stTextInput>div>div>input {
        background-color: #f0f2f6;
    }
</style>
""", unsafe_allow_html=True)

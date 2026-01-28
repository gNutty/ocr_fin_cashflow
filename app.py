import streamlit as st
import os
import pandas as pd
import json
from ocr_process import process_single_pdf
from excel_handler import append_to_excel

st.set_page_config(page_title="Smart Cash Flow OCR", layout="wide")

st.title("💰 Smart Cash Flow OCR")
st.markdown("---")

# Load API Key from config.json if it exists
config_api_key = ""
if os.path.exists("config.json"):
    try:
        with open("config.json", "r") as f:
            config_api_key = json.load(f).get("API_KEY", "")
    except Exception:
        pass

# Sidebar Configuration
st.sidebar.header("Settings")
source_path = st.sidebar.text_input("Source PDF Path", value=os.getcwd() + r"\source")
master_path = st.sidebar.text_input("AC Master Path", value=os.getcwd() + r"\Master\AC_Master.xlsx")
export_path = st.sidebar.text_input("Export Excel Path", value=os.getcwd() + r"\output\CashFlow_Report.xlsx")

ocr_engine = st.sidebar.selectbox("OCR Engine", ["Tesseract", "Typhoon"])
api_key = ""

if ocr_engine == "Typhoon":
    if config_api_key:
        api_key = config_api_key
        st.sidebar.success("✅ API Key loaded from config.json")
    else:
        api_key = st.sidebar.text_input("Typhoon API Key", type="password")

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
        options = ["All Files"] + st.session_state.pdf_files
        selected_file = st.selectbox("Select PDF to process", options)
        
        if st.button("🚀 Run OCR"):
            if ocr_engine == "Typhoon" and not api_key:
                st.error("Please provide a Typhoon API Key.")
            else:
                all_results = []
                all_raw_text = ""
                
                files_to_process = []
                if selected_file == "All Files":
                    files_to_process = st.session_state.pdf_files
                else:
                    files_to_process = [selected_file]
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, file in enumerate(files_to_process):
                    status_text.text(f"Processing {idx+1}/{len(files_to_process)}: {file}...")
                    pdf_full_path = os.path.join(source_path, file)
                    
                    try:
                        results, raw_text = process_single_pdf(
                            pdf_full_path, 
                            engine=ocr_engine, 
                            api_key=api_key, 
                            master_path=master_path
                        )
                        # Add filename to each entry for clarity in batch results
                        for res in results:
                            res["Source File"] = file
                            
                        all_results.extend(results)
                        all_raw_text += f"=== File: {file} ===\n{raw_text}\n\n"
                    except Exception as e:
                        st.error(f"Error processing {file}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(files_to_process))
                
                st.session_state.current_results = all_results
                st.session_state.raw_text = all_raw_text
                status_text.text("OCR Completed!")
                st.success(f"Processed {len(files_to_process)} file(s).")

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
    /* Darken text in inputs for better visibility */
    .stTextInput>div>div>input {
        background-color: #f0f2f6 !important;
        color: #000000 !important;
    }
    /* Specifically for OCR Engine (Selectbox) - keep text white on dark background */
    .stSelectbox>div>div>div {
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

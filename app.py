import streamlit as st
import os
import pandas as pd
import json
from ocr_process import process_single_pdf, lookup_master
from excel_handler import append_to_excel
import urllib.parse
import base64

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
    # Prepare data for display
    display_df = pd.DataFrame(st.session_state.current_results)
    
    # Ensure all columns exist
    for col in ["A/C No", "Document Date", "Reference No", "Total Value", "Bank Name", "Company Name", "Transaction", "Source File", "Page"]:
        if col not in display_df.columns:
            display_df[col] = None

    # Reorder columns for better UX
    cols = ["A/C No", "Bank Name", "Company Name", "Document Date", "Reference No", "Total Value", "Transaction", "Source File", "Page"]
    display_df = display_df[cols]

    # Handle PDF Link construction
    # Handle PDF Link construction
    def make_pdf_link(row):
        source_file = str(row["Source File"]) if row["Source File"] else ""
        page_num = row["Page"] if pd.notna(row["Page"]) else 1
        
        file_path = os.path.join(source_path, source_file)
        file_url = f"file:///{urllib.parse.quote(file_path.replace('\\', '/'))}#page={page_num}"
        return file_url

    # Ensure Page is filled so we don't have issues
    display_df["Page"] = display_df["Page"].fillna(1).astype(int)
    
    # Apply link creation and FORCE string type to avoid Streamlit error
    display_df["PDF Link"] = display_df.apply(make_pdf_link, axis=1).astype(str)

    # UI for Data Validation
    t1, t2 = st.tabs(["📝 Edit Table", "🔍 PDF Preview"])
    
    with t1:
        st.info("💡 **Tip:** Edit **A/C No** to auto-lookup Bank/Company. PDF Link may be blocked by browser; use the **PDF Preview** tab for a reliable view.")
        edited_df = st.data_editor(
            display_df,
            column_config={
                "PDF Link": st.column_config.LinkColumn(
                    "PDF Link",
                    help="Click to open PDF at the specific page. Note: Modern browsers block local file links. Use the PDF Preview tab for a built-in view.",
                    validate="^file://.*",
                    display_text="Open in New Tab"
                ),
                "Page": st.column_config.NumberColumn(disabled=True),
                "Source File": st.column_config.TextColumn(disabled=True),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor"
        )

    with t2:
        if not edited_df.empty:
            # Let user select a row to preview
            row_idx = st.selectbox("Select row to preview PDF page", 
                                   range(len(edited_df)), 
                                   format_func=lambda i: f"Row {i+1}: {edited_df.iloc[i]['Source File']} (P.{edited_df.iloc[i]['Page']})")
            
            if row_idx is not None:
                target_row = edited_df.iloc[row_idx]
                target_pdf = os.path.join(source_path, str(target_row["Source File"]))
                
                # Safely get page number, default to 1 if missing or invalid
                raw_page = target_row.get("Page")
                try:
                    target_page = int(raw_page) if raw_page and pd.notna(raw_page) else 1
                except ValueError:
                    target_page = 1
                
                if os.path.exists(target_pdf):
                    try:
                        with open(target_pdf, "rb") as f:
                            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                        
                        # Use iframe with #page=N
                        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#page={target_page}" width="100%" height="800" type="application/pdf"></iframe>'
                        st.markdown(pdf_display, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Error loading preview: {e}")
                else:
                    st.warning(f"File not found: {target_pdf}")
        else:
            st.info("No data available for preview.")

    # Auto-matching logic for A/C No
    if not edited_df.equals(display_df):
        needs_update = False
        new_results = edited_df.to_dict('records')
        
        for i, row in enumerate(new_results):
            # Check if A/C No was changed or if Bank/Company is empty but A/C No exists
            old_ac = display_df.iloc[i]["A/C No"] if i < len(display_df) else None
            new_ac = row["A/C No"]
            
            if (new_ac and new_ac != old_ac) or (new_ac and not row["Bank Name"]):
                bank, company = lookup_master(new_ac, master_path)
                if bank or company:
                    new_results[i]["Bank Name"] = bank
                    new_results[i]["Company Name"] = company
                    needs_update = True
        
        if needs_update:
            st.session_state.current_results = new_results
            st.rerun()

    if st.button("💾 Export & Append to Excel"):
        # Remove the helper "PDF Link" column before exporting
        export_df = edited_df.drop(columns=["PDF Link"])
        msg = append_to_excel(export_df, export_path)
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

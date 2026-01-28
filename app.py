import streamlit as st
import os
import pandas as pd
import json
from ocr_process import process_single_pdf, lookup_master
from excel_handler import append_to_excel
import urllib.parse
import base64
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_path

# --- Helper Functions ---
def render_pdf(file_path, page_num=1):
    """Render a specific page of a PDF as an image."""
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            st.error(f"File not found: {file_path}")
            return

        # Convert PDF to image
        images = convert_from_path(file_path, first_page=page_num, last_page=page_num)
        if images:
            st.image(images[0], caption=f"Page {page_num} of {os.path.basename(file_path)}", use_container_width=True)
        else:
            st.error("Could not render PDF page.")
    except Exception as e:
        st.error(f"Error rendering PDF: {e}")
        # Fallback to iframe if pdf2image fails (e.g. missing poppler)
        try:
            with open(file_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#page={page_num}" width="100%" height="800" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        except Exception as fallback_error:
            st.error(f"Fallback preview failed: {fallback_error}")

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

if "current_results" in st.session_state and st.session_state.current_results:
    # Prepare data for display
    display_df = pd.DataFrame(st.session_state.current_results)
    
    # Reset index to ensure iloc alignment
    display_df = display_df.reset_index(drop=True)
    
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

    # --- Split Layout: Data Table (Left) & PDF Preview (Right) ---
    col1, col2 = st.columns([0.65, 0.35], gap="medium")

    with col1:
        st.subheader("Edit Data")
        
        # Add 'Select' column for robust row selection
        if "Select" not in display_df.columns:
            display_df.insert(0, "Select", False)
        
        # Configure columns
        column_config = {
            "Select": st.column_config.CheckboxColumn("View", help="Check to view PDF", width="small"),
            "PDF Link": st.column_config.LinkColumn(
                "PDF Link",
                help="Open in new tab",
                validate="^file://.*",
                display_text="Open"
            ),
            "Page": st.column_config.NumberColumn(disabled=True),
            "Source File": st.column_config.TextColumn(disabled=True),
        }
        
        # Display Data Editor
        edited_df = st.data_editor(
            display_df,
            column_config=column_config,
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor",
            hide_index=True  # Hide default index to save space
        )
        
        # Detect Selection for Preview
        target_source = None
        target_page = 1
        
        # Check if any row is selected via checkbox
        # We use the filtered dataframe to find truthy 'Select' values
        selected_rows = edited_df[edited_df["Select"] == True]
        
        if not selected_rows.empty:
            # Take the last selected row
            current_row = selected_rows.iloc[-1]
            target_source = current_row["Source File"]
            target_page_raw = current_row["Page"]
            try:
                target_page = int(target_page_raw) if pd.notna(target_page_raw) else 1
            except:
                target_page = 1

    with col2:
        st.subheader("PDF Preview")
        if target_source:
             target_pdf_path = os.path.join(source_path, str(target_source))
             st.markdown(f"**File:** `{target_source}`")
             st.markdown(f"**Page:** `{target_page}`")
             render_pdf(target_pdf_path, target_page)
        else:
            st.info("Select a row in the 'View' column to preview the PDF.")

    # --- Auto-Lookup Logic ---
    # Iterate to check for missing bank/company info
    for index, row in edited_df.iterrows():
        ac_no = str(row.get("A/C No", "")).strip()
        bank_name = str(row.get("Bank Name", "")).strip()
        comp_name = str(row.get("Company Name", "")).strip()
        
        if ac_no and (not bank_name or not comp_name):
             match = lookup_master(ac_no)
             if match:
                 updated = False
                 if not bank_name and match["Bank Name"]:
                     edited_df.at[index, "Bank Name"] = match["Bank Name"]
                     updated = True
                 if not comp_name and match["Company Name"]:
                     edited_df.at[index, "Company Name"] = match["Company Name"]
                     updated = True
                 
                 # If we updated the dataframe, we might need to rerun to show it?
                 # Streamlit's data_editor return value is the *current* state. 
                 # Modifying it here won't update the UI immediately unless we force a rerun or rely on next cycle.
                 # However, usually we should separate "display" from "edit".
                 # For now, let's just accept the edit for export. 

    st.divider()
    if st.button("💾 Export & Append to Excel"):
        # Remove the helper columns before exporting
        cols_to_drop = [c for c in ["Select", "PDF Link"] if c in edited_df.columns]
        export_df = edited_df.drop(columns=cols_to_drop)
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

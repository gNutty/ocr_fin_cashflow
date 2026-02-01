import streamlit as st

# CRITICAL: st.set_page_config MUST be the first Streamlit command
st.set_page_config(page_title="Smart Cash Flow OCR", page_icon="💰", layout="wide")

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
import db_manager as db

# --- Initialization ---
db.init_db()

# --- Caching for Performance ---
@st.cache_data(ttl=60)
def get_cached_filter_options():
    """Cache filter options for 60 seconds."""
    return db.get_filter_options()

# --- Helper Functions ---
def render_pdf(file_path, page_num=1):
    """Render a specific page of a PDF as an image."""
    try:
        if not os.path.exists(file_path):
            st.error(f"File not found: {file_path}")
            return

        images = convert_from_path(file_path, first_page=page_num, last_page=page_num)
        if images:
            st.image(images[0], caption=f"Page {page_num} of {os.path.basename(file_path)}", use_container_width=True)
        else:
            st.error("Could not render PDF page.")
    except Exception as e:
        st.error(f"Error rendering PDF: {e}")
        try:
            with open(file_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#page={page_num}" width="100%" height="800" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        except Exception as fallback_error:
            st.error(f"Fallback preview failed: {fallback_error}")

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
st.sidebar.header("⚙️ Settings")
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

# --- Tabs Implementation ---
tab_process, tab_db = st.tabs(["🚀 OCR Processing", "📊 Database Dashboard"])

# ==========================================
# TAB 1: OCR Processing
# ==========================================
with tab_process:
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
            options = ["Select All"] + st.session_state.pdf_files
            selected_options = st.multiselect("Select PDF(s) to process", options, default=["Select All"])
            
            if "Select All" in selected_options:
                selected_files = st.session_state.pdf_files
            else:
                selected_files = selected_options
            
            col_actions, col_status = st.columns([0.4, 0.6])
            with col_actions:
                run_btn = st.button("🚀 Run OCR", use_container_width=True)
                
            if run_btn:
                if ocr_engine == "Typhoon" and not api_key:
                    st.error("Please provide a Typhoon API Key.")
                elif not selected_files:
                    st.warning("Please select at least one file to process.")
                else:
                    all_results = []
                    all_raw_text = ""
                    
                    files_to_process = selected_files
                    
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
            # Use expander for long text (Best Practice #6)
            with st.expander("View Raw OCR Output", expanded=False):
                st.text_area("OCR Output", st.session_state.raw_text, height=300)

    st.markdown("---")
    st.subheader("📊 Data Validation & Export")

    if "current_results" in st.session_state and st.session_state.current_results:
        display_df = pd.DataFrame(st.session_state.current_results)
        display_df = display_df.reset_index(drop=True)
        # Ensure all columns exist
        for col in ["A/C No", "Bank Name", "Company Name", "Currency", "Document Date", "Reference No", "Total Value", "Transaction", "Source File", "Page"]:
            if col not in display_df.columns:
                display_df[col] = None

        # Reorder columns for better UX
        cols = ["A/C No", "Bank Name", "Company Name", "Currency", "Document Date", "Reference No", "Total Value", "Transaction", "Source File", "Page"]
        display_df = display_df[cols]

        def make_pdf_link(row):
            source_file = str(row["Source File"]) if row["Source File"] else ""
            page_num = row["Page"] if pd.notna(row["Page"]) else 1
            file_path = os.path.join(source_path, source_file)
            file_url = f"file:///{urllib.parse.quote(file_path.replace('\\', '/'))}#page={page_num}"
            return file_url

        display_df["Page"] = display_df["Page"].fillna(1).astype(int)
        
        col1_res, col2_res = st.columns([0.65, 0.35], gap="medium")

        with col1_res:
            st.subheader("Edit Data")
            
            if "Select" not in display_df.columns:
                 display_df.insert(0, "Select", False)
                 for res in st.session_state.current_results:
                     if "Select" not in res:
                         res["Select"] = False
            
            def on_editor_change():
                if "data_editor" not in st.session_state:
                    return
                
                edited_rows = st.session_state["data_editor"]["edited_rows"]
                new_selection_idx = None
                
                for idx, changes in edited_rows.items():
                    if "Select" in changes and changes["Select"] is True:
                         new_selection_idx = int(idx)
                         break
                
                if new_selection_idx is not None:
                    for i, res in enumerate(st.session_state.current_results):
                        res["Select"] = (i == new_selection_idx)
                
                for idx, changes in edited_rows.items():
                     idx = int(idx)
                     for k, v in changes.items():
                         if k != "Select":
                             st.session_state.current_results[idx][k] = v
            # Re-build display_df from current_results
            display_df = pd.DataFrame(st.session_state.current_results)
            display_df = display_df.reset_index(drop=True)
            for col in ["A/C No", "Bank Name", "Company Name", "Currency", "Document Date", "Reference No", "Total Value", "Transaction", "Source File", "Page", "Select"]:
                if col not in display_df.columns:
                     if col == "Select": display_df[col] = False
                     else: display_df[col] = None
            
            if "Total Value" in display_df.columns:
                display_df["Total Value"] = pd.to_numeric(display_df["Total Value"].replace('', pd.NA), errors='coerce')
                display_df["Total Value"] = display_df["Total Value"].apply(
                    lambda x: f"{x:,.2f}" if pd.notna(x) else ""
                )
            
            display_df["Page"] = display_df["Page"].fillna(1).astype(int)
            display_df["PDF Link"] = display_df.apply(make_pdf_link, axis=1).astype(str)
            
            cols_order = ["Select", "A/C No", "Bank Name", "Company Name", "Currency", "Document Date", "Reference No", "Total Value", "Transaction", "Source File", "Page", "PDF Link"]
            display_df = display_df[[c for c in cols_order if c in display_df.columns]]

            column_config = {
                "Select": st.column_config.CheckboxColumn("View", help="Check to view PDF", width="small"),
                "PDF Link": st.column_config.LinkColumn("PDF Link", help="Open in new tab", validate="^file://.*", display_text="Open"),
                "Page": st.column_config.NumberColumn(disabled=True),
                "Source File": st.column_config.TextColumn(disabled=True),
                "Total Value": st.column_config.TextColumn("Total Value", help="Amount with 2 decimal places"),
            }
            
            edited_df = st.data_editor(
                display_df,
                column_config=column_config,
                num_rows="fixed",
                use_container_width=True,
                height=600,
                key="data_editor",
                hide_index=True,
                on_change=on_editor_change
            )

            target_source = None
            target_page = 1
            selected_rows = edited_df[edited_df["Select"] == True]
            
            if not selected_rows.empty:
                current_row = selected_rows.iloc[-1]
                target_source = current_row["Source File"]
                target_page_raw = current_row["Page"]
                try:
                    target_page = int(target_page_raw) if pd.notna(target_page_raw) else 1
                except:
                    target_page = 1

        with col2_res:
            st.subheader("PDF Preview")
            if target_source:
                 target_pdf_path = os.path.join(source_path, str(target_source))
                 render_pdf(target_pdf_path, target_page)
            else:
                st.info("Select a row in the 'View' column to preview the PDF.")
        # Master Lookup Logic
        for index, row in edited_df.iterrows():
            ac_no = str(row.get("A/C No", "")).strip()
            bank_name = str(row.get("Bank Name", "")).strip()
            comp_name = str(row.get("Company Name", "")).strip()
            currency = str(row.get("Currency", "")).strip()
            
            if ac_no and (not bank_name or not comp_name or not currency):
                 match_bank, match_comp, match_curr = lookup_master(ac_no, master_path)
                 if match_bank:
                     if not bank_name: edited_df.at[index, "Bank Name"] = match_bank
                     if not comp_name: edited_df.at[index, "Company Name"] = match_comp
                     if not currency: edited_df.at[index, "Currency"] = match_curr

        st.divider()
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("💾 Export & Append to Excel"):
                with st.spinner("Exporting to Excel..."):
                    cols_to_drop = [c for c in ["Select", "PDF Link"] if c in edited_df.columns]
                    export_df = edited_df.drop(columns=cols_to_drop)
                    msg = append_to_excel(export_df, export_path)
                st.toast("Export complete!", icon="✅")
                st.info(msg)
        
        with col_btn2:
            if st.button("🗄️ Save to Database"):
                with st.spinner("Saving to database..."):
                    cols_to_drop = [c for c in ["Select", "PDF Link"] if c in edited_df.columns]
                    save_df = edited_df.drop(columns=cols_to_drop)
                    count, msg = db.save_records(save_df)
                if count > 0:
                    st.toast(f"Saved {count} records!", icon="✅")
                    st.success(msg)
                    # Clear cache so Dashboard gets fresh data
                    get_cached_filter_options.clear()
                else:
                    st.error(msg)
    else:
        st.info("Run OCR to see data here.")

# ==========================================
# TAB 2: Database Dashboard
# ==========================================
with tab_db:
    st.subheader("🗃️ Historical Data Navigator")
    
    with st.expander("🔍 Search & Filter Options", expanded=False):
        # Use st.form to prevent rerun on every filter change (Best Practice #5)
        with st.form("filter_form"):
            banks, companies, currencies, years, months = get_cached_filter_options()
            
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                f_bank = st.selectbox("Filter by Bank", banks, key="f_bank")
            with col_f2:
                f_company = st.selectbox("Filter by Company", companies, key="f_company")
            with col_f3:
                f_currency = st.selectbox("Filter by Currency", currencies, key="f_currency")
                
            st.markdown("##### 📅 Date Filtering")
            date_filter_type = st.radio("Filter Type", ["All", "Date Range", "Year & Month"], horizontal=True)
            
            row_d1, row_d2 = st.columns(2)
            
            f_start_date = None
            f_end_date = None
            
            if date_filter_type == "Date Range":
                with row_d1:
                    f_start_date = st.date_input("Start Date", value=None)
                with row_d2:
                    f_end_date = st.date_input("End Date", value=None)
            
            elif date_filter_type == "Year & Month":
                with row_d1:
                    f_year = st.selectbox("Year", years)
                with row_d2:
                    f_month = st.selectbox("Month", months)
                    
                if f_year != "All":
                    if f_month != "All":
                        import calendar
                        # Get last day of selected month
                        last_day = calendar.monthrange(int(f_year), int(f_month))[1]
                        f_start_date = f"{f_year}-{f_month}-01"
                        f_end_date = f"{f_year}-{f_month}-{last_day}"
                    else:
                        f_start_date = f"{f_year}-01-01"
                        f_end_date = f"{f_year}-12-31"
            
            apply_btn = st.form_submit_button("🔍 Apply Filters", use_container_width=True)
    
    # Initialize filter state
    if "applied_bank" not in st.session_state:
        st.session_state.applied_bank = "All"
    if "applied_company" not in st.session_state:
        st.session_state.applied_company = "All"
    if "applied_currency" not in st.session_state:
        st.session_state.applied_currency = "All"
        
    if apply_btn:
        st.session_state.applied_bank = f_bank
        st.session_state.applied_company = f_company
        st.session_state.applied_currency = f_currency
        st.session_state.applied_start_date = f_start_date
        st.session_state.applied_end_date = f_end_date
        
    hist_df = db.load_records(
        bank=st.session_state.applied_bank, 
        company=st.session_state.applied_company,
        currency=st.session_state.applied_currency,
        start_date=st.session_state.get("applied_start_date"),
        end_date=st.session_state.get("applied_end_date")
    )
    
    if not hist_df.empty:
        col_met1, col_met2, col_met3, col_met4 = st.columns([1.5, 2, 1, 1])
        with col_met1:
            st.metric("Total Records", f"{len(hist_df):,}")
        with col_met2:
            total_val = hist_df["Total Value"].sum()
            st.metric("Total Accumulated Value", f"{total_val:,.2f}")
            
        if "Select" not in hist_df.columns:
            hist_df.insert(0, "Select", False)
            
        edited_hist_df = st.data_editor(
            hist_df,
            column_config={
                "Select": st.column_config.CheckboxColumn("🗑️", help="Select to delete", width="small"),
                "id": None,
            },
            use_container_width=True,
            hide_index=True,
            key="db_editor"
        )
        
        col_db1, col_db2 = st.columns(2)
        
        with col_db1:
            selected_to_delete = edited_hist_df[edited_hist_df["Select"] == True]
            if not selected_to_delete.empty:
                # Warning before delete (Best Practice #7)
                st.warning(f"⚠️ You are about to delete {len(selected_to_delete)} record(s). This cannot be undone.")
                if st.button(f"🗑️ Confirm Delete ({len(selected_to_delete)})", type="primary"):
                    with st.spinner("Deleting records..."):
                        ids_to_delete = selected_to_delete["id"].tolist()
                        count = db.delete_records(ids_to_delete)
                    st.toast(f"Deleted {count} records!", icon="🗑️")
                    get_cached_filter_options.clear()
                    st.rerun()
            else:
                st.button("🗑️ Delete Selected", disabled=True)
        
        with col_db2:
            if st.button("📥 Export to New Excel"):
                with st.spinner("Exporting report..."):
                    export_hist = edited_hist_df.drop(columns=["Select"])
                    report_name = f"DB_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    report_path = os.path.join("output", report_name)
                    export_hist.to_excel(report_path, index=False)
                st.toast("Report exported!", icon="📥")
                st.success(f"Report exported to {report_path}")
            
    else:
        st.info("No data found in database. Try saving some OCR results first.")

# Style (Minimal CSS)
st.markdown("""
<style>
    .stButton>button {
        border-radius: 5px;
        height: 3em;
    }
    [data-testid="stDataFrameResizable"], 
    [data-testid="stDataFrame"],
    .dvn-scroller {
        overflow-anchor: none !important;
    }
    .main .block-container {
        overflow-anchor: none !important;
    }
</style>
""", unsafe_allow_html=True)

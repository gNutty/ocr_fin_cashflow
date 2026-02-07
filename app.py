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

@st.cache_data(ttl=60)
def get_ac_master_data(master_path=None, mtime=None):
    """Load Master data from database. Arguments are kept for compatibility but ignored."""
    try:
        return db.get_all_master_records()
    except Exception as e:
        st.error(f"Error loading Master data from DB: {e}")
        return pd.DataFrame()

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
st.sidebar.header("📌 Navigation")
app_mode = st.sidebar.radio("Go to", ["Application", "⚙️ Master Data Management"], label_visibility="collapsed")

if app_mode == "⚙️ Master Data Management":
    st.title("⚙️ Master Data Management")
    st.markdown("Manage Bank Account Mapping (AC Master)")
    
    # --- MASTER DATA MANAGEMENT FUNCTIONALITY ---
    
    # 1. Fetch Data
    master_df = db.get_connection().execute("SELECT * FROM ac_master").fetchall() # Raw check
    # Use pandas for easier handling
    df_master = db.get_all_master_records()
    
    # --- ACTION FORMS ---
    if "master_action" not in st.session_state:
        st.session_state.master_action = None

    # --- VIEW MODE: LIST ---
    if st.session_state.master_action is None:
        # 2. Display Table
        st.subheader("📋 Current Master Records")
        
        # Search box
        search_term = st.text_input("🔍 Search Accounts", "")
        if search_term:
            mask = df_master.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)
            df_display = df_master[mask]
        else:
            df_display = df_master
            
        # Sort dataframe for better display
        if not df_display.empty:
            df_display = df_display.sort_values(by=["BankName", "ACNO"])
            
        # Add Select column if not exists
        if "Select" not in df_display.columns:
            df_display.insert(0, "Select", False)
            
        # Edit/Delete UI
        edited_master_df = st.data_editor(
            df_display,
            column_config={
                "Select": st.column_config.CheckboxColumn("✅", help="Select record", width="small"),
                "id": st.column_config.NumberColumn("ID", help="Record ID", disabled=True, width="small"),
            },
            use_container_width=True,
            hide_index=True,
            key="master_editor",
            disabled=["id", "ACNO", "BankName", "Branch", "Branch NicName", "AccountName", "AccountType", "Currency", "timestamp"] # Make data read-only in table
        )
        
        # Get selected records
        selected_master = edited_master_df[edited_master_df["Select"] == True]
        
        # Action Buttons
        col_mb1, col_mb2, col_mb3 = st.columns([1, 1, 4])
        
        with col_mb1:
            if st.button("✏️ Edit Record", disabled=len(selected_master) != 1, use_container_width=True):
                rec_id = int(selected_master.iloc[0]["id"])
                st.session_state.master_edit_id = rec_id
                st.session_state.master_action = "edit"
                st.rerun()
                
        with col_mb2:
            if st.button("🗑️ Delete", disabled=len(selected_master) == 0, type="primary", use_container_width=True):
                ids_to_del = selected_master["id"].tolist()
                count = db.delete_master_records(ids_to_del)
                st.success(f"Deleted {count} records!")
                get_ac_master_data.clear()
                st.rerun()
                
        with col_mb3:
            if st.button("➕ Add New Record", use_container_width=False):
                st.session_state.master_action = "add"
                st.rerun()

    # --- ADD MODE ---
    elif st.session_state.master_action == "add":
        st.subheader("➕ Add New Account Record")
        st.divider()
        with st.form("add_master_form"):
            c1, c2 = st.columns(2)
            with c1:
                new_ac = st.text_input("A/C No (Required)")
                new_bank = st.text_input("Bank Name")
                new_branch = st.text_input("Branch")
                new_nic = st.text_input("Branch NicName")
            with c2:
                new_name = st.text_input("Account Name")
                new_type = st.text_input("Account Type")
                new_curr = st.text_input("Currency")
            
            col_save, col_cancel = st.columns([1, 1])
            with col_save:
                submitted = st.form_submit_button("💾 Save Record", type="primary", use_container_width=True)
            with col_cancel:
                cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
                
            if submitted:
                if not new_ac:
                    st.error("A/C No is required!")
                else:
                    data = {
                        "ACNO": new_ac, "BankName": new_bank, "Branch": new_branch, 
                        "Branch NicName": new_nic, "AccountName": new_name, 
                        "AccountType": new_type, "Currency": new_curr
                    }
                    success, msg = db.add_master_record(data)
                    if success:
                        st.success(msg)
                        st.session_state.master_action = None
                        get_ac_master_data.clear() # Clear cache
                        st.rerun()
                    else:
                        st.error(msg)
                        
            if cancelled:
                st.session_state.master_action = None
                st.rerun()

    # --- EDIT MODE ---
    elif st.session_state.master_action == "edit":
        # Check if master_edit_id exists
        if "master_edit_id" not in st.session_state or not st.session_state.master_edit_id:
             st.error("No record selected for editing.")
             if st.button("Cancel"):
                 st.session_state.master_action = None
                 st.rerun()
        else:
            edit_id = st.session_state.master_edit_id
            curr_rec = db.get_master_record_by_id(edit_id)
            
            if curr_rec:
                st.subheader(f"✏️ Edit Record: {curr_rec.get('ACNO')}")
                st.divider()
                with st.form("edit_master_form"):
                    c1, c2 = st.columns(2)
                    with c1:
                        e_ac = st.text_input("A/C No", value=curr_rec.get('ACNO'))
                        e_bank = st.text_input("Bank Name", value=curr_rec.get('BankName'))
                        e_branch = st.text_input("Branch", value=curr_rec.get('Branch'))
                        e_nic = st.text_input("Branch NicName", value=curr_rec.get('Branch NicName'))
                    with c2:
                        e_name = st.text_input("Account Name", value=curr_rec.get('AccountName'))
                        e_type = st.text_input("Account Type", value=curr_rec.get('AccountType'))
                        e_curr = st.text_input("Currency", value=curr_rec.get('Currency'))
                    
                    col_save, col_cancel = st.columns([1, 1])
                    with col_save:
                        submitted = st.form_submit_button("💾 Update Record", type="primary", use_container_width=True)
                    with col_cancel:
                        cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
                        
                    if submitted:
                        data = {
                            "ACNO": e_ac, "BankName": e_bank, "Branch": e_branch, 
                            "Branch NicName": e_nic, "AccountName": e_name, 
                            "AccountType": e_type, "Currency": e_curr
                        }
                        success, msg = db.update_master_record(edit_id, data)
                        if success:
                            st.success(msg)
                            st.session_state.master_action = None
                            st.session_state.master_edit_id = None
                            get_ac_master_data.clear()
                            st.rerun()
                        else:
                            st.error(msg)
                    
                    if cancelled:
                        st.session_state.master_action = None
                        st.session_state.master_edit_id = None
                        st.rerun()



    st.stop() # STOP HERE if in Master Data mode

# Sidebar Configuration (Original)
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
tab_process, tab_db, tab_manual, tab_report, tab_balance = st.tabs(["🚀 OCR Processing", "📊 Database Dashboard", "➕ Manual Entry", "📉 Bank Statement By A/C No. Report", "💰 Bank Balance Summary"])

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
                    # Initialize edit mode state if fresh run
                    if "edit_mode" in st.session_state:
                        del st.session_state.edit_mode
                    if "edit_index" in st.session_state:
                         del st.session_state.edit_index
                         
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
        
        # Initialize Edit Mode State
        if "edit_mode" not in st.session_state:
            st.session_state.edit_mode = False
        if "edit_index" not in st.session_state:
            st.session_state.edit_index = -1

        col1_res, col2_res = st.columns([0.65, 0.35], gap="medium")

        # Define these variables early so they are available for PDF Preview
        target_source = None
        target_page = 1

        with col1_res:
            col_head, col_edit_btn, col_del_btn = st.columns([0.6, 0.2, 0.2])
            with col_head:
                st.subheader("Edit Data")
            
            # --- VIEW MODE: TABLE ---
            if not st.session_state.edit_mode:
                if "Select" not in display_df.columns:
                     display_df.insert(0, "Select", False)
                     for res in st.session_state.current_results:
                         if "Select" not in res:
                             res["Select"] = False
                
                # Check for selected row for Edit/Delete Button availability
                selected_indices = [i for i, r in enumerate(st.session_state.current_results) if r.get("Select", False)]
                is_selected_one = len(selected_indices) == 1
                is_selected_any = len(selected_indices) > 0
                
                with col_edit_btn:
                    if st.button("✏️ Edit Record", disabled=not is_selected_one, use_container_width=True):
                        st.session_state.edit_mode = True
                        idx = selected_indices[0]
                        st.session_state.edit_index = idx
                        
                        # FORCE INIT SESSION STATE FOR EDIT FORM
                        # This ensures valuable are populated even if re-entering the same record
                        rec = st.session_state.current_results[idx]
                        st.session_state[f"edit_ac_{idx}"] = rec.get("A/C No", "")
                        st.session_state[f"edit_bank_{idx}"] = rec.get("Bank Name", "")
                        st.session_state[f"edit_comp_{idx}"] = rec.get("Company Name", "")
                        st.session_state[f"edit_curr_{idx}"] = rec.get("Currency", "")
                        st.session_state[f"edit_date_{idx}"] = pd.to_datetime(rec.get("Document Date")) if rec.get("Document Date") else pd.Timestamp.now()
                        st.session_state[f"edit_ref_{idx}"] = rec.get("Reference No", "")
                        st.session_state[f"edit_total_{idx}"] = float(rec.get("Total Value", 0.0)) if rec.get("Total Value") else 0.0
                        st.session_state[f"edit_trans_{idx}"] = rec.get("Transaction", "DEBIT")
                        
                        st.rerun()

                with col_del_btn:
                    if st.button("🗑️ Delete Record", disabled=not is_selected_any, type="primary", use_container_width=True):
                         # Logic to delete selected
                         # Filter out indices in reverse order to avoid shifting issues
                         indices_to_delete = sorted(selected_indices, reverse=True)
                         for idx in indices_to_delete:
                             st.session_state.current_results.pop(idx)
                         
                         st.toast(f"Deleted {len(indices_to_delete)} record(s)!", icon="🗑️")
                         st.rerun()

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
    
                selected_rows = edited_df[edited_df["Select"] == True]
                
                if not selected_rows.empty:
                    current_row = selected_rows.iloc[-1]
                    target_source = current_row["Source File"]
                    target_page_raw = current_row["Page"]
                    try:
                        target_page = int(target_page_raw) if pd.notna(target_page_raw) else 1
                    except:
                        target_page = 1
                        
                # Master Lookup Logic for Inline Edits
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
            
            # --- EDIT MODE: FORM ---
            else:
                idx = st.session_state.edit_index
                if idx < 0 or idx >= len(st.session_state.current_results):
                     # Error state, fallback
                     st.session_state.edit_mode = False
                     st.rerun()
                
                record = st.session_state.current_results[idx]
                
                # Set target source for PDF preview based on editing record
                target_source = record.get("Source File")
                try:
                    target_page = int(record.get("Page", 1))
                except:
                    target_page = 1

                # Navigation Controls (Above Form)
                nav_col1, nav_col2, nav_col3 = st.columns([0.2, 0.6, 0.2])
                
                with nav_col1:
                    if st.button("⬅️ Previous", disabled=(idx <= 0), use_container_width=True):
                        st.session_state.edit_index -= 1
                        new_idx = st.session_state.edit_index
                        
                        # FORCE INIT SESSION STATE
                        rec = st.session_state.current_results[new_idx]
                        st.session_state[f"edit_ac_{new_idx}"] = rec.get("A/C No", "")
                        st.session_state[f"edit_bank_{new_idx}"] = rec.get("Bank Name", "")
                        st.session_state[f"edit_comp_{new_idx}"] = rec.get("Company Name", "")
                        st.session_state[f"edit_curr_{new_idx}"] = rec.get("Currency", "")
                        st.session_state[f"edit_date_{new_idx}"] = pd.to_datetime(rec.get("Document Date")) if rec.get("Document Date") else pd.Timestamp.now()
                        st.session_state[f"edit_ref_{new_idx}"] = rec.get("Reference No", "")
                        st.session_state[f"edit_total_{new_idx}"] = float(rec.get("Total Value", 0.0)) if rec.get("Total Value") else 0.0
                        st.session_state[f"edit_trans_{new_idx}"] = rec.get("Transaction", "DEBIT")
                        
                        st.rerun()
                
                with nav_col2:
                    st.markdown(f"<p style='text-align: center; padding-top: 10px;'><b>Record {idx+1} of {len(st.session_state.current_results)}</b></p>", unsafe_allow_html=True)
                    
                with nav_col3:
                    if st.button("Next ➡️", disabled=(idx >= len(st.session_state.current_results) - 1), use_container_width=True):
                        st.session_state.edit_index += 1
                        new_idx = st.session_state.edit_index
                        
                        # FORCE INIT SESSION STATE
                        rec = st.session_state.current_results[new_idx]
                        st.session_state[f"edit_ac_{new_idx}"] = rec.get("A/C No", "")
                        st.session_state[f"edit_bank_{new_idx}"] = rec.get("Bank Name", "")
                        st.session_state[f"edit_comp_{new_idx}"] = rec.get("Company Name", "")
                        st.session_state[f"edit_curr_{new_idx}"] = rec.get("Currency", "")
                        st.session_state[f"edit_date_{new_idx}"] = pd.to_datetime(rec.get("Document Date")) if rec.get("Document Date") else pd.Timestamp.now()
                        st.session_state[f"edit_ref_{new_idx}"] = rec.get("Reference No", "")
                        st.session_state[f"edit_total_{new_idx}"] = float(rec.get("Total Value", 0.0)) if rec.get("Total Value") else 0.0
                        st.session_state[f"edit_trans_{new_idx}"] = rec.get("Transaction", "DEBIT")
                        
                        st.rerun()

                # Input change callback for A/C No
                def on_ac_edit_change():
                    # Get the new A/C value from session state using the unique key
                    new_ac = st.session_state.get(f"edit_ac_{idx}", "")
                    # Lookup in DB
                    match_bank, match_comp, match_curr = db.lookup_master_info(new_ac)
                    if match_bank:
                        # Update UI Widgets ONLY
                        # DO NOT update current_results here (wait for Save button)
                        st.session_state[f"edit_bank_{idx}"] = match_bank
                        st.session_state[f"edit_comp_{idx}"] = match_comp
                        st.session_state[f"edit_curr_{idx}"] = match_curr
                        
                        st.toast(f"Match Found: {match_bank}, {match_comp}", icon="✅")
                    else:
                        st.toast(f"No match found for: {new_ac}", icon="⚠️")

                st.markdown("##### ✏️ Edit Details")
                
                # Form Layout
                e_col1, e_col2 = st.columns(2)
                
                with e_col1:
                    # A/C No with on_change trigger
                    st.text_input(
                        "A/C No", 
                        key=f"edit_ac_{idx}",
                        on_change=on_ac_edit_change
                    )
                    
                    e_bank = st.text_input("Bank Name", key=f"edit_bank_{idx}")
                    e_comp = st.text_input("Company Name", key=f"edit_comp_{idx}")
                    e_curr = st.text_input("Currency", key=f"edit_curr_{idx}")
                
                with e_col2:
                     # Handle Date parsing safely
                    doc_date_val = record.get("Document Date", pd.Timestamp.now())
                    if pd.isna(doc_date_val) or doc_date_val == "":
                         doc_date_val = pd.Timestamp.now()
                    else:
                         try:
                             doc_date_val = pd.to_datetime(doc_date_val)
                         except:
                             doc_date_val = pd.Timestamp.now()

                    e_date = st.date_input("Document Date", value=doc_date_val, key=f"edit_date_{idx}")
                    e_ref = st.text_input("Reference No", value=record.get("Reference No", ""), key=f"edit_ref_{idx}")
                    
                    # Handle float parsing
                    try:
                         val_float = float(record.get("Total Value", 0.0))
                    except:
                         val_float = 0.0
                    e_total = st.number_input("Total Value", value=val_float, format="%.2f", key=f"edit_total_{idx}")
                    
                    target_idx = 0 if record.get("Transaction") == "DEBIT" else 1
                    e_trans = st.selectbox("Transaction", ["DEBIT", "CREDIT"], index=target_idx, key=f"edit_trans_{idx}")
                    
                st.divider()
                
                b_col1, b_col2 = st.columns([1, 1])
                with b_col1:
                    if st.button("💾 Save Changes", type="primary", use_container_width=True):
                        # Update session state from widget keys
                        st.session_state.current_results[idx]["A/C No"] = st.session_state.get(f"edit_ac_{idx}")
                        st.session_state.current_results[idx]["Bank Name"] = st.session_state.get(f"edit_bank_{idx}")
                        st.session_state.current_results[idx]["Company Name"] = st.session_state.get(f"edit_comp_{idx}")
                        st.session_state.current_results[idx]["Currency"] = st.session_state.get(f"edit_curr_{idx}")
                        st.session_state.current_results[idx]["Document Date"] = st.session_state.get(f"edit_date_{idx}").strftime("%Y-%m-%d")
                        st.session_state.current_results[idx]["Reference No"] = st.session_state.get(f"edit_ref_{idx}")
                        st.session_state.current_results[idx]["Total Value"] = st.session_state.get(f"edit_total_{idx}")
                        st.session_state.current_results[idx]["Transaction"] = st.session_state.get(f"edit_trans_{idx}")
                        
                        # STAY IN EDIT MODE - Refresh to show updated data
                        st.toast(f"Record #{idx+1} updated!", icon="✅")
                        st.rerun()
                        
                with b_col2:
                    if st.button("🔙 Back to List", use_container_width=True):
                        st.session_state.edit_mode = False
                        st.rerun()
                            
        # Column 2: PDF Preview (Shared Logic)
        with col2_res:
            st.subheader("PDF Preview")
            if target_source:
                 target_pdf_path = os.path.join(source_path, str(target_source))
                 # Debug info if file missing
                 if not os.path.exists(target_pdf_path):
                     st.warning(f"File not found: {target_pdf_path}")
                 else:
                     render_pdf(target_pdf_path, target_page)
            else:
                st.info("Select a row or edit a record to preview.")

        if not st.session_state.edit_mode:
            st.divider()
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("💾 Export & Append to Excel"):
                    with st.spinner("Exporting to Excel..."):
                        # Ensure we use latest data
                        current_df = pd.DataFrame(st.session_state.current_results)
                        cols_to_drop = [c for c in ["Select", "PDF Link"] if c in current_df.columns]
                        export_df = current_df.drop(columns=cols_to_drop, errors='ignore')
                        msg = append_to_excel(export_df, export_path)
                    st.toast("Export complete!", icon="✅")
                    st.info(msg)
            
            with col_btn2:
                if st.button("🗄️ Save to Database"):
                    with st.spinner("Saving to database..."):
                        current_df = pd.DataFrame(st.session_state.current_results)
                        cols_to_drop = [c for c in ["Select", "PDF Link"] if c in current_df.columns]
                        save_df = current_df.drop(columns=cols_to_drop, errors='ignore')
                        count, msg = db.save_records(save_df)
                    if count > 0:
                        st.toast(f"Saved {count} records!", icon="✅")
                        st.success(msg)
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
    
    # Save filtered IDs for navigation
    if not hist_df.empty:
        st.session_state.db_filtered_ids = hist_df["id"].tolist()
    else:
        st.session_state.db_filtered_ids = []
    
    if not hist_df.empty:
        # Initialize Edit Mode State for Database Dashboard
        if "db_edit_mode" not in st.session_state:
            st.session_state.db_edit_mode = False
        if "db_edit_id" not in st.session_state:
            st.session_state.db_edit_id = None
        
        # --- VIEW MODE: TABLE ---
        if not st.session_state.db_edit_mode:
            # Metrics and Controls Row
            col_met1, col_met2, col_met3, col_met4 = st.columns([1.5, 2, 1.2, 0.3])
            with col_met1:
                st.metric("Total Records", f"{len(hist_df):,}")
            with col_met2:
                total_val = hist_df["Total Value"].sum()
                st.metric("Total Accumulated Value", f"{total_val:,.2f}")
            with col_met3:
                st.markdown("<br>", unsafe_allow_html=True)
                is_all_selected = st.checkbox("✅ Select All", key="sel_all_records", help="Check to select all records in the table")
            with col_met4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔄", help="Refresh data from database", use_container_width=True):
                    st.rerun()
                
            if "Select" not in hist_df.columns:
                hist_df.insert(0, "Select", is_all_selected)
            else:
                hist_df["Select"] = is_all_selected
                
            edited_hist_df = st.data_editor(
                hist_df,
                column_config={
                    "Select": st.column_config.CheckboxColumn("✅", help="Select record", width="small"),
                    "id": st.column_config.NumberColumn("ID", help="Record ID", disabled=True, width="small"),
                },
                use_container_width=True,
                hide_index=True,
                key="db_editor"
            )
            
            # Get selected records
            selected_records = edited_hist_df[edited_hist_df["Select"] == True]
            is_one_selected = len(selected_records) == 1
            is_any_selected = len(selected_records) > 0
            
            # Action Buttons Row
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("✏️ Edit Record", disabled=not is_one_selected, use_container_width=True, key="btn_db_edit_rec"):
                    # Get the selected record ID
                    rec_row = selected_records.iloc[0]
                    selected_id = rec_row["id"]
                    
                    st.session_state.db_edit_mode = True
                    st.session_state.db_edit_id = selected_id
                    
                    # Get basic info
                    ac_no = rec_row.get("A/C No", "")
                    bank = rec_row.get("Bank Name", "")
                    comp = rec_row.get("Company Name", "")
                    curr = rec_row.get("Currency", "")
                    
                    # Auto-lookup if info is missing or "None"
                    if ac_no and (not bank or bank == "None" or not comp or comp == "None" or not curr or curr == "None"):
                        l_bank, l_comp, l_curr = db.lookup_master_info(ac_no)
                        if l_bank:
                            bank = l_bank if (not bank or bank == "None") else bank
                            comp = l_comp if (not comp or comp == "None") else comp
                            curr = l_curr if (not curr or curr == "None") else curr
                            st.toast(f"✅ Auto-lookup found: {bank}", icon="🔍")

                    # FORCE INIT SESSION STATE
                    st.session_state.db_edit_ac = ac_no
                    st.session_state.db_edit_bank = bank if bank and bank != "None" else ""
                    st.session_state.db_edit_comp = comp if comp and comp != "None" else ""
                    st.session_state.db_edit_curr = curr if curr and curr != "None" else ""
                    st.session_state.db_edit_date = pd.to_datetime(rec_row.get("Document Date")) if rec_row.get("Document Date") \
                                                    else pd.Timestamp.now()
                    st.session_state.db_edit_ref = rec_row.get("Reference No", "")
                    st.session_state.db_edit_total = float(rec_row.get("Total Value", 0.0)) if rec_row.get("Total Value") else 0.0
                    st.session_state.db_edit_trans = rec_row.get("Transaction", "DEBIT")
                    
                    st.rerun()
            
            with col_btn2:
                if is_any_selected:
                    st.warning(f"⚠️ {len(selected_records)} record(s) selected")
                    if st.button(f"🗑️ Delete ({len(selected_records)})", type="primary", use_container_width=True, key="btn_db_del_rec"):
                        with st.spinner("Deleting records..."):
                            ids_to_delete = selected_records["id"].tolist()
                            count = db.delete_records(ids_to_delete)
                        st.toast(f"Deleted {count} records!", icon="🗑️")
                        get_cached_filter_options.clear()
                        st.rerun()
                else:
                    st.button("🗑️ Delete Selected", disabled=True, use_container_width=True, key="btn_db_del_disabled")
            
            with col_btn3:
                if st.button("📥 Export to Excel", use_container_width=True):
                    with st.spinner("Exporting report..."):
                        export_hist = edited_hist_df.drop(columns=["Select"])
                        report_name = f"DB_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                        report_path = os.path.join("output", report_name)
                        export_hist.to_excel(report_path, index=False)
                    st.toast("Report exported!", icon="📥")
                    st.success(f"Report exported to {report_path}")
        
        # --- EDIT MODE: FORM ---
        else:
            record_id = st.session_state.db_edit_id
            
            # Debug info
            st.caption(f"🔍 Attempting to load record ID: {record_id} (type: {type(record_id).__name__})")
            
            # Convert to int if needed
            try:
                record_id = int(record_id)
            except (ValueError, TypeError):
                st.error(f"Invalid record ID: {record_id}")
                if st.button("🔙 Back to List", key="btn_back_invalid_id"):
                    st.session_state.db_edit_mode = False
                    st.session_state.db_edit_id = None
                    st.rerun()
                st.stop()
            
            record = db.get_record_by_id(record_id)
            
            if record is None:
                st.error(f"Record #{record_id} not found in database.")
                st.warning("This may happen if the record was deleted or the session has stale data.")
                if st.button("🔙 Back to List", key="back_from_error"):
                    st.session_state.db_edit_mode = False
                    st.session_state.db_edit_id = None
                    st.rerun()
            else:
                # --- Navigation Logic ---
                filtered_ids = st.session_state.get("db_filtered_ids", [])
                current_idx = -1
                if record_id in filtered_ids:
                    current_idx = filtered_ids.index(record_id)
                
                nav_col1, nav_col2, nav_col3 = st.columns([0.2, 0.6, 0.2])
                
                with nav_col1:
                    if st.button("⬅️ Previous", disabled=(current_idx <= 0), key="btn_db_prev", use_container_width=True):
                        new_id = filtered_ids[current_idx - 1]
                        st.session_state.db_edit_id = new_id
                        
                        # FORCE INIT STATE FOR NEW RECORD
                        new_rec = db.get_record_by_id(new_id)
                        if new_rec:
                             ac_no = new_rec.get("A/C No", "")
                             bank = new_rec.get("Bank Name", "")
                             comp = new_rec.get("Company Name", "")
                             curr = new_rec.get("Currency", "")
                             
                             if ac_no and (not bank or bank == "None" or not comp or comp == "None" or not curr or curr == "None"):
                                 l_bank, l_comp, l_curr = db.lookup_master_info(ac_no)
                                 if l_bank:
                                     bank = l_bank if (not bank or bank == "None") else bank
                                     comp = l_comp if (not comp or comp == "None") else comp
                                     curr = l_curr if (not curr or curr == "None") else curr

                             st.session_state.db_edit_ac = ac_no
                             st.session_state.db_edit_bank = bank if bank and bank != "None" else ""
                             st.session_state.db_edit_comp = comp if comp and comp != "None" else ""
                             st.session_state.db_edit_curr = curr if curr and curr != "None" else ""
                             st.session_state.db_edit_date = pd.to_datetime(new_rec.get("Document Date")) if new_rec.get("Document Date") else pd.Timestamp.now()
                             st.session_state.db_edit_ref = new_rec.get("Reference No", "")
                             st.session_state.db_edit_total = float(new_rec.get("Total Value", 0.0)) if new_rec.get("Total Value") else 0.0
                             st.session_state.db_edit_trans = new_rec.get("Transaction", "DEBIT")
                        
                        st.rerun()

                with nav_col2:
                    st.markdown(f"<p style='text-align: center; padding-top: 10px;'><b>Record {current_idx+1} of {len(filtered_ids)} (ID: {record_id})</b></p>", unsafe_allow_html=True)

                with nav_col3:
                    if st.button("Next ➡️", disabled=(current_idx >= len(filtered_ids) - 1), key="btn_db_next", use_container_width=True):
                        new_id = filtered_ids[current_idx + 1]
                        st.session_state.db_edit_id = new_id
                        
                        # FORCE INIT STATE FOR NEW RECORD
                        new_rec = db.get_record_by_id(new_id)
                        if new_rec:
                             ac_no = new_rec.get("A/C No", "")
                             bank = new_rec.get("Bank Name", "")
                             comp = new_rec.get("Company Name", "")
                             curr = new_rec.get("Currency", "")
                             
                             if ac_no and (not bank or bank == "None" or not comp or comp == "None" or not curr or curr == "None"):
                                 l_bank, l_comp, l_curr = db.lookup_master_info(ac_no)
                                 if l_bank:
                                     bank = l_bank if (not bank or bank == "None") else bank
                                     comp = l_comp if (not comp or comp == "None") else comp
                                     curr = l_curr if (not curr or curr == "None") else curr

                             st.session_state.db_edit_ac = ac_no
                             st.session_state.db_edit_bank = bank if bank and bank != "None" else ""
                             st.session_state.db_edit_comp = comp if comp and comp != "None" else ""
                             st.session_state.db_edit_curr = curr if curr and curr != "None" else ""
                             st.session_state.db_edit_date = pd.to_datetime(new_rec.get("Document Date")) if new_rec.get("Document Date") else pd.Timestamp.now()
                             st.session_state.db_edit_ref = new_rec.get("Reference No", "")
                             st.session_state.db_edit_total = float(new_rec.get("Total Value", 0.0)) if new_rec.get("Total Value") else 0.0
                             st.session_state.db_edit_trans = new_rec.get("Transaction", "DEBIT")
                        
                        st.rerun()
                st.divider()
                
                # define callback
                def on_db_ac_change():
                    new_ac = st.session_state.get("db_edit_ac", "")
                    bank, comp, curr = db.lookup_master_info(new_ac)
                    if bank:
                        st.session_state.db_edit_bank = bank if bank and bank != "None" else ""
                        st.session_state.db_edit_comp = comp if comp and comp != "None" else ""
                        st.session_state.db_edit_curr = curr if curr and curr != "None" else ""
                        st.toast(f"✅ Auto-filled details for A/C: {new_ac}")
                    else:
                        st.toast(f"⚠️ No master data found for A/C: {new_ac}")

                # Use direct widgets instead of form
                col_e1, col_e2 = st.columns(2)
                
                with col_e1:
                    e_ac_no = st.text_input("A/C No", key="db_edit_ac", on_change=on_db_ac_change)
                    e_bank = st.text_input("Bank Name", key="db_edit_bank")
                    e_company = st.text_input("Company Name", key="db_edit_comp")
                    e_currency = st.text_input("Currency", key="db_edit_curr")
                
                with col_e2:
                    # Widgets using KEYS ONLY (Initialized in Edit Button)
                    e_date = st.date_input("Document Date", key="db_edit_date")
                    e_ref = st.text_input("Reference No", key="db_edit_ref")
                    e_total = st.number_input("Total Value", format="%.2f", key="db_edit_total")
                    
                    e_trans = st.selectbox("Transaction", ["DEBIT", "CREDIT"], key="db_edit_trans")
                
                st.divider()
                
                # Source File (read-only)
                st.text_input("Source File (Read-only)", value=record.get("Source File", ""), disabled=True)
                
                col_save, col_cancel = st.columns(2)
                
                with col_save:
                    if st.button("💾 Save Changes", type="primary", use_container_width=True):
                        # Prepare data for update from session state keys
                        update_data = {
                            "ac_no": st.session_state.db_edit_ac,
                            "bank_name": st.session_state.db_edit_bank,
                            "company_name": st.session_state.db_edit_comp,
                            "currency": st.session_state.db_edit_curr,
                            "doc_date": st.session_state.db_edit_date.strftime("%Y-%m-%d"),
                            "ref_no": st.session_state.db_edit_ref,
                            "total_value": st.session_state.db_edit_total,
                            "transaction_details": st.session_state.db_edit_trans
                        }
                        
                        success, msg = db.update_record(record_id, update_data)
                        
                        if success:
                            st.toast(msg, icon="✅")
                            # Clear edit state keys
                            keys_to_clear = ["db_edit_ac", "db_edit_bank", "db_edit_comp", "db_edit_curr", "db_edit_date", "db_edit_ref", "db_edit_total", "db_edit_trans"]
                            for k in keys_to_clear:
                                if k in st.session_state: del st.session_state[k]
                                
                            st.session_state.db_edit_mode = False
                            st.session_state.db_edit_id = None
                            get_cached_filter_options.clear()
                            st.rerun()
                        else:
                            st.error(msg)
                
                with col_cancel:
                    if st.button("❌ Cancel", use_container_width=True, key="btn_db_edit_cancel"):
                        # Clear edit state keys
                        keys_to_clear = ["db_edit_ac", "db_edit_bank", "db_edit_comp", "db_edit_curr", "db_edit_date", "db_edit_ref", "db_edit_total", "db_edit_trans"]
                        for k in keys_to_clear:
                            if k in st.session_state: del st.session_state[k]
                            
                        st.session_state.db_edit_mode = False
                        st.session_state.db_edit_id = None
                        st.rerun()
            
    else:
        st.info("No data found in database. Try saving some OCR results first.")

# ==========================================
# TAB 3: Manual Entry
# ==========================================
with tab_manual:
    st.subheader("➕ Manual Record Entry")
    st.info("Directly add a transaction record to the database. Fields will auto-populate based on A/C No selection.")
    
    # Load Master Data
    master_df = get_ac_master_data(master_path, os.path.getmtime(master_path) if os.path.exists(master_path) else 0)
    
    if not master_df.empty:
        # Create formatted options and a mapping back to the raw A/C No
        master_df['Display'] = master_df.apply(lambda x: f"{x['ACNO']} - {x['BankName']} - {x['AccountName']} {x.get('Branch NicName', '')}".strip(), axis=1)
        ac_display_options = ["-- Select Account --"] + master_df['Display'].tolist()
        ac_mapping = dict(zip(master_df['Display'], master_df['ACNO']))
        
        # UI Columns
        col_m1, col_m2 = st.columns([0.6, 0.4], gap="large")
        
        # Initialize session state for manual entry if not exists
        if "m_ref" not in st.session_state: st.session_state.m_ref = ""
        if "m_total" not in st.session_state: st.session_state.m_total = 0.0
        if "m_source" not in st.session_state: st.session_state.m_source = "Manual Save"

        with col_m1:
            st.markdown("##### 📝 Input Details")
            selected_display = st.selectbox("A/C No (Search by No, Bank, or Name)", ac_display_options, key="manual_ac")
            selected_ac = ac_mapping.get(selected_display, "-- Select Account --")
            
            # Auto-lookup based on selection
            bank_val = ""
            comp_val = ""
            curr_val = ""
            acc_type_val = ""
            
            if selected_ac != "-- Select Account --":
                match = master_df[master_df['ACNO'] == selected_ac]
                if not match.empty:
                    bank_val = match.iloc[0].get('BankName', '')
                    comp_val = match.iloc[0].get('AccountName', '')
                    curr_val = match.iloc[0].get('Currency', '')
                    acc_type_val = match.iloc[0].get('AccountType', '')
            
            m_transaction = st.selectbox("Transaction Type", ["DEBIT", "CREDIT"], key="m_trans")
            m_date = st.date_input("Document Date", value=pd.Timestamp.now(), key="m_date")
            m_ref = st.text_input("Reference No", key="m_ref_input", value=st.session_state.m_ref)
            m_total = st.number_input("Total Value", min_value=0.0, format="%.2f", key="m_total_input", value=st.session_state.m_total)
            m_source = st.text_input("Source File", key="m_source_input", value=st.session_state.m_source)

        with col_m2:
            st.markdown("##### 🔍 Auto Lookup (Read-only)")
            st.text_input("Bank Name", value=bank_val, disabled=True)
            st.text_input("Company Name", value=comp_val, disabled=True)
            st.text_input("Account Type", value=acc_type_val, disabled=True)
            st.text_input("Currency", value=curr_val, disabled=True)
            
            # Action Buttons
            st.markdown("<br>", unsafe_allow_html=True)
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                submit_manual = st.button("📁 Save Record to Database", use_container_width=True, type="primary")
            with col_b2:
                if st.button("🧹 Clear Form", use_container_width=True):
                    st.session_state.m_ref = ""
                    st.session_state.m_total = 0.0
                    st.session_state.m_source = "Manual Save"
                    st.rerun()

        if submit_manual:
            if selected_ac == "-- Select Account --":
                st.error("Please select a valid Account Number.")
            elif m_total <= 0:
                st.warning("Total Value should be greater than 0.")
            else:
                # Prepare data for db_manager.save_records
                manual_data = {
                    "A/C No": [selected_ac],
                    "Bank Name": [bank_val],
                    "Company Name": [comp_val],
                    "Currency": [curr_val],
                    "Document Date": [m_date.strftime("%Y-%m-%d")],
                    "Reference No": [m_ref],
                    "Total Value": [m_total],
                    "Transaction": [m_transaction],
                    "Source File": [m_source]
                }
                save_df = pd.DataFrame(manual_data)
                count, msg = db.save_records(save_df)
                
                if count > 0:
                    st.success(f"Successfully saved manual record for A/C {selected_ac}")
                    st.toast("Manual record saved!", icon="✅")
                    get_cached_filter_options.clear()
                else:
                    st.error(f"Failed to save: {msg}")
    else:
        st.error(f"Could not load account list from {master_path}. Please check the file path in Settings.")

# ==========================================
# TAB 4: Bank Statement By A/C No. Report
# ==========================================
with tab_report:
    st.subheader("📉 Bank Statement By A/C No. Report")
    st.info("Generate a detailed bank statement with running balance.")
    
    # Reuse functionality from Manual Entry to load Master Data options
    master_df = get_ac_master_data(master_path, os.path.getmtime(master_path) if os.path.exists(master_path) else 0)
    
    if not master_df.empty:
        # Create formatting options
        master_df['Display'] = master_df.apply(lambda x: f"{x['ACNO']} - {x['BankName']} - {x['AccountName']} {x.get('Branch NicName', '')}".strip(), axis=1)
        ac_display_options = ["-- Select Account --"] + master_df['Display'].tolist()
        ac_mapping = dict(zip(master_df['Display'], master_df['ACNO']))
        
        col_r1, col_r2, col_r3 = st.columns([1.5, 1, 1])
        
        with col_r1:
            r_selected_display = st.selectbox("Select Account", ac_display_options, key="report_ac")
            r_selected_ac = ac_mapping.get(r_selected_display, None)
            
        with col_r2:
             # Date Range for Report
            r_start_date = st.date_input("From Date", value=pd.Timestamp.now() - pd.Timedelta(days=30), key="rpt_start")
            
        with col_r3:
            r_end_date = st.date_input("To Date", value=pd.Timestamp.now(), key="rpt_end")
            
        col_r4, col_r5 = st.columns([1, 2])
        with col_r4:
            starting_balance = st.number_input("Starting Balance", value=0.0, format="%.2f")
            
        if st.button("📊 Generate Report", type="primary"):
            if r_selected_ac and r_selected_ac != "-- Select Account --":
                # Load Data filtered by Account and Date Range
                report_df = db.load_records(
                    ac_no=r_selected_ac,
                    start_date=r_start_date,
                    end_date=r_end_date
                )
                
                if not report_df.empty:
                    # Data Transformation Logic
                    # 1. Sort by Date
                    report_df = report_df.sort_values(by=["Document Date", "id"], ascending=[True, True])
                    
                    # 2. Pivot/Melt Logic: Separate Total Value into Debit/Credit columns
                    report_df['Debit'] = report_df.apply(lambda x: x['Total Value'] if x['Transaction'] == 'DEBIT' else 0, axis=1)
                    report_df['Credit'] = report_df.apply(lambda x: x['Total Value'] if x['Transaction'] == 'CREDIT' else 0, axis=1)
                    
                    # 3. Calculate Running Balance
                    # Calculate cumulative sum of (Debit - Credit)
                    report_df['Net Change'] = report_df['Debit'] - report_df['Credit']
                    report_df['Balance'] = starting_balance + report_df['Net Change'].cumsum()
                    
                    # 4. Final Formatting
                    # Columns needed: Date, Debit, Credit, Balance, Others (Ref No)
                    final_df = report_df[['Document Date', 'Debit', 'Credit', 'Balance', 'Reference No']].copy()
                    final_df = final_df.rename(columns={'Document Date': 'Date', 'Reference No': 'Others'})
                    
                    # Format for display
                    st.divider()
                    # st.markdown(f"**Statement for:** {r_selected_display}")
                    # st.markdown(f"**Period:** {r_start_date.strftime('%d/%m/%Y')} - {r_end_date.strftime('%d/%m/%Y')}")
                    
                    # Create display copy for formatting
                    display_df = final_df.copy()
                    for col in ["Debit", "Credit", "Balance"]:
                         display_df[col] = display_df[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "0.00")
                    
                    st.data_editor(
                        display_df,
                        column_config={
                            "Date": st.column_config.TextColumn("Date"),
                            "Debit": st.column_config.TextColumn("Debit"),
                            "Credit": st.column_config.TextColumn("Credit"),
                            "Balance": st.column_config.TextColumn("Balance"),
                            "Others": "Others"
                        },
                        use_container_width=True,
                        hide_index=True,
                        disabled=True
                    )

                    # Export Button
                    report_filename = f"Statement_{r_selected_ac}_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx"
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                         # Write info as headers at the top
                         final_df.to_excel(writer, index=False, sheet_name='Statement', startrow=3)
                         
                         workbook = writer.book
                         worksheet = writer.sheets['Statement']
                         
                         # Add Header Info
                         header_fmt = workbook.add_format({'bold': True, 'font_size': 12})
                         worksheet.write(0, 0, f"Statement for: {r_selected_display}", header_fmt)
                         worksheet.write(1, 0, f"Period: {r_start_date.strftime('%d/%m/%Y')} - {r_end_date.strftime('%d/%m/%Y')}", header_fmt)
                         
                         # Basic Excel Formatting
                         fmt_currency = workbook.add_format({'num_format': '#,##0.00'})
                         worksheet.set_column('B:D', 18, fmt_currency) # Debit, Credit, Balance
                         worksheet.set_column('A:A', 12) # Date
                         worksheet.set_column('E:E', 25) # Others
                    
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=buffer.getvalue(),
                        file_name=report_filename,
                        mime="application/vnd.ms-excel"
                    )
                    
                else:
                    st.warning("No transactions found for the selected account and period.")
            else:
                st.error("Please select an Account Number first.")

# ==========================================
# TAB 5: Bank Balance Summary Report
# ==========================================
with tab_balance:
    st.subheader("💰 Bank Balance Summary Report")
    st.info("Generate a summary of bank balances from start of month to selected date, grouped by currency.")
    
    # Load Master Data for Branch info
    master_df = get_ac_master_data(master_path, os.path.getmtime(master_path) if os.path.exists(master_path) else 0)
    
    # UI Controls
    col_bal1, col_bal2, col_bal3 = st.columns([1, 2, 1])
    
    with col_bal1:
        bal_as_of_date = st.date_input("As of Date", value=pd.Timestamp.now(), key="bal_as_of")
    
    with col_bal2:
        # Get account list from database
        account_list = db.get_account_list()
        if account_list:
            # Create display options
            account_options = [f"{a['ac_no']} - {a['bank_name']} ({a['currency']})" for a in account_list]
            account_mapping = {f"{a['ac_no']} - {a['bank_name']} ({a['currency']})": a['ac_no'] for a in account_list}
            
            selected_accounts_display = st.multiselect(
                "Select Accounts (Default: All)",
                options=account_options,
                default=[],
                key="bal_accounts",
                help="Leave empty to include all accounts"
            )
            
            # Map display back to ac_no
            if selected_accounts_display:
                selected_ac_list = [account_mapping[d] for d in selected_accounts_display]
            else:
                selected_ac_list = None  # All accounts
        else:
            st.warning("No accounts found in database.")
            selected_ac_list = None
    
    with col_bal3:
        starting_balance_global = st.number_input("Starting Balance (Global)", value=0.0, format="%.2f", key="bal_start")
    
    if st.button("📊 Generate Balance Report", type="primary", key="gen_bal_report"):
        with st.spinner("Generating report..."):
            # Get balance summary from database
            balance_df = db.get_balance_summary(bal_as_of_date, selected_ac_list)
            
            if not balance_df.empty:
                # Merge with Master data to get Branch info
                if not master_df.empty and 'ACNO' in master_df.columns:
                    master_lookup = master_df[['ACNO', 'Branch', 'AccountName']].copy()
                    master_lookup = master_lookup.rename(columns={'ACNO': 'ac_no', 'AccountName': 'company_name'})
                    balance_df = balance_df.merge(master_lookup, on='ac_no', how='left')
                else:
                    balance_df['Branch'] = ''
                    balance_df['company_name'] = ''
                
                # Calculate Balance
                balance_df['balance'] = starting_balance_global + balance_df['total_debit'] - balance_df['total_credit']
                
                # Get unique currencies for grouping
                currencies = balance_df['currency'].dropna().unique()
                
                # Show date range info
                start_of_month = bal_as_of_date.replace(day=1)
                st.markdown(f"**Period:** {start_of_month.strftime('%Y-%m-%d')} to {bal_as_of_date.strftime('%Y-%m-%d')}")
                
                st.divider()
                
                # Display grouped by currency
                total_data_for_export = []
                
                for curr in sorted(currencies):
                    curr_df = balance_df[balance_df['currency'] == curr].copy()
                    
                    if curr_df.empty:
                        continue
                    
                    # Currency Header
                    st.markdown(f"### Bank ({curr} Amount)")
                    
                    # Prepare display dataframe
                    display_cols = ['bank_name', 'Branch', 'ac_no', 'balance']
                    display_curr_df = curr_df[[c for c in display_cols if c in curr_df.columns]].copy()
                    display_curr_df = display_curr_df.rename(columns={
                        'bank_name': 'Bank',
                        'Branch': 'Branch',
                        'ac_no': 'A/C No.',
                        'balance': 'BANK BAL.'
                    })
                    
                    # Format balance
                    display_curr_df['BANK BAL.'] = display_curr_df['BANK BAL.'].apply(lambda x: f"{x:,.2f}")
                    
                    # Display table
                    st.dataframe(display_curr_df, use_container_width=True, hide_index=True)
                    
                    # Currency Total
                    curr_total = curr_df['balance'].sum()
                    st.markdown(f"**Total ({curr}): {curr_total:,.2f}**")
                    st.divider()
                    
                    # Collect for export
                    curr_df['currency_group'] = curr
                    total_data_for_export.append(curr_df)
                
                # Export Button
                if total_data_for_export:
                    export_df = pd.concat(total_data_for_export, ignore_index=True)
                    export_df = export_df[['bank_name', 'Branch', 'ac_no', 'currency', 'total_debit', 'total_credit', 'balance']]
                    export_df = export_df.rename(columns={
                        'bank_name': 'Bank',
                        'ac_no': 'A/C No.',
                        'total_debit': 'Total Debit',
                        'total_credit': 'Total Credit',
                        'balance': 'BANK BAL.',
                        'currency': 'Currency'
                    })
                    
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        export_df.to_excel(writer, index=False, sheet_name='Balance Summary', startrow=2)
                        workbook = writer.book
                        worksheet = writer.sheets['Balance Summary']
                        
                        # Header info
                        header_fmt = workbook.add_format({'bold': True, 'font_size': 12})
                        worksheet.write(0, 0, f"Bank Balance Summary as of {bal_as_of_date.strftime('%Y-%m-%d')}", header_fmt)
                        
                        # Format currency columns
                        fmt_currency = workbook.add_format({'num_format': '#,##0.00'})
                        worksheet.set_column('E:G', 18, fmt_currency)
                    
                    st.download_button(
                        label="📥 Download Excel Report",
                        data=buffer.getvalue(),
                        file_name=f"Balance_Summary_{bal_as_of_date.strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.ms-excel"
                    )
            else:
                st.warning("No data found for the selected criteria.")


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

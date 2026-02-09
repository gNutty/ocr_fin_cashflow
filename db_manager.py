import sqlite3
import pandas as pd
import datetime
import os
import re

DB_NAME = "ocr_data.db"

# Use a module-level connection for caching purposes
_connection = None

def get_connection():
    """Create or reuse a database connection."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_NAME, check_same_thread=False)
    return _connection

def init_db():
    """Initialize the database tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()
    
    # Transactions Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ac_no TEXT,
            bank_name TEXT,
            company_name TEXT,
            currency TEXT,
            doc_date TEXT,
            ref_no TEXT,
            total_value REAL,
            transaction_details TEXT,
            source_file TEXT,
            timestamp TEXT
        )
    """)
    
    # Migration: Add currency column if it doesn't exist (for existing databases)
    try:
        c.execute("ALTER TABLE transactions ADD COLUMN currency TEXT")
    except sqlite3.OperationalError:
        # Column already exists, ignore error
        pass
    
    # AC Master Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS ac_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ac_no TEXT UNIQUE,
            bank_name TEXT,
            branch TEXT,
            branch_nic_name TEXT,
            account_name TEXT,
            account_type TEXT,
            currency TEXT,
            timestamp TEXT
        )
    """)
    
    conn.commit()

def normalize_date(date_str):
    """
    Normalize various date formats to YYYY-MM-DD.
    Supports: 
    - 01-Jan-2024
    - 05/12/2025
    - January 01, 2024
    - 2024-01-01 or 2024/1/1
    """
    if not date_str or pd.isna(date_str):
        return None
        
    date_str = str(date_str).strip()
    
    # Month mapping
    months_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
        'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    try:
        # Case 1: DD-MMM-YYYY (e.g., 01-Jan-2024)
        m = re.match(r"(\d{1,2})-([a-zA-Z]{3})-(\d{4})", date_str)
        if m:
            day, mon, year = m.groups()
            mon_num = months_map.get(mon.lower(), '01')
            return f"{year}-{mon_num}-{int(day):02d}"
            
        # Case 2: DD/MM/YYYY (e.g., 05/12/2025)
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if m:
            day, mon, year = m.groups()
            return f"{year}-{int(mon):02d}-{int(day):02d}"
            
        # Case 3: MMM DD, YYYY (e.g., January 01, 2024)
        m = re.match(r"([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})", date_str)
        if m:
            mon_name, day, year = m.groups()
            mon_num = '01'
            for k, v in months_map.items():
                if mon_name.lower().startswith(k):
                    mon_num = v
                    break
            return f"{year}-{mon_num}-{int(day):02d}"
            
        # Case 4: YYYY-MM-DD or YYYY/MM/DD (Ensure exactly 10 chars, ignore time)
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
        if m:
            year, mon, day = m.groups()
            return f"{year}-{int(mon):02d}-{int(day):02d}"
            
    except Exception:
        pass
        
    return date_str # Return as is if normalization fails

def save_records(df):
    """
    Save records from a Pandas DataFrame to the database.
    Expects specific column names from the OCR process.
    """
    if df.empty:
        return 0, "No data to save."
    
    # Prepare data for insertion
    records_to_save = []
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for _, row in df.iterrows():
        # Clean numeric value (remove commas)
        val_str = str(row.get("Total Value", "0")).replace(",", "")
        try:
            total_val = float(val_str) if val_str and val_str != "nan" else 0.0
        except ValueError:
            total_val = 0.0
            
        doc_date = str(row.get("Document Date", ""))
        normalized_doc_date = normalize_date(doc_date)
        
        records_to_save.append((
            str(row.get("A/C No", "")),
            str(row.get("Bank Name", "")),
            str(row.get("Company Name", "")),
            str(row.get("Currency", "")),
            normalized_doc_date,
            str(row.get("Reference No", "")),
            total_val,
            str(row.get("Transaction", "")),
            str(row.get("Source File", "")),
            current_time
        ))
    
    conn = get_connection()
    c = conn.cursor()
    try:
        c.executemany("""
            INSERT INTO transactions 
            (ac_no, bank_name, company_name, currency, doc_date, ref_no, total_value, transaction_details, source_file, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records_to_save)
        conn.commit()
        count = len(records_to_save)
        return count, f"Successfully saved {count} records to database."
    except Exception as e:
        return 0, f"Error saving to database: {str(e)}"

def load_records(bank=None, company=None, currency=None, start_date=None, end_date=None, ac_no=None):
    """
    Fetch records from the database with optional filters.
    """
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    
    if ac_no and ac_no != "All":
        query += " AND ac_no = ?"
        params.append(ac_no)
    
    if bank and bank != "All":
        query += " AND bank_name = ?"
        params.append(bank)
    
    if company and company != "All":
        query += " AND company_name = ?"
        params.append(company)

    if currency and currency != "All":
        query += " AND currency = ?"
        params.append(currency)
        
    if start_date:
        query += " AND doc_date >= ?"
        params.append(str(start_date))
        
    if end_date:
        query += " AND doc_date <= ?"
        params.append(str(end_date))

    # For Year/Month filtering if start_date/end_date are not provided
    # Re-evaluating params for Year/Month selection
    
    conn = get_connection()
    df = pd.read_sql_query(query, conn, params=params)
    
    # Rename columns back to user-friendly names for display
    id_map = {
        "ac_no": "A/C No",
        "bank_name": "Bank Name",
        "company_name": "Company Name",
        "currency": "Currency",
        "doc_date": "Document Date",
        "ref_no": "Reference No",
        "total_value": "Total Value",
        "transaction_details": "Transaction",
        "source_file": "Source File",
        "timestamp": "Saved At"
    }
    df = df.rename(columns=id_map)
    
    # Post-load normalization just in case older records exist
    if "Document Date" in df.columns:
        df["Document Date"] = df["Document Date"].apply(normalize_date)
        
    return df

def get_filter_options():
    """Get unique banks, companies, currencies, and A/C numbers for filter dropdowns."""
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT DISTINCT ac_no, bank_name, company_name, currency, doc_date FROM transactions", conn)
        ac_nos = sorted(df["ac_no"].dropna().unique().tolist())
        banks = sorted(df["bank_name"].dropna().unique().tolist())
        companies = sorted(df["company_name"].dropna().unique().tolist())
        currencies = sorted(df["currency"].dropna().unique().tolist())
        
        # Extract years and months from doc_date
        years = set()
        months = set()
        for d in df["doc_date"].dropna():
            norm_d = normalize_date(d)
            if norm_d and "-" in norm_d:
                parts = norm_d.split("-")
                if len(parts) >= 1: years.add(parts[0])
                if len(parts) >= 2: months.add(parts[1])
        
        sorted_years = sorted(list(years), reverse=True)
        sorted_months = sorted(list(months))
        
        return ["All"] + ac_nos, ["All"] + banks, ["All"] + companies, ["All"] + currencies, ["All"] + sorted_years, ["All"] + sorted_months
    except Exception:
        return ["All"], ["All"], ["All"], ["All"], ["All"], ["All"]

def delete_records(ids):
    """Delete records by ID list."""
    if not ids:
        return 0
    
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join(["?"] * len(ids))
    c.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", ids)
    conn.commit()
    count = c.rowcount
    return count

def get_account_list():
    """
    Get unique account numbers with their bank name and currency.
    Returns a list of dicts for multi-select dropdown.
    """
    conn = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT DISTINCT ac_no, bank_name, currency 
            FROM transactions 
            WHERE ac_no IS NOT NULL AND ac_no != ''
            ORDER BY currency, bank_name, ac_no
        """, conn)
        return df.to_dict('records')
    except Exception:
        return []

def get_balance_summary(as_of_date, account_list=None):
    """
    Calculate balance summary for accounts from start of month to as_of_date.
    
    Args:
        as_of_date: The date to calculate balance as of (datetime.date or string YYYY-MM-DD)
        account_list: Optional list of account numbers to filter (None = all accounts)
    
    Returns:
        DataFrame with columns: ac_no, bank_name, currency, total_debit, total_credit
    """
    conn = get_connection()
    
    # Calculate start of month
    if isinstance(as_of_date, str):
        as_of_date = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
    
    start_of_month = as_of_date.replace(day=1)
    
    # Build query
    query = """
        SELECT 
            ac_no,
            bank_name,
            currency,
            SUM(CASE WHEN transaction_details = 'DEBIT' THEN total_value ELSE 0 END) as total_debit,
            SUM(CASE WHEN transaction_details = 'CREDIT' THEN total_value ELSE 0 END) as total_credit
        FROM transactions
        WHERE doc_date >= ? AND doc_date <= ?
    """
    params = [str(start_of_month), str(as_of_date)]
    
    if account_list and len(account_list) > 0:
        placeholders = ",".join(["?"] * len(account_list))
        query += f" AND ac_no IN ({placeholders})"
        params.extend(account_list)
    
    query += " GROUP BY ac_no, bank_name, currency ORDER BY currency, bank_name, ac_no"
    
    df = pd.read_sql_query(query, conn, params=params)
    return df

def update_record(record_id, data):
    """
    Update a single record by ID with validation.
    Uses parameterized queries for security (prevents SQL injection).
    
    Args:
        record_id: The ID of the record to update
        data: Dict with keys matching column names:
            - ac_no, bank_name, company_name, currency
            - doc_date, ref_no, total_value, transaction_details
    
    Returns:
        (success: bool, message: str)
    """
    if not record_id:
        return False, "Record ID is required."
    
    # Validate and normalize data
    try:
        # Normalize date
        doc_date = normalize_date(data.get("doc_date", ""))
        
        # Validate total_value is numeric
        total_value_str = str(data.get("total_value", "0")).replace(",", "")
        try:
            total_value = float(total_value_str) if total_value_str else 0.0
        except ValueError:
            return False, "Total Value must be a valid number."
        
        # Validate transaction type
        transaction = str(data.get("transaction_details", "")).upper()
        if transaction not in ["DEBIT", "CREDIT"]:
            return False, "Transaction must be DEBIT or CREDIT."
        
        conn = get_connection()
        c = conn.cursor()
        
        # Parameterized query for security
        c.execute("""
            UPDATE transactions SET
                ac_no = ?,
                bank_name = ?,
                company_name = ?,
                currency = ?,
                doc_date = ?,
                ref_no = ?,
                total_value = ?,
                transaction_details = ?
            WHERE id = ?
        """, (
            str(data.get("ac_no", "")),
            str(data.get("bank_name", "")),
            str(data.get("company_name", "")),
            str(data.get("currency", "")),
            doc_date,
            str(data.get("ref_no", "")),
            total_value,
            transaction,
            record_id
        ))
        
        conn.commit()
        
        if c.rowcount > 0:
            return True, f"Record #{record_id} updated successfully."
        else:
            return False, f"Record #{record_id} not found."
            
    except Exception as e:
        return False, f"Error updating record: {str(e)}"

def get_record_by_id(record_id):
    """
    Fetch a single record by ID for editing.
    """
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM transactions WHERE id = ?", conn, params=[record_id])
    
    if df.empty:
        return None
    
    # Rename columns to user-friendly names
    id_map = {
        "ac_no": "A/C No",
        "bank_name": "Bank Name",
        "company_name": "Company Name",
        "currency": "Currency",
        "doc_date": "Document Date",
        "ref_no": "Reference No",
        "total_value": "Total Value",
        "transaction_details": "Transaction",
        "source_file": "Source File"
    }
    df = df.rename(columns=id_map)
    return df.iloc[0].to_dict()

# --- MASTER DATA FUNCTIONS ---

def get_all_master_records():
    """
    Fetch all master data records.
    Returns a DataFrame.
    """
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM ac_master ORDER BY bank_name, ac_no", conn)
    
    # Rename columns to match old Excel format for compatibility
    rename_map = {
        "ac_no": "ACNO",
        "bank_name": "BankName",
        "branch": "Branch",
        "branch_nic_name": "Branch NicName",
        "account_name": "AccountName",
        "account_type": "AccountType",
        "currency": "Currency"
    }
    df = df.rename(columns=rename_map)
    return df

def get_master_record_by_id(record_id):
    """Fetch single master record by ID."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM ac_master WHERE id = ?", conn, params=[record_id])
    if df.empty:
        return None
        
    rename_map = {
        "ac_no": "ACNO",
        "bank_name": "BankName",
        "branch": "Branch",
        "branch_nic_name": "Branch NicName",
        "account_name": "AccountName",
        "account_type": "AccountType",
        "currency": "Currency"
    }
    df = df.rename(columns=rename_map)
    return df.iloc[0].to_dict()

def add_master_record(data):
    """
    Add a new master record.
    Data dict keys: ACNO, BankName, Branch, Branch NicName, AccountName, AccountType, Currency
    """
    conn = get_connection()
    c = conn.cursor()
    
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO ac_master (ac_no, bank_name, branch, branch_nic_name, account_name, account_type, currency, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(data.get("ACNO", "")).strip(),
            str(data.get("BankName", "")).strip(),
            str(data.get("Branch", "")).strip(),
            str(data.get("Branch NicName", "")).strip(),
            str(data.get("AccountName", "")).strip(),
            str(data.get("AccountType", "")).strip(),
            str(data.get("Currency", "")).strip(),
            timestamp
        ))
        conn.commit()
        return True, "Master record added successfully."
    except sqlite3.IntegrityError:
        return False, f"Error: A/C No '{data.get('ACNO')}' already exists."
    except Exception as e:
        return False, f"Error adding record: {str(e)}"

def update_master_record(record_id, data):
    """
    Update master record by ID.
    Data dict keys: ACNO, BankName, Branch, Branch NicName, AccountName, AccountType, Currency
    """
    conn = get_connection()
    c = conn.cursor()
    
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE ac_master SET
                ac_no = ?,
                bank_name = ?,
                branch = ?,
                branch_nic_name = ?,
                account_name = ?,
                account_type = ?,
                currency = ?,
                timestamp = ?
            WHERE id = ?
        """, (
            str(data.get("ACNO", "")).strip(),
            str(data.get("BankName", "")).strip(),
            str(data.get("Branch", "")).strip(),
            str(data.get("Branch NicName", "")).strip(),
            str(data.get("AccountName", "")).strip(),
            str(data.get("AccountType", "")).strip(),
            str(data.get("Currency", "")).strip(),
            timestamp,
            record_id
        ))
        conn.commit()
        
        if c.rowcount > 0:
            return True, "Master record updated successfully."
        else:
            return False, "Record not found."
            
    except sqlite3.IntegrityError:
        return False, f"Error: A/C No '{data.get('ACNO')}' already exists in another record."
    except Exception as e:
        return False, f"Error updating record: {str(e)}"

def delete_master_records(ids):
    """Delete master records by ID list."""
    if not ids: return 0
    conn = get_connection()
    c = conn.cursor()
    placeholders = ",".join(["?"] * len(ids))
    c.execute(f"DELETE FROM ac_master WHERE id IN ({placeholders})", ids)
    conn.commit()
    return c.rowcount

def migrate_excel_to_db(excel_path):
    """
    Migrate existing Excel master data to SQLite if table is empty.
    Returns: (count, message)
    """
    if not os.path.exists(excel_path):
        return 0, "Excel file not found."
        
    conn = get_connection()
    c = conn.cursor()
    
    # Check if table is empty
    c.execute("SELECT COUNT(*) FROM ac_master")
    count = c.fetchone()[0]
    
    if count > 0:
        return count, "Database already populated. Skipping migration."
        
    try:
        df = pd.read_excel(excel_path)
        # Clean columns
        df.columns = [str(col).strip() for col in df.columns]
        
        records_added = 0
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for _, row in df.iterrows():
            try:
                ac_no = str(row.get("ACNO", "")).strip().replace("'", "")
                if not ac_no or ac_no.lower() == "nan": continue
                
                c.execute("""
                    INSERT INTO ac_master (ac_no, bank_name, branch, branch_nic_name, account_name, account_type, currency, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ac_no,
                    str(row.get("BankName", "")).strip(),
                    str(row.get("Branch", "")).strip(),
                    str(row.get("Branch NicName", "")).strip(),
                    str(row.get("AccountName", "")).strip(),
                    str(row.get("AccountType", "")).strip(),
                    str(row.get("Currency", "")).strip(),
                    timestamp
                ))
                records_added += 1
            except sqlite3.IntegrityError:
                pass # Skip duplicates if any
                
        conn.commit()
        return records_added, f"Successfully migrated {records_added} records from Excel."
        
    except Exception as e:
        return 0, f"Error during migration: {str(e)}"

def lookup_master_info(ac_no):
    """
    Lookup Bank, Company, and Currency from master data based on A/C No.
    Supports partial matching (input in DB or DB in input).
    Returns: (BankName, AccountName, Currency) or (None, None, None)
    """
    if not ac_no:
        return None, None, None
        
    clean_input = str(ac_no).strip().replace(" ", "").replace("-", "")
    if not clean_input:
        return None, None, None

    conn = get_connection()
    try:
        # Fetch all ACNOs to perform flexible matching in Python
        # (Since SQLite restricted LIKE/INSTR might miss some fuzzy cases or reverse containment)
        df = pd.read_sql_query("SELECT ac_no, bank_name, account_name, currency FROM ac_master", conn)
        
        # Normalize DB ACNOs
        df['clean_ac'] = df['ac_no'].astype(str).str.strip().str.replace("'", "").str.replace(" ", "").str.replace("-", "")
        
        # Match logic: input in DB_AC or DB_AC in input
        match = df[df['clean_ac'].apply(lambda x: x in clean_input or clean_input in x)]
        
        if not match.empty:
            # Return first match
            row = match.iloc[0]
            return row['bank_name'], row['account_name'], row['currency']
            
    except Exception as e:
        print(f"DB Lookup Error: {e}")
        return None, None, None

    return None, None, None

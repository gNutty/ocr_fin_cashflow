import sqlite3
import pandas as pd
import datetime
import os

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
    conn.commit()

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
            
        records_to_save.append((
            str(row.get("A/C No", "")),
            str(row.get("Bank Name", "")),
            str(row.get("Company Name", "")),
            str(row.get("Currency", "")),
            str(row.get("Document Date", "")),
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

def load_records(bank=None, company=None, currency=None, start_date=None, end_date=None):
    """
    Fetch records from the database with optional filters.
    """
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    
    if bank and bank != "All":
        query += " AND bank_name = ?"
        params.append(bank)
    
    if company and company != "All":
        query += " AND company_name = ?"
        params.append(company)

    if currency and currency != "All":
        query += " AND currency = ?"
        params.append(currency)
        
    # Date filtering can be added here if needed, 
    # but requires standardized date formats in doc_date.
    
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
    return df

def get_filter_options():
    """Get unique banks, companies, and currencies for filter dropdowns."""
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT DISTINCT bank_name, company_name, currency FROM transactions", conn)
        banks = sorted(df["bank_name"].dropna().unique().tolist())
        companies = sorted(df["company_name"].dropna().unique().tolist())
        currencies = sorted(df["currency"].dropna().unique().tolist())
        return ["All"] + banks, ["All"] + companies, ["All"] + currencies
    except Exception:
        return ["All"], ["All"], ["All"]

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

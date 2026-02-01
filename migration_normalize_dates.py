import sqlite3
import re
import pandas as pd

DB_NAME = "ocr_data.db"

def normalize_date(date_str):
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    months_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
        'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    try:
        # Case 1: DD-MMM-YYYY
        m = re.match(r"(\d{1,2})-([a-zA-Z]{3})-(\d{4})", date_str)
        if m:
            day, mon, year = m.groups()
            mon_num = months_map.get(mon.lower(), '01')
            return f"{year}-{mon_num}-{int(day):02d}"
        # Case 2: DD/MM/YYYY
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if m:
            day, mon, year = m.groups()
            return f"{year}-{int(mon):02d}-{int(day):02d}"
        # Case 3: MMM DD, YYYY
        m = re.match(r"([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})", date_str)
        if m:
            mon_name, day, year = m.groups()
            mon_num = '01'
            for k, v in months_map.items():
                if mon_name.lower().startswith(k):
                    mon_num = v
                    break
            return f"{year}-{mon_num}-{int(day):02d}"
        # Case 4: YYYY-MM-DD (Ensure exactly 10 chars, ignore time)
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
        if m:
            year, mon, day = m.groups()
            return f"{year}-{int(mon):02d}-{int(day):02d}"
    except Exception:
        pass
    return date_str

def migrate():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, doc_date FROM transactions")
    rows = cursor.fetchall()
    
    updated_count = 0
    for row_id, old_date in rows:
        new_date = normalize_date(old_date)
        if new_date != old_date:
            cursor.execute("UPDATE transactions SET doc_date = ? WHERE id = ?", (new_date, row_id))
            updated_count += 1
            
    conn.commit()
    print(f"Migration complete. Updated {updated_count} records.")
    conn.close()

if __name__ == "__main__":
    migrate()

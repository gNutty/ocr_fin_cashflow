import sqlite3
import pandas as pd

conn = sqlite3.connect("ocr_data.db")
df = pd.read_sql_query("SELECT id, doc_date FROM transactions LIMIT 10", conn)
print("Database Content (Top 10):")
print(df)

df_all = pd.read_sql_query("SELECT DISTINCT doc_date FROM transactions", conn)
print("\nUnique doc_dates in DB:")
print(df_all)

conn.close()

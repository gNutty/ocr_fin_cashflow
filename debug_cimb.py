import os
import sys
import json
sys.path.append(r'd:\Project\ocr\ocr_fin_cashflow')
from ocr_process import process_single_pdf

pdf_path = r'd:\Project\ocr\ocr_fin_cashflow\source\ADV & SWIFT FOR 025001625815, 025001625796, 025001626248, 025001626274, 025001626236, 025001626286, 025001626317 - CIMB - CP T.pdf'
master_file = r'd:\Project\ocr\ocr_fin_cashflow\Master\AC_Master.xlsx'

print(f"Processing: {pdf_path}")
entries, text = process_single_pdf(pdf_path, master_path=master_file)

with open('cimb_raw_text.txt', 'w', encoding='utf-8') as f:
    f.write(text)

with open('cimb_entries.json', 'w', encoding='utf-8') as f:
    json.dump(entries, f, indent=2, ensure_ascii=False)

print(f"Done. Saved raw text to cimb_raw_text.txt and entries to cimb_entries.json")

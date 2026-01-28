import re

test_text = """
; 02-12-25;16:52 ;                   CP Tdg Singapore ;             # ]/ 13

SINGAPORE BRANCH !     65 ๐ทนแล Street, #32-05/07, OCBC Centre. Singapore 049613, TEL: (66) 6633 6691, FAX: (65) 6533-0930
Co, Req. No. : S96FC4735E

To:                                                     DEBIT ADVICE

CP Trading Co Ltd                                   Date :             02-Dec-2025
British Virgin Islands

c/o 6001 Beach Road                                           Our Ref:          IC 25/0662
#14-01 Golden Mile Tower                                                                :

Singapore 199589

A/C'NO:     9943-000613-001                                  :       USD 87,300.06

We have today DEBITED your USD account with us, details as follow :-

DOCUMENTS FOR             USD 87,215.55

DRAWER: MAHESH EDIBLE OIL MANUFACTURES PVT LTD

Bill Amount                                                                                 : USD                   87,215.55
0,0625% commission                                                                    : USD                         54.51
Swift                                                                                           : USD                         30.00
Total Debited                                                                               : USD                   87,300.06
Remarks: As per your instructions, we will courier the documents to

Ms Maria Samlee, Bangkok, Thailand.

Yours Sincerely,
‘For KRUNG THAI BANK PUBLIC COMPANY LIMITED
Singapore Branch

AUTHORISED SIGNATURE
"""

def test_regex():
    # A/C No
    # Improved regex logic
    ac_regex = r"(?:A[/.]?C['\s]*NO|Account\s*No)[;:\.\s]*\s*([\d-]+)"
    ac_match = re.search(ac_regex, test_text, re.IGNORECASE)
    ac_no = ac_match.group(1).strip() if ac_match else "NOT FOUND"
    print(f"A/C No: {ac_no}")

    # Date
    date_regex = r"Date\s*[;:\.]?\s*([\d]{1,2}-[\w]{3}-[\d]{4})"
    date_match = re.search(date_regex, test_text, re.IGNORECASE)
    date_val = date_match.group(1).strip() if date_match else "NOT FOUND"
    print(f"Date: {date_val}")

    # Our Ref
    ref_regex = r"(?:Our Ref|B/C|REFERENCE NO\.)\s*[;:\.]?\s*([\w\d/ -]+)"
    ref_match = re.search(ref_regex, test_text, re.IGNORECASE)
    ref_val = ref_match.group(1).strip().split('\n')[0] if ref_match else "NOT FOUND"
    print(f"Reference No: {ref_val}")

    # Total Value
    # Using the keywords logic from ocr_process.py
    val_keywords = ["Total Debited", "Amount Credited", "Total Value", "Bill Amount"]
    total_val = "NOT FOUND"
    for kw in val_keywords:
        match = re.search(rf"{kw}\s*[:;]?\s*[A-Z]{3}?\s*([\d,]+\.\d{2})", test_text, re.IGNORECASE)
        if match:
            total_val = match.group(1).replace(",", "")
            break
    print(f"Total Value: {total_val}")

if __name__ == "__main__":
    test_regex()

import os
import re
import json
import requests
import pytesseract
import pandas as pd
from pdf2image import convert_from_path
import base64
from io import BytesIO

# --- Configuration ---
TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
POPPLER_PATH = None 

def setup_tesseract():
    if os.path.exists(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def ocr_tesseract(pdf_path):
    setup_tesseract()
    images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)
    text = ""
    for i, image in enumerate(images):
        page_text = pytesseract.image_to_string(image, lang='tha+eng')
        text += f"--- Page {i + 1} ---\n{page_text}\n\n"
    return text

def ocr_typhoon(pdf_path, api_key):
    url = "https://api.opentyphoon.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)
    full_text = ""
    
    for i, img in enumerate(images):
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        payload = {
            "model": "typhoon-v1.5-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this bank document page accurately. Return only the extracted text."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_str}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 2048
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            page_text = response.json()['choices'][0]['message']['content']
            full_text += f"--- Page {i + 1} ---\n{page_text}\n\n"
        except Exception as e:
            print(f"Typhoon error on page {i+1}: {e}")
            setup_tesseract()
            page_text = pytesseract.image_to_string(img, lang='tha+eng')
            full_text += f"--- Page {i + 1} (Fallback Tesseract) ---\n{page_text}\n\n"
            
    return full_text

def extract_fields_from_chunk(text):
    fields = {
        "A/C No": None,
        "Document Date": None,
        "Reference No": None,
        "Total Value": None,
        "Bank Name": None,
        "Company Name": None,
        "Transaction": None
    }
    
    # A/C No: Handle variations and OCR noise (e.g., A/ICNO, AIC No, AVCNO, A/C'NO)
    # Using a list of patterns to try in order of specificity
    ac_patterns = [
        r"(?:A[/|I]?C['\s]*NO|Account\s*No|AVCNO|AIC\s?No)[;:\.\s]*\s*([\d-]{7,})", # Priority: Specific keywords + long enough number
        r"Id>([\d-]{7,})</Id", # XML-like patterns found in SWIFT reports
        r"(?:A[/|I]?C['\s]*NO|Account\s*No|AVCNO|AIC\s?No)[;:\.\s]*\s*([\d-]+)"  # Fallback: Keywords with any number/hyphen
    ]
    
    for pattern in ac_patterns:
        ac_match = re.search(pattern, text, re.IGNORECASE)
        if ac_match:
            val = ac_match.group(1).strip()
            # Basic validation: Usually ac nos are more than 5 digits/chars
            if len(val) >= 5:
                fields["A/C No"] = val
                break
    
    # Document Date: DD-MMM-YYYY or MMM DD, YYYY
    # Try finding the date pattern directly if "Date :" is missing
    date_match = re.search(r"Date\s*[;:\.]?\s*([\d]{1,2}-[\w]{3}-[\d]{4})", text, re.IGNORECASE)
    if not date_match:
        # Search for date pattern anywhere in the text if not near "Date"
        date_match = re.search(r"(\b\d{1,2}-[\w]{3}-\d{4}\b)", text, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r"([A-Z]+ \d{1,2}, \d{4})", text, re.IGNORECASE)
        
    if date_match:
        fields["Document Date"] = date_match.group(1).strip()
    
    # Reference No: Our Ref, B/C, or look for IC/EC pattern
    # Krungthai specific: Our Ref: OR 25/0055, EC 25/0708, IC 25/0662
    ref_match = re.search(r"(?:Our Ref|B/C|REFERENCE NO\.|Our Ref[:;]|c/o.*?[:;])\s*[;:\.]?\s*([\w\d/ -]{5,})", text, re.IGNORECASE)
    if not ref_match:
         # Look for the pattern XX YY/ZZZZ directly (e.g., OR 25/0055)
         ref_match = re.search(r"\b((?:OR|IC|EC|BC)\s?\d{2}/\d{4})\b", text, re.IGNORECASE)
         
    if ref_match:
        ref_val = ref_match.group(1).strip().split('\n')[0].strip()
        # Clean up if it matched something like "A/C No" or "AMOUNT"
        if any(x in ref_val.upper() for x in ["A/C", "AMOUNT", "DATE"]):
            # Try to extract just the code if possible
            re_code = re.search(r"((?:OR|IC|EC|BC)\s?\d{2}/\d{4})", ref_val, re.IGNORECASE)
            if re_code:
                ref_val = re_code.group(1)
            else:
                ref_val = None
        fields["Reference No"] = ref_val
    
    # Total Value: Amount Credited, Total Debited, etc.
    # Prioritize specific keywords
    val_keywords = [
        "Amount Credited", "Total Debited", "Total Credited", 
        "Total Amount", "Total Value", "Debit Amount", "Credit Amount", "Amount"
    ]
    
    for kw in val_keywords:
        # Try same line first
        val_match = re.search(rf"{kw}\s*[:;]?\s*[A-Z]{3}?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
        if val_match:
            fields["Total Value"] = val_match.group(1).replace(",", "")
            # If it's "Amount Credited", we are very sure, but let's check if there's a better match later
            if "Amount Credited" in kw:
                break
        
        # Try looking ahead in the chunk
        kw_match = re.search(rf"{kw}\s*[:;]?", text, re.IGNORECASE)
        if kw_match:
            # Search for all currency patterns after the keyword
            lookahead_text = text[kw_match.end():]
            all_vals = re.findall(r"(?:[A-Z]{3}?\s*)?([\d,]+\.\d{2})(?!\d)", lookahead_text)
            if all_vals:
                # For "Amount Credited", the target value is often the LAST one in the section
                if "Amount Credited" in kw:
                    fields["Total Value"] = all_vals[-1].replace(",", "")
                else:
                    fields["Total Value"] = all_vals[0].replace(",", "")
                break
    
    # Fallback for Total Value: Look for currency pattern following a colon if still None
    if not fields["Total Value"]:
        # Try to find a pattern like ': USD 123,456.78' or ': 123,456.78'
        val_match = re.search(r"[:;]\s*[A-Z]{3}?\s*([\d,]+\.\d{2})(?!\d)", text)
        if val_match:
            fields["Total Value"] = val_match.group(1).replace(",", "")
    
    # Final cleanup: if Total Value is still None, take the last currency pattern in the chunk
    if not fields["Total Value"]:
        all_vals = re.findall(r"[A-Z]{3}?\s*([\d,]+\.\d{2})(?!\d)", text)
        if all_vals:
            fields["Total Value"] = all_vals[-1].replace(",", "")
    
    # Transaction Type
    if re.search(r"DEBIT ADVICE", text, re.IGNORECASE):
        fields["Transaction"] = "DEBIT"
    elif re.search(r"CREDIT ADVICE", text, re.IGNORECASE):
        fields["Transaction"] = "CREDIT"
        
    return fields

def extract_all_entries(text):
    # Map page numbers to text positions
    page_map = []
    for m in re.finditer(r"--- Page (\d+) ---", text):
        page_map.append((m.start(), int(m.group(1))))
    
    # If no pages found, assume Page 1 (start at 0)
    if not page_map:
        page_map.append((0, 1))

    # Split text into chunks based on header markers (e.g., DEBIT ADVICE, CREDIT ADVICE, RECEIPT NO)
    # Using lookahead (?=...) so the delimiter is kept at the start of the chunk
    chunks = re.split(r"(?=(?:DEBIT ADVICE|CREDIT ADVICE|RECEIPT NO\.))", text, flags=re.IGNORECASE)
    
    results = []
    last_ac_no = None  # Store the last seen A/C No to "forward-fill" if missing
    
    current_pos = 0
    
    for chunk in chunks:
        if not chunk: 
            continue
            
        # Determine Page Number for this chunk based on its start position
        # Find the last page marker that is before or at the start of this chunk
        page = 1
        for p_start, p_num in page_map:
            if p_start <= current_pos:
                page = p_num
            else:
                break
        
        # Process chunk
        # Pre-check removed to ensure we don't skip valid chunks due to keyword casing
        data = extract_fields_from_chunk(chunk)
        data["Page"] = page
        
        # Special logic: If A/C No is missing, use the one from the previous entry
        if not data["A/C No"] and last_ac_no:
            data["A/C No"] = last_ac_no
        elif data["A/C No"]:
            last_ac_no = data["A/C No"]
            
        if any(v for k, v in data.items() if k != "Page"): # Only add if at least one field found
            results.append(data)
        
        # Advance position
        current_pos += len(chunk)
        
    return results

def lookup_master(ac_no, master_path):
    if not ac_no or not os.path.exists(master_path):
        return None, None
    
    try:
        df = pd.read_excel(master_path)
        df['ACNO'] = df['ACNO'].astype(str).str.replace("'", "").str.strip()
        clean_ac = str(ac_no).strip().replace(" ", "")
        
        # Exact match or partial match for account number
        match = df[df['ACNO'].apply(lambda x: clean_ac in x or x in clean_ac)]
        if not match.empty:
            return match.iloc[0]['BankName'], match.iloc[0]['AccountName']
    except Exception as e:
        print(f"Lookup error: {e}")
    
    return None, None

def process_single_pdf(pdf_path, engine="Tesseract", api_key=None, master_path=None):
    if engine == "Typhoon" and api_key:
        text = ocr_typhoon(pdf_path, api_key)
    else:
        text = ocr_tesseract(pdf_path)
    
    entries = extract_all_entries(text)
    
    for data in entries:
        if master_path:
            bank, company = lookup_master(data["A/C No"], master_path)
            data["Bank Name"] = bank
            data["Company Name"] = company
            
    return entries, text

if __name__ == "__main__":
    import json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    master_file = os.path.join(base_dir, 'Master', 'AC_Master.xlsx')
    test_pdf = os.path.join(base_dir, 'source', 'FUNDS IN FOR INV 360352, 2540700066,2500061873,2540700067 -KTB -CP T.pdf')
    
    api_key = None
    config_path = os.path.join(base_dir, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            api_key = json.load(f).get("API_KEY")

    if os.path.exists(test_pdf):
        print(f"Testing OCR on: {test_pdf}")
        # Run with Tesseract as it's more stable for this test
        results, raw_text = process_single_pdf(test_pdf, engine="Tesseract", master_path=master_file)
        print("Extracted Data:", json.dumps(results, indent=2))
        
        output_dir = os.path.join(base_dir, 'output', 'test_results')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        txt_name = os.path.basename(test_pdf).replace(".pdf", ".txt")
        with open(os.path.join(output_dir, txt_name), 'w', encoding='utf-8') as f:
            f.write(raw_text)
        print(f"Raw text saved to {output_dir}")

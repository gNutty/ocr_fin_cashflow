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

# --- Parser Strategy Pattern ---

class BankParser:
    def extract_chunk(self, text):
        """Extract fields from a text chunk. Must be implemented by subclasses."""
        raise NotImplementedError

class KrungthaiParser(BankParser):
    def extract_chunk(self, text):
        fields = {
            "A/C No": None,
            "Document Date": None,
            "Reference No": None,
            "Total Value": None,
            "Bank Name": "Krungthai", # Auto-fill Bank Name
            "Company Name": None,
            "Transaction": None
        }
        
        # A/C No
        ac_patterns = [
            r"(?:A[/|I]?C['\s]*NO|Account\s*No|AVCNO|AIC\s?No)[;:\.\s\=]*\s*([\d\-\=]{7,})", 
            r"Id>([\d-]{7,})</Id", 
            r"(?:A[/|I]?C['\s]*NO|Account\s*No|AVCNO|AIC\s?No)[;:\.\s\=]*\s*([\d\-\=]+)"
        ]
        for pattern in ac_patterns:
            ac_match = re.search(pattern, text, re.IGNORECASE)
            if ac_match:
                val = ac_match.group(1).strip().replace("=", "-")
                if len(val) >= 5:
                    fields["A/C No"] = val
                    break
        
        # Document Date
        date_match = re.search(r"Date\s*[;:\.]?\s*([\d]{1,2}-[\w]{3}-[\d]{4})", text, re.IGNORECASE)
        if not date_match:
            date_match = re.search(r"(\b\d{1,2}-[\w]{3}-\d{4}\b)", text, re.IGNORECASE)
        if not date_match:
            date_match = re.search(r"([A-Z]+ \d{1,2}, \d{4})", text, re.IGNORECASE)
        if date_match:
            fields["Document Date"] = date_match.group(1).strip()
        
        # Reference No
        ref_match = re.search(r"(?:Our Ref|B/C|REFERENCE NO\.|Our Ref[:;]|c/o.*?[:;])\s*[;:\.]?\s*([\w\d/ -]{5,})", text, re.IGNORECASE)
        if not ref_match:
             ref_match = re.search(r"\b((?:OR|IC|EC|BC)\s?\d{2}/\d{4})\b", text, re.IGNORECASE)
        if ref_match:
            ref_val = ref_match.group(1).strip().split('\n')[0].strip()
            if any(x in ref_val.upper() for x in ["A/C", "AMOUNT", "DATE"]):
                re_code = re.search(r"((?:OR|IC|EC|BC)\s?\d{2}/\d{4})", ref_val, re.IGNORECASE)
                ref_val = re_code.group(1) if re_code else None
            fields["Reference No"] = ref_val
        
        # Transaction Type
        if re.search(r"DEBIT\s*ADVICE", text, re.IGNORECASE):
            fields["Transaction"] = "DEBIT"
        elif re.search(r"CREDIT\s*ADVICE", text, re.IGNORECASE):
            fields["Transaction"] = "CREDIT"
        
        # Only extract Total Value if we have a transaction type
        if fields["Transaction"]:
            # Skip extraction if this looks like a Shipment Receipt (which often has false positive totals)
            is_shipment_receipt = re.search(r"Shipment\s*Receipt", text, re.IGNORECASE)
            is_advice = re.search(r"ADVICE", text, re.IGNORECASE)
            
            if not (is_shipment_receipt and not is_advice):
                val_patterns = [
                    (r"A[nm]ount\s*Credited", False), 
                    (r"Total\s*Debited", False), 
                    (r"Total\s*Credited", False), 
                    (r"Total\s*Amount", False), 
                    (r"Total\s*Value", False), 
                    (r"Debit\s*Amount", False), 
                    (r"Credit\s*Amount", False), 
                    (r"Amount", True) # Keep pick_last for "Amount" as it's a weak keyword
                ]
                
                for kw_pattern, pick_last in val_patterns:
                    kw_match = re.search(kw_pattern, text, re.IGNORECASE)
                    if kw_match:
                        lookahead_text = text[kw_match.end():]
                        all_vals = re.findall(r"(?:[A-Z]{3}|[ก-ฮ]{3}|[฿\$])?[\s\.]*((?:\d{1,3}[\s,]*)+\.\d{2})(?!\d)", lookahead_text)
                        if all_vals:
                            val_idx = -1 if pick_last else 0
                            fields["Total Value"] = re.sub(r"[\s,]", "", all_vals[val_idx])
                            break
            
                # Absolute Last Resort
                if not fields["Total Value"]:
                    all_vals = re.findall(r"(?:[A-Z]{3}|[ก-ฮ]{3}|[฿\$])?[\s\.]*((?:\d{1,3}[\s,]*)+\.\d{2})(?!\d)", text)
                    if all_vals: 
                        fields["Total Value"] = re.sub(r"[\s,]", "", all_vals[-1])
            
        return fields

class SantanderParser(BankParser):
    def extract_chunk(self, text):
        fields = {
            "A/C No": None,
            "Document Date": None,
            "Reference No": None,
            "Total Value": None,
            "Bank Name": "Santander",
            "Company Name": None,
            "Transaction": None
        }
        
        # Transaction Type identification
        # Santander OCR sometimes sees "DEBIT ADVICE" as something messy but "DEBITED" is usually clear
        if re.search(r"DEBIT\s*ADVICE|WE\s*HAVE\s*DEBITED", text, re.IGNORECASE):
            fields["Transaction"] = "DEBIT"
        elif re.search(r"CREDIT\s*ADVICE|WE\s*HAVE\s*CREDITED", text, re.IGNORECASE):
            fields["Transaction"] = "CREDIT"
        
        # Identification check: Only proceed if it looks like an advice
        if not fields["Transaction"] and not re.search(r"KING\s*ovice|SANTANDER", text, re.IGNORECASE):
            return fields

        # A/C No: "A/C 0069-100128-251" - handling possible OCR noise
        ac_match = re.search(r"A/C\s*[:.-]?\s*([\d-]+)", text, re.IGNORECASE)
        if ac_match:
            fields["A/C No"] = ac_match.group(1).strip()
            
        # Document Date: "DATE : December 18, 2025" -> yyyy-MM-dd
        # Handling variations in markers: ":" or ">" or "ล" or "บรด" or just space
        date_match = re.search(r"DATE\s*[:>ล\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.IGNORECASE)
        if date_match:
            date_str = date_match.group(1).strip()
            try:
                # Use pandas for flexible date parsing
                dt = pd.to_datetime(date_str)
                fields["Document Date"] = dt.strftime('%Y-%m-%d')
            except:
                fields["Document Date"] = date_str # Fallback

        # Total Value: Last numeric sequence (usually at the bottom)
        # Handle formats like 48,022.84
        all_vals = re.findall(r"(?:\d{1,3}(?:[\s,]\d{3})*|\d+)\.\d{2}(?!\d)", text)
        if all_vals:
            fields["Total Value"] = re.sub(r"[\s,]", "", all_vals[-1])
            
        # Reference No: "OUR REF : ...", "Ref: ..." etc.
        ref_match = re.search(r"OUR\s*REF\s*[:>ล\s]*([\w\d/-]{5,})", text, re.IGNORECASE)
        if not ref_match:
             ref_match = re.search(r"REF\s*[:>ล\s]*([\w\d/-]{5,})", text, re.IGNORECASE)
        if ref_match:
            fields["Reference No"] = ref_match.group(1).strip()
            
        print("Using Santander Parser")
        return fields

class GenericParser(BankParser):
    def extract_chunk(self, text):
        # reuse Krungthai logic as a baseline fallback for now, or simplify
        # For safety, let's just reuse Krungthai's logic logic but clear the Bank Name
        parser = KrungthaiParser()
        data = parser.extract_chunk(text)
        data["Bank Name"] = None # Don't assume bank name
        return data

def get_bank_parser(text):
    if "KRUNGTHAI" in text.upper():
        return KrungthaiParser()
    elif "CIMB" in text.upper():
        return CIMBParser()
    elif "SANTANDER" in text.upper() or "DEBIT ADVICE" in text.upper() or "CREDIT ADVICE" in text.upper() or "KING OVICE" in text.upper():
        return SantanderParser()
    else:
        return GenericParser()

def extract_all_entries(text):
    # Detect Parser Strategy
    parser = get_bank_parser(text)
    print(f"Detected Parser: {parser.__class__.__name__}")
    
    # Map page numbers to text positions
    page_map = []
    for m in re.finditer(r"--- Page (\d+) ---", text):
        page_map.append((m.start(), int(m.group(1))))
    
    if not page_map:
        page_map.append((0, 1))

    # Split text into chunks based on header markers (Common checks, can be moved to parser if needed)
    # For now, keep the split logic generic or make it robust enough for both
    # Krungthai: DEBIT ADVICE, CREDIT ADVICE
    # CIMB: To be determined. Assuming potentially similar or we process the whole text if splits don't apply.
    # Split text into chunks based on header markers
    # Added "Shipment Receipt" and page markers to ensure clean separation of advice sections
    chunks = re.split(r"(?=(?:DEBIT ADVICE|CREDIT ADVICE|RECEIPT NO\.|Shipment Receipt|KING\s*ovice|--- Page \d+ ---))", text, flags=re.IGNORECASE)
    
    results = []
    header_state = {
        "Document Date": None,
        "Reference No": None,
        "A/C No": None
    }
    
    current_pos = 0
    
    for chunk in chunks:
        if not chunk: 
            continue
            
        # Determine Page Number
        page = 1
        for p_start, p_num in page_map:
            if p_start <= current_pos:
                page = p_num
            else:
                break
        
        # Filter: Skip chunks that don't look like Advice (unless they contain header info we need)
        is_actual_advice = re.search(r"DEBIT\s*ADVICE|CREDIT\s*ADVICE", chunk, re.IGNORECASE)
        
        # Strategy Extract
        data = parser.extract_chunk(chunk)
        data["Page"] = page
        
        # Merge with previous header state
        for key in ["Document Date", "Reference No", "A/C No"]:
            if data[key]:
                header_state[key] = data[key]
            else:
                data[key] = header_state[key]
            
        # Only append IF it's actual advice OR it has transaction data (as fallback)
        if is_actual_advice or data["Transaction"]:
            results.append(data)
        elif results and not any(v for k, v in data.items() if k not in ["Page", "Bank Name", "Document Date", "Reference No", "A/C No"]):
            # Update last result with potential header info from this chunk
            last_res = results[-1]
            for k in ["Document Date", "Reference No", "A/C No"]:
                if not last_res[k] and data[k]:
                    last_res[k] = data[k]
            
        current_pos += len(chunk)
        
    return results

import db_manager as db

def lookup_master(ac_no, master_path=None):
    """
    Lookup Bank, Company, and Currency from Database.
    master_path argument is kept for compatibility but ignored.
    """
    return db.lookup_master_info(ac_no)

def process_single_pdf(pdf_path, engine="Tesseract", api_key=None, master_path=None):
    if engine == "Typhoon" and api_key:
        text = ocr_typhoon(pdf_path, api_key)
    else:
        text = ocr_tesseract(pdf_path)
    
    entries = extract_all_entries(text)
    
    for data in entries:
        if master_path:
            bank, company, currency = lookup_master(data["A/C No"], master_path)
            data["Bank Name"] = bank
            data["Company Name"] = company
            data["Currency"] = currency
            
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

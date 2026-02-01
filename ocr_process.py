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

class CIMBParser(BankParser):
    def extract_chunk(self, text):
        fields = {
            "A/C No": None,
            "Document Date": None,
            "Reference No": None,
            "Total Value": None,
            "Bank Name": "CIMB",
            "Company Name": None,
            "Transaction": None
        }
        
        # A/C No: "Account No." -> "2200027067340"
        ac_patterns = [
            r"Account\s*No[.,\s]*\s*([\d]+)",
            r"A/C\s*No[.,\s]*\s*([\d]+)",
            r"Debit\s*Current\s*Account\s*[\(\[]?\s*Account\s*No[.,\s]*\s*([\d]+)", # Robust catch
            r"Current\s*Account\s*[\(\[]?\s*Account\s*No[.,\s]*\s*([\d]+)\s*[\)\]]?"
        ]
        for pattern in ac_patterns:
            ac_match = re.search(pattern, text, re.IGNORECASE)
            if ac_match:
                fields["A/C No"] = ac_match.group(1).strip()
                break
            
        # Document Date: "Date:" -> "05/12/2025"
        date_match = re.search(r"Date\s*[:]\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
        if not date_match:
             date_match = re.search(r"Date\s*[:]\s*(\d{1,2}-\d{1,2}-\d{4})", text, re.IGNORECASE)
        if date_match:
            fields["Document Date"] = date_match.group(1).strip()
            
        # Reference No: Inward Bill Collection No. : 025001625815
        ref_patterns = [
            r"Inward\s*Bill\s*Collection\s*No\.?\s*[:;.-]?\s*([\w\d/-]{5,})",
            r"Our\s*Ref\s*[:;.-]?\s*([\w\d/-]{5,})",
            r"SWIFT\s*ID\s*[:;.-]?\s*([\w]{5,})" # Fallback
        ]
        for pattern in ref_patterns:
            ref_match = re.search(pattern, text, re.IGNORECASE)
            if ref_match:
                fields["Reference No"] = ref_match.group(1).strip()
                break
             
        # Transaction Type
        if re.search(r"DEBIT\s*ADVICE", text, re.IGNORECASE):
            fields["Transaction"] = "DEBIT"
        elif re.search(r"CREDIT\s*ADVICE", text, re.IGNORECASE):
            fields["Transaction"] = "CREDIT"
             
        # Total Value: Only extract if transaction detected
        if fields["Transaction"]:
            # Prioritize numbers preceded by currency (USD/THB/etc)
            cur_vals = re.findall(r"(?:[A-Z]{3}|[ก-ฮ]{3}|[฿\$])[\s\.]*((?:\d{1,3}[\s,]*)+\.\d{2})(?!\d)", text)
            if cur_vals:
                fields["Total Value"] = re.sub(r"[\s,]", "", cur_vals[-1])
            else:
                # Fallback: Last number with 2 decimals
                all_vals = re.findall(r"(?:\d{1,3}[\s,]*)+\.\d{2}(?!\d)", text)
                if all_vals:
                     fields["Total Value"] = re.sub(r"[\s,]", "", all_vals[-1])
            
        print("Using CIMB Parser")
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
    chunks = re.split(r"(?=(?:DEBIT ADVICE|CREDIT ADVICE|RECEIPT NO\.|Shipment Receipt|--- Page \d+ ---))", text, flags=re.IGNORECASE)
    
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

def lookup_master(ac_no, master_path):
    if not ac_no or not os.path.exists(master_path):
        return None, None, None
    
    try:
        df = pd.read_excel(master_path)
        df['ACNO'] = df['ACNO'].astype(str).str.replace("'", "").str.strip()
        clean_ac = str(ac_no).strip().replace(" ", "")
        
        # Exact match or partial match for account number
        match = df[df['ACNO'].apply(lambda x: clean_ac in x or x in clean_ac)]
        if not match.empty:
            return match.iloc[0]['BankName'], match.iloc[0]['AccountName'], match.iloc[0]['Currency']
    except Exception as e:
        print(f"Lookup error: {e}")
    
    return None, None, None

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

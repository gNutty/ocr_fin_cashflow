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
        "Company Name": None
    }
    
    # A/C No: Handle :, ., ;, or just space
    ac_match = re.search(r"A/C\s?NO[;:\.]?\s*([\d-]+)", text, re.IGNORECASE)
    if ac_match:
        fields["A/C No"] = ac_match.group(1).strip()
    
    # Document Date: DD-MMM-YYYY or MMM DD, YYYY
    # Try finding the date pattern directly if "Date :" is missing
    date_match = re.search(r"Date\s*[;:\.]?\s*([\d]{1,2}-[\w]{3}-[\d]{4})", text, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r"\s+([\d]{1,2}-[\w]{3}-[\d]{4})", text, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r"([A-Z]+ \d{1,2}, \d{4})", text, re.IGNORECASE)
        
    if date_match:
        fields["Document Date"] = date_match.group(1).strip()
    
    # Reference No: Our Ref, B/C, or look for IC pattern
    ref_match = re.search(r"(?:Our Ref|B/C|REFERENCE NO\.|Our Ref[:;]|c/o.*?[:;])\s*([\w\d/ -]+)", text, re.IGNORECASE)
    if not ref_match:
         ref_match = re.search(r"(IC\s?\d{2}/\d{4})", text, re.IGNORECASE)
         
    if ref_match:
        fields["Reference No"] = ref_match.group(1).strip().split('\n')[0]
    
    # Total Value: Total Debited, Total Amount, or Debit Amount
    val_match = re.search(r"(?:Total Debited|Total Amount|Total Value|Debit Amount|Amount)\s*[:;]?\s*[A-Z]{3}?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if not val_match:
        val_match = re.search(r"Total\s*.*?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
        
    if val_match:
        fields["Total Value"] = val_match.group(1).replace(",", "")
        
    return fields

def extract_all_entries(text):
    # Split text into chunks based on header markers (e.g., DEBIT ADVICE, RECEIPT NO)
    chunks = re.split(r"(?=DEBIT ADVICE|RECEIPT NO\.)", text, flags=re.IGNORECASE)
    results = []
    for chunk in chunks:
        if "Total" in chunk or "A/C" in chunk:
            data = extract_fields_from_chunk(chunk)
            if any(data.values()): # Only add if at least one field found
                results.append(data)
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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    master_file = os.path.join(base_dir, 'Master', 'AC_Master.xlsx')
    test_pdf = os.path.join(base_dir, 'source', 'ADV + SWIFT FOR IC 25-0660, 0661,0656 -KTB -CP T.pdf')
    
    api_key = None
    config_path = os.path.join(base_dir, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            api_key = json.load(f).get("API_KEY")

    if os.path.exists(test_pdf):
        print(f"Testing OCR on: {test_pdf}")
        # Testing with Tesseract first as it's faster and Typhoon has 400 issues
        results, raw_text = process_single_pdf(test_pdf, engine="Tesseract", master_path=master_file)
        print("Extracted Data:", json.dumps(results, indent=2))
        
        output_dir = os.path.join(base_dir, 'output', 'test_results')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        txt_name = os.path.basename(test_pdf).replace(".pdf", ".txt")
        with open(os.path.join(output_dir, txt_name), 'w', encoding='utf-8') as f:
            f.write(raw_text)
        print(f"Raw text saved to {output_dir}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    master_file = os.path.join(base_dir, 'Master', 'AC_Master.xlsx')
    test_pdf = os.path.join(base_dir, 'source', 'ADV + SWIFT FOR IC 25-0660, 0661,0656 -KTB -CP T.pdf')
    
    api_key = None
    config_path = os.path.join(base_dir, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            api_key = json.load(f).get("API_KEY")

    if os.path.exists(test_pdf):
        print(f"Testing OCR on: {test_pdf}")
        # Note: Processing 9 pages with Typhoon might take a while.
        result, raw_text = process_single_pdf(test_pdf, engine="Typhoon", api_key=api_key, master_path=master_file)
        print("Extracted Data:", json.dumps(result, indent=2))
        
        output_dir = os.path.join(base_dir, 'output', 'test_typhoon')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        txt_name = os.path.basename(test_pdf).replace(".pdf", ".txt")
        with open(os.path.join(output_dir, txt_name), 'w', encoding='utf-8') as f:
            f.write(raw_text)
        print(f"Raw text saved to {output_dir}")

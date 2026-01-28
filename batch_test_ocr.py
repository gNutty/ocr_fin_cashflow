import os
import ocr_process
import json

def run_batch_test():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(base_dir, 'source')
    output_dir = os.path.join(base_dir, 'output', 'batch_test')
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    pdf_files = [f for f in os.listdir(source_dir) if f.lower().endswith('.pdf')]
    print(f"Found {len(pdf_files)} PDF files in source folder.\n")
    
    report = []
    
    for filename in pdf_files:
        pdf_path = os.path.join(source_dir, filename)
        print(f"Processing: {filename}...")
        
        try:
            # Using Tesseract for testing as it's the default/fallback
            entries, raw_text = ocr_process.process_single_pdf(pdf_path, engine="Tesseract")
            
            # Save raw text for debugging
            txt_name = filename.replace(".pdf", ".txt")
            with open(os.path.join(output_dir, txt_name), 'w', encoding='utf-8') as f:
                f.write(raw_text)
                
            has_ac = False
            ac_list = []
            for entry in entries:
                if entry.get("A/C No"):
                    has_ac = True
                    ac_list.append(entry["A/C No"])
            
            status = "SUCCESS" if has_ac else "FAILED"
            print(f"  Status: {status} | ACs: {ac_list}")
            
            report.append({
                "filename": filename,
                "status": status,
                "ac_numbers": ac_list,
                "entries_found": len(entries)
            })
            
        except Exception as e:
            print(f"  Error: {e}")
            report.append({
                "filename": filename,
                "status": "ERROR",
                "error": str(e)
            })
            
    # Save final report
    with open(os.path.join(output_dir, "batch_report.json"), 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
        
    print("\n--- Summary ---")
    success_count = sum(1 for r in report if r["status"] == "SUCCESS")
    failed_count = sum(1 for r in report if r["status"] == "FAILED")
    error_count = sum(1 for r in report if r["status"] == "ERROR")
    
    print(f"Success: {success_count}")
    print(f"Failed:  {failed_count}")
    print(f"Errors:  {error_count}")
    print(f"\nReport saved to: {os.path.join(output_dir, 'batch_report.json')}")

if __name__ == "__main__":
    run_batch_test()

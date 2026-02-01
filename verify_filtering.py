import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from ocr_process import extract_all_entries
except ImportError:
    # If not in the same dir, try to find it
     sys.path.append(r'd:\Project\ocr\ocr_fin_cashflow')
     from ocr_process import extract_all_entries

def test_filtering():
    print("Running Filtering Verification Tests...")
    
    # Test Case 1: Valid Advice
    test_text_1 = """
    KRUNGTHAI BANK
    DEBIT ADVICE
    A/C NO : 123-456-789
    Date : 01-Jan-2024
    Our Ref : OR12/2024
    Total Amount : 1,000.00
    """
    results_1 = extract_all_entries(test_text_1)
    print(f"\nTest 1 (Valid Advice): Found {len(results_1)} entries")
    assert len(results_1) == 1
    assert results_1[0]["Transaction"] == "DEBIT"
    assert results_1[0]["Total Value"] == "1000.00"
    
    # Test Case 2: No Advice Keywords (Should be skipped)
    test_text_2 = """
    KRUNGTHAI BANK
    SOME OTHER DOCUMENT
    A/C NO : 123-456-789
    Date : 01-Jan-2024
    Amount : 5,000.00
    """
    results_2 = extract_all_entries(test_text_2)
    print(f"Test 2 (Invalid Advice): Found {len(results_2)} entries")
    assert len(results_2) == 0
    
    # Test Case 3: Mixed Document (Page 1 header, Page 2 advice)
    test_text_3 = """
    --- Page 1 ---
    KRUNGTHAI BANK
    A/C NO : 123-456-789
    
    --- Page 2 ---
    CREDIT ADVICE
    Date : 02-Jan-2024
    Total Amount : 2,500.00
    """
    results_3 = extract_all_entries(test_text_3)
    print(f"Test 3 (Mixed Document): Found {len(results_3)} entries")
    assert len(results_3) == 1
    assert results_3[0]["A/C No"] == "123-456-789"
    assert results_3[0]["Transaction"] == "CREDIT"
    assert results_3[0]["Total Value"] == "2500.00"

    print("\nAll filtering tests PASSED!")

if __name__ == "__main__":
    test_filtering()

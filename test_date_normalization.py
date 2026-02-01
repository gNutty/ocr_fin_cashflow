import sys
import os
import pandas as pd

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_manager import normalize_date

def test_normalization():
    test_cases = [
        ("01-Jan-2024", "2024-01-01"),
        ("15-Feb-2025", "2025-02-15"),
        ("05/12/2025", "2025-12-05"),
        ("1/5/2024", "2024-05-01"),
        ("January 01, 2024", "2024-01-01"),
        ("Dec 31, 2023", "2023-12-31"),
        ("2024-05-20", "2024-05-20"),
        (None, None),
        ("", None),
    ]
    
    passed = 0
    for input_val, expected in test_cases:
        result = normalize_date(input_val)
        if result == expected:
            print(f"PASSED: '{input_val}' -> '{result}'")
            passed += 1
        else:
            print(f"FAILED: '{input_val}' -> Expected '{expected}', got '{result}'")
            
    print(f"\nResult: {passed}/{len(test_cases)} cases passed.")
    assert passed == len(test_cases)

if __name__ == "__main__":
    test_normalization()

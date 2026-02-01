import re

test_texts = [
    "Total Debited                                                                               : USD                   $8,709.26",
    "Arnount Credited                                      :                USD                     14,301.37"
]

def test_extraction():
    # Final consolidated pattern
    pattern = r"([A-Z]{3}|[ก-ฮ]{3})\s*[^\d\s]*\s*((?:\d{1,3}[\s,]*)+\.\d{2})(?!\d)"
    
    print("--- Testing Final Regex Fixes ---")
    for text in test_texts:
        all_vals = re.findall(pattern, text)
        result = re.sub(r"[\s,]", "", all_vals[-1][1]) if all_vals else "NOT FOUND"
        print(f"Text: '{text.strip()}' -> Extracted: {result}")
        if "$" in text:
            assert result == "8709.26", f"Failed to extract with symbol: {result}"
        else:
            assert result == "14301.37", f"Failed standard extraction: {result}"

if __name__ == "__main__":
    test_extraction()
    print("\nSUCCESS: All Total Value patterns verified!")

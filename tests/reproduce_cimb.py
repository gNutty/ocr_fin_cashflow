
import sys
import os
import re

# Add parent directory to path to import ocr_process
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ocr_process

ocr_text = """
hal CIMB BANK

CIMB BANK SINGAPORE
TRADE SERVICES

Fax: (65) 63172300
SWIFT 1D: CIBBSGSG

Date: 23/12/2025

To:

C.P. TRADING CO., LTD.
6001 BEACH ROAD
#14-01

GOLDEN MILE TOWER
SINGAPORE 199589

Dear Sir/Madam,

DEBIT ADVICE

ORIGINAL COPY

Strictly Private & Confidential

Please note we have debited your account and/or received payment for settlement of Inward Bill Collection.

Inward Bill Collection No.: 025001631715
Maturity Date                :

For USD132,046.20
Rate 1.290150000

Less: Misc/Other Charges

Itern(s)           .                                                                                     Amount

Debit Current Account (Account No, 2200027067340)

Courier                                                USD                32.00
Wire Transfer                                         USD                32.00
Commission                                          USD                82.53
0.0625000% Flat

Commission in Lieu                                  USD               100.00
0.0250000% Flat

Bills                                                    บริง          132.046.20

Total Debited

Ex. Rate

1.000000000
1.000000000
1.000000000
1.000000000

1.000000000

THIS ADVICE IS COMPUTER GENERATED. NO SIGNATURE IS REQUIRED.

CIMB BANK BERHAD (13497-P)

encarporated In Motaysta}

30 Raffles Place #04-01 Singapore 048622
Telephone (65) 6337 5115 Facsimile (65) 6337 5335

weew.cimb.com.sg

SGD170,359.40

USD
0.00

Converted Amount
USD

32.00

32.00

82.53

100.00

132,046.20
USD132,292.73

Page 1/1
"""

def test_extraction():
    print("Testing CIMB Extraction...")
    
    # 1. Test get_bank_parser
    parser = ocr_process.get_bank_parser(ocr_text)
    print(f"Parser detected: {parser.__class__.__name__}")
    
    # 2. Test chunk extraction manually first
    data = parser.extract_chunk(ocr_text)
    print("Direct Chunk Extraction Result:")
    print(data)
    
    # 3. Test full extraction flow
    print("\nFull Flow Extraction Result:")
    results = ocr_process.extract_all_entries(ocr_text)
    for i, res in enumerate(results):
        print(f"Result {i+1}: {res}")

if __name__ == "__main__":
    test_extraction()

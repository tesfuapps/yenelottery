"""
utils/ocr.py — OCR utility for extracting Transaction IDs and Amounts from screenshots.
"""

import pytesseract
import re
import logging
from PIL import Image
import os
from typing import Dict, Optional

# Configure Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

logger = logging.getLogger(__name__)

# Common patterns for Ethiopian transaction IDs:
# Telebirr: Usually alphanumeric e.g. DCB5NI9X3T
# CBE: Usually starts with FT e.g. FT23...
# Dashen/others: various alphanumeric
ID_REGEX_PATTERNS = [
    r'FT[A-Z0-9]{6,14}',  # CBE / Commercial Bank
    r'[A-Z0-9]{9,12}',    # Telebirr / Alphanumeric 10 chars
]

# Patterns for extracting ETB amount
AMOUNT_PATTERNS = [
    r'ETB\s*(\d+(?:\.\d+)?)',           # ETB 280.0
    r'(\d+(?:\.\d+)?)\s*ETB',           # 280.61 ETB
    r'AMOUNT[^\d]*(\d+(?:\.\d+)?)',      # Amount: 280
    r'PAID[^\d]*(\d+(?:\.\d+)?)',        # Paid Amount: 280
]

def extract_receipt_info(image_path: str) -> Dict[str, Optional[str]]:
    """
    Performs OCR on the image and attempts to find a transaction ID and amount.
    Returns a dict: {"tx_id": "...", "amount": "..."}
    """
    result = {"tx_id": "", "amount": None}
    try:
        # Load image
        img = Image.open(image_path)
        
        # Increase contrast/binarize for better OCR if needed (optional)
        # For now, let's try direct OCR
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR Raw Text: {text.strip()}")
        
        # 1. Extract Transaction ID
        for pattern in ID_REGEX_PATTERNS:
            match = re.search(pattern, text.upper())
            if match:
                result["tx_id"] = match.group(0)
                logger.info(f"[OCR] TxID Match Found: {result['tx_id']}")
                break
                
        # If no strict pattern, look for keywords like "Transaction Number" or "Ref"
        if not result["tx_id"]:
            lines = text.split('\n')
            for line in lines:
                line_upper = line.upper()
                if any(k in line_upper for k in ["TRANSACTION NUMBER", "REFERENCE", "REF NO", "TRANS ID", "TRANSACTION ID"]):
                    # Try to extract alphanumeric words after the keyword
                    words = line.split()
                    for word in reversed(words):
                        clean_word = re.sub(r'[^A-Z0-9]', '', word.upper())
                        if len(clean_word) >= 6:
                            result["tx_id"] = clean_word
                            break
                    if result["tx_id"]:
                        break
                        
        # 2. Extract Amount
        for pattern in AMOUNT_PATTERNS:
            match = re.search(pattern, text.upper())
            if match:
                try:
                    result["amount"] = float(match.group(1))
                    logger.info(f"[OCR] Amount Match Found: {result['amount']}")
                    break
                except ValueError:
                    continue
                    
        return result
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return result

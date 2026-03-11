"""
utils/ocr.py — OCR utility for extracting Transaction IDs from screenshots.
"""

import pytesseract
import re
import logging
from PIL import Image
import os

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

def extract_transaction_id(image_path: str) -> str:
    """
    Performs OCR on the image and attempts to find a transaction ID.
    Returns the ID if found, else an empty string.
    """
    try:
        # Load image
        img = Image.open(image_path)
        
        # Increase contrast/binarize for better OCR if needed (optional)
        # For now, let's try direct OCR
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR Raw Text: {text.strip()}")
        
        # Search for patterns
        for pattern in ID_REGEX_PATTERNS:
            match = re.search(pattern, text.upper())
            if match:
                found_id = match.group(0)
                logger.info(f"🔍 OCR Match Found: {found_id}")
                return found_id
                
        # If no strict pattern, look for keywords like "Transaction Number" or "Ref"
        # and take the next word
        lines = text.split('\n')
        for line in lines:
            line_upper = line.upper()
            if any(k in line_upper for k in ["TRANSACTION NUMBER", "REFERENCE", "REF NO", "TRANS ID"]):
                # Try to extract alphanumeric words after the keyword
                words = line.split()
                for word in reversed(words):
                    clean_word = re.sub(r'[^A-Z0-9]', '', word.upper())
                    if len(clean_word) >= 6:
                        return clean_word
                        
        return ""
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return ""

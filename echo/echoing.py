# echo/echoing.py

import re

def echoing(input_text: str) -> str:
    """Remove special characters from input text and return clean text."""
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', input_text)
    return cleaned_text